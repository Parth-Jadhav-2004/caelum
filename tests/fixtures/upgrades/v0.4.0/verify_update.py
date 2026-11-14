"""Frozen v0.4.0 updater verification logic for backwards-compatibility tests."""

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent

MAX_PACKAGE = 512 * 1024 * 1024

TARGETS = {
    "ubuntu-24.04": ("ubuntu", "24.04", ".deb"),
    "debian-12": ("debian", "12", ".deb"),
    "ubuntu-26.04": ("ubuntu", "26.04", ".deb"),
    "arch": ("arch", None, ".pkg.tar.zst"),
    "fedora-43": ("fedora", "43", ".rpm"),
}

SAFE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value
    ):
        raise ValueError("Updates require a stable major.minor.patch version")
    return tuple(map(int, value.split(".")))


def verify_manifest(raw, signature, info, *, key=None, now=None):
    if len(raw) > 65536 or len(signature) != 64:
        raise ValueError("Invalid update signature or metadata size")
    with tempfile.TemporaryDirectory(prefix="caelum-verify-", dir="/tmp") as directory:
        work = Path(directory)
        (work / "manifest").write_bytes(raw)
        (work / "signature").write_bytes(signature)
        result = subprocess.run(
            [
                "/usr/bin/openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(key or BASE / "update-public.pem"),
                "-rawin",
                "-in",
                str(work / "manifest"),
                "-sigfile",
                str(work / "signature"),
            ],
            capture_output=True,
            env=SAFE_ENV,
            timeout=10,
        )
        if result.returncode:
            raise ValueError("Update signature verification failed; nothing was installed")
    manifest = json.loads(raw)
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported update manifest")
    version_tuple(manifest["version"])
    current_time = time.time() if now is None else now
    issued, expires = manifest["issued"], manifest["expires"]
    if not all(type(value) is int for value in (issued, expires)) or not (
        issued - 86400 <= current_time < expires <= issued + 90 * 86400
    ):
        raise ValueError("Update metadata expired or is not yet valid; check your clock")
    asset = manifest["assets"][info["target"]]
    name = asset["name"]
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"caelum[-_][a-zA-Z0-9._-]+", name)
        or not name.endswith(TARGETS[info["target"]][2])
        or type(asset["size"]) is not int
        or not 0 < asset["size"] <= MAX_PACKAGE
        or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
    ):
        raise ValueError("Invalid update package metadata")
    return manifest, asset
