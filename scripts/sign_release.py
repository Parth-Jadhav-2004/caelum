#!/usr/bin/env python3
"""Create and sign bounded, expiring native update metadata for a stable release."""

import argparse
import base64
import hashlib
import importlib.util
import json
import re
import subprocess
import time
import tomllib
from pathlib import Path

from build_package import ROOT, TARGETS


def sign(directory, private_key, now=None, legacy_private_key=None):
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("Only stable major.minor.patch releases can be published")
    public_key = ROOT / "python/caelum/update-public.pem"
    encoded = subprocess.check_output(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-outform", "DER"],
    )
    if len(encoded) != 44 or not encoded.startswith(bytes.fromhex("302a300506032b6570032100")):
        raise ValueError("An Ed25519 signing key is required")
    derived = subprocess.check_output(
        ["openssl", "pkey", "-in", str(private_key), "-pubout"],
    )
    spec = importlib.util.spec_from_file_location(
        "caelum_trust", Path(__file__).resolve().parents[1] / "python/caelum/updates.py"
    )
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    trusted = verifier.trusted_public_keys(ROOT / "python/caelum")
    if not any(derived.strip() == value.strip() for value in trusted):
        raise ValueError("Signing key does not match an active public key shipped in Caelum")
    legacy = derived
    if legacy_private_key:
        legacy = subprocess.check_output(
            ["openssl", "pkey", "-in", str(legacy_private_key), "-pubout"]
        )
    if legacy.strip() != public_key.read_bytes().strip():
        raise ValueError(
            "Rotation requires the legacy signing key to preserve older updater compatibility"
        )
    assets = {}
    for target, (kind, _) in TARGETS.items():
        name = {
            "deb": f"caelum_{version}-1_{target}_amd64.deb",
            "arch": f"caelum-{version}-1-x86_64.pkg.tar.zst",
            "rpm": f"caelum-{version}-1.fedora43.x86_64.rpm",
        }[kind]
        path = directory / name
        if not 0 < path.stat().st_size <= 512 * 1024 * 1024:
            raise ValueError(f"Invalid package size: {name}")
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        assets[target] = {"name": name, "sha256": checksum, "size": path.stat().st_size}
    issued = int(time.time()) if now is None else now
    manifest = directory / "update.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "version": version,
                "issued": issued,
                "expires": issued + 90 * 86400,
                "assets": assets,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    entries = []
    for signing_key, public in [(private_key, derived)] + (
        [(legacy_private_key, legacy)] if legacy_private_key else []
    ):
        signature = directory / "update.json.sig"
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(signing_key),
                "-rawin",
                "-in",
                str(manifest),
                "-out",
                str(signature),
            ],
            check=True,
        )
        identifier = verifier.public_key_id(public)
        if not any(item["key_id"] == identifier for item in entries):
            entries.append(
                {
                    "key_id": identifier,
                    "signature": base64.b64encode(signature.read_bytes()).decode(),
                }
            )
    # The last raw signature is always from the original key for 0.4.0 clients.
    bundle = directory / "update-signatures.json"
    bundle.write_text(
        json.dumps({"schema": 1, "signatures": entries}, sort_keys=True, separators=(",", ":"))
    )
    verifier.BASE = ROOT / "python/caelum"
    verifier.verify_manifest(
        manifest.read_bytes(), bundle.read_bytes(), {"target": next(iter(TARGETS))}, now=issued
    )
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-rawin",
            "-in",
            str(manifest),
            "-sigfile",
            str(directory / "update.json.sig"),
        ],
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("private_key", type=Path)
    parser.add_argument("--legacy-key", type=Path)
    args = parser.parse_args()
    sign(args.directory, args.private_key, legacy_private_key=args.legacy_key)
