#!/usr/bin/env python3
"""Fail closed on private runtime files and recognizable secrets; never print values.

With no paths, scan tracked repository files. Directory arguments scan extracted
package payloads (the package builder also checks its staging tree).
"""

import argparse
import re
import subprocess
from pathlib import Path

SECRET = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
    rb"|\bgsk_[A-Za-z0-9]{40,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b"
    rb"|\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b"
    rb"|\bAKIA[A-Z0-9]{16}\b"
)
PRIVATE_SUFFIXES = {
    ".wav",
    ".mp3",
    ".ogg",
    ".flac",
    ".m4a",
    ".pcm",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".jsonl",
    ".key",
}
PRIVATE_NAMES = {"environment", "credentials.json", "onboarding.json", "config.toml", ".env"}


def scan(paths):
    issues = []
    for path in paths:
        path = Path(path)
        name = path.name.lower()
        if (
            path.suffix.lower() in PRIVATE_SUFFIXES
            or name in PRIVATE_NAMES
            or name.startswith(".env.")
            and name != ".env.example"
            or name.endswith(("-wal", "-shm"))
        ):
            issues.append((str(path), "private runtime file"))
        if path.is_file() and not path.is_symlink() and SECRET.search(path.read_bytes()):
            issues.append((str(path), "possible secret"))
    return issues


def check(paths):
    issues = scan(paths)
    if issues:
        # Paths only: matched secrets and file contents must never reach CI logs.
        raise ValueError("Privacy scan failed: " + "; ".join(f"{p}: {why}" for p, why in issues))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    if args.paths:
        paths = [
            file for root in args.paths for file in (root.rglob("*") if root.is_dir() else [root])
        ]
    else:
        paths = [
            Path(p)
            for p in subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
            if p
        ]
    check(paths)
    print("Privacy scan passed (private filenames and recognizable credential patterns).")


if __name__ == "__main__":
    main()
