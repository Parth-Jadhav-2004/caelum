#!/usr/bin/env python3
"""Edit installed trust policy in source; never generate or rotate production secrets."""

import argparse
import importlib.util
import json
import os
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("update_verifier", ROOT / "python/caelum/updates.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def edit(policy, command, value, not_before=0, not_after=4102444800):
    bundle = json.loads(policy.read_text())
    if command == "add":
        public = Path(value).read_bytes()
        identifier = verifier.public_key_id(public)
        if any(entry["id"] == identifier for entry in bundle["keys"]):
            raise ValueError("Public key is already present")
        bundle["keys"].append(
            {
                "id": identifier,
                "pem": public.decode(),
                "not_before": not_before,
                "not_after": not_after,
                "revoked": False,
            }
        )
    else:
        entry = next((entry for entry in bundle["keys"] if entry["id"] == value), None)
        if entry is None:
            raise ValueError("Unknown public-key fingerprint")
        entry["revoked"] = True
    with tempfile.TemporaryDirectory(prefix="caelum-trust-check-") as directory:
        (Path(directory) / "update-trust.json").write_text(json.dumps(bundle))
        verifier.trusted_public_keys(Path(directory))
    descriptor, temporary = tempfile.mkstemp(prefix=".update-trust-", dir=policy.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(bundle, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, policy)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("add", "revoke"))
    parser.add_argument("value", help="Public PEM path for add, SHA-256 DER fingerprint for revoke")
    parser.add_argument("--policy", type=Path, default=ROOT / "python/caelum/update-trust.json")
    parser.add_argument("--not-before", type=int, default=int(time.time()))
    parser.add_argument("--not-after", type=int, default=4102444800)
    args = parser.parse_args()
    edit(args.policy, args.command, args.value, args.not_before, args.not_after)
