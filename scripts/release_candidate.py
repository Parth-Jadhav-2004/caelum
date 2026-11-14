#!/usr/bin/env python3
"""Record, assemble and verify a complete immutable Linux release candidate."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import tomllib
from pathlib import Path

from build_package import ROOT, TARGETS


def digest(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular file: {path.name}")
    if not 0 < path.stat().st_size <= 512 * 1024 * 1024:
        raise ValueError(f"Invalid size: {path.name}")
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    return {"sha256": checksum, "size": path.stat().st_size}


def version():
    value = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("Candidate version must be stable major.minor.patch")
    versions = [
        json.loads((ROOT / name).read_text())["version"]
        for name in ("package.json", "src-tauri/tauri.conf.json")
    ]
    versions.append(
        tomllib.loads((ROOT / "src-tauri/Cargo.toml").read_text())["package"]["version"]
    )
    if any(item != value for item in versions):
        raise ValueError("Python, frontend, Rust and Tauri versions must agree")
    return value


def package_names(value):
    return {
        target: {
            "deb": f"caelum_{value}-1_{target}_amd64.deb",
            "arch": f"caelum-{value}-1-x86_64.pkg.tar.zst",
            "rpm": f"caelum-{value}-1.fedora43.x86_64.rpm",
        }[kind]
        for target, (kind, _) in TARGETS.items()
    }


def source_identity():
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=ROOT, check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if os.environ.get("GITHUB_SHA", sha) != sha:
        raise ValueError("Checkout differs from the candidate workflow commit")
    return {
        "sha": sha,
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        "version": version(),
    }


def record(directory, target):
    metadata = {
        **source_identity(),
        "target": target,
        "package": package_names(version())[target],
        "python": subprocess.check_output(["python3", "--version"], text=True).strip(),
        "rust": subprocess.check_output(["rustc", "--version"], text=True).strip(),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "locks": {
            name: digest(ROOT / name)["sha256"]
            for name in ("uv.lock", "package-lock.json", "src-tauri/Cargo.lock")
        },
        "checks": ["package-install", "backend-ipc", "simulated-audio", "native-react-bootstrap"],
    }
    metadata["asset"] = digest(directory / metadata["package"])
    (directory / f"build-info-{target}.json").write_text(
        json.dumps(metadata, sort_keys=True, indent=2) + "\n"
    )


def assemble(directory):
    identity = source_identity()
    names = set(package_names(identity["version"]).values()) | {
        f"build-info-{target}.json" for target in TARGETS
    }
    if {path.name for path in directory.iterdir()} != names:
        raise ValueError("Candidate requires exactly all five packages and provenance files")
    manifest = {
        "schema": 1,
        **identity,
        "created": int(time.time()),
        "files": {name: digest(directory / name) for name in sorted(names)},
    }
    (directory / "candidate.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    verify(directory, identity["sha"], identity["run_id"], identity["run_attempt"])


def verify(directory, sha, run_id=None, run_attempt=None, now=None):
    manifest_path = directory / "candidate.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 65536:
        raise ValueError("Invalid candidate manifest")
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("schema") != 1
        or manifest.get("sha") != sha
        or not re.fullmatch(r"[a-f0-9]{40}", sha)
    ):
        raise ValueError("Candidate source identity mismatch")
    if manifest["version"] != version():
        raise ValueError("Candidate version differs from checkout")
    if run_id is not None and manifest["run_id"] != str(run_id):
        raise ValueError("Candidate workflow run mismatch")
    if run_attempt is not None and manifest["run_attempt"] != str(run_attempt):
        raise ValueError("Candidate workflow attempt mismatch")
    now = int(time.time()) if now is None else now
    if type(manifest.get("created")) is not int or not 0 <= now - manifest["created"] <= 7 * 86400:
        raise ValueError("Candidate is expired or dated in the future; build a fresh candidate")
    names = package_names(manifest["version"])
    expected = set(names.values()) | {f"build-info-{target}.json" for target in TARGETS}
    if set(manifest["files"]) != expected:
        raise ValueError("Incomplete or unexpected candidate asset set")
    # Only final publication metadata may be present beside the candidate files.
    if (
        {path.name for path in directory.iterdir()}
        - expected
        - {
            "candidate.json",
            "update.json",
            "update.json.sig",
            "update-signatures.json",
            "SHA256SUMS",
        }
    ):
        raise ValueError("Unexpected files in candidate directory")
    for name, info in manifest["files"].items():
        if digest(directory / name) != info:
            raise ValueError(f"Candidate checksum mismatch: {name}")
    for target, name in names.items():
        info = json.loads((directory / f"build-info-{target}.json").read_text())
        for key in ("sha", "version", "run_id", "run_attempt"):
            if info[key] != manifest[key]:
                raise ValueError("Mixed candidate provenance")
        if (
            info["target"] != target
            or info["package"] != name
            or info["asset"] != manifest["files"][name]
        ):
            raise ValueError("Package provenance mismatch")
        for lock in ("uv.lock", "package-lock.json", "src-tauri/Cargo.lock"):
            if info["locks"][lock] != digest(ROOT / lock)["sha256"]:
                raise ValueError("Candidate lockfile mismatch")
        if set(info["checks"]) != {
            "package-install",
            "backend-ipc",
            "simulated-audio",
            "native-react-bootstrap",
        }:
            raise ValueError("Candidate checks are incomplete")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record", "assemble", "verify"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("target", nargs="?", choices=TARGETS)
    args = parser.parse_args()
    if args.command == "record":
        if args.target is None:
            parser.error("record requires a target")
        record(args.directory, args.target)
    elif args.command == "assemble":
        assemble(args.directory)
    else:
        verify(args.directory, source_identity()["sha"])
