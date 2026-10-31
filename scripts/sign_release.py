#!/usr/bin/env python3
"""Create and sign bounded, expiring native update metadata for a stable release."""

import argparse
import hashlib
import json
import re
import subprocess
import time
import tomllib
from pathlib import Path

from build_package import ROOT, TARGETS


def sign(directory, private_key, now=None):
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("Only stable major.minor.patch releases can be published")
    public_key = ROOT / "src/caelum/update-public.pem"
    encoded = subprocess.check_output(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-outform", "DER"],
    )
    if len(encoded) != 44 or not encoded.startswith(bytes.fromhex("302a300506032b6570032100")):
        raise ValueError("An Ed25519 signing key is required")
    derived = subprocess.check_output(
        ["openssl", "pkey", "-in", str(private_key), "-pubout"],
    )
    if derived.strip() != public_key.read_bytes().strip():
        raise ValueError("Signing key does not match the public key shipped in Caelum")
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
    signature = directory / "update.json.sig"
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private_key),
            "-rawin",
            "-in",
            str(manifest),
            "-out",
            str(signature),
        ],
        check=True,
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
            str(signature),
        ],
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("private_key", type=Path)
    args = parser.parse_args()
    sign(args.directory, args.private_key)
