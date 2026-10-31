"""Owner-only credential metadata; secrets go to Secret Service where available."""

import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from .config import config_path


def _path():
    return config_path().with_name("credentials.json")


def _read():
    path = _path()
    if not path.exists():
        return {}
    if (
        path.is_symlink()
        or path.stat().st_uid != os.getuid()
        or stat.S_IMODE(path.stat().st_mode) != 0o600
    ):
        raise RuntimeError("Credential file must be owned by you with mode 600")
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or any(
            not isinstance(record, dict)
            or record.get("storage") not in ("file", "keyring", "deleted")
            or (record.get("storage") == "file" and not isinstance(record.get("value"), str))
            for record in data.values()
        ):
            raise ValueError("Invalid credential metadata")
        return data
    except (ValueError, OSError):
        raise RuntimeError("Could not read saved credentials") from None


def _write(data):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".credentials-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _secret(action, name, value=None):
    args = ["secret-tool", action]
    if action == "store":
        args.append("--label=Caelum provider key")
    args.extend(["application", "caelum", "credential", name])
    try:
        return subprocess.run(
            args,
            input=value,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def get(name):
    record = _read().get(name)
    if record:
        if record["storage"] == "deleted":
            return None
        if record["storage"] == "file":
            return record["value"]
        result = _secret("lookup", name)
        return result.stdout.strip() if result and result.returncode == 0 else None
    return os.environ.get(name)


def store(name, value):
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
        raise ValueError("Credential name must be an uppercase environment variable")
    if not value or any(char.isspace() for char in value):
        raise ValueError("Enter a nonempty key without spaces or line breaks")
    data = _read()
    result = _secret("store", name, value)
    storage = "keyring" if result and result.returncode == 0 else "file"
    old_keyring = data.get(name, {}).get("storage") == "keyring" or data.get(name, {}).get(
        "keyring_copy", False
    )
    data[name] = {"storage": storage}
    if storage == "file" and old_keyring:
        data[name]["keyring_copy"] = True
    if storage == "file":
        data[name]["value"] = value
    _write(data)
    return storage


def delete(name):
    data = _read()
    result = _secret("clear", name)
    if (
        data.get(name, {}).get("storage") == "keyring" or data.get(name, {}).get("keyring_copy")
    ) and (not result or result.returncode != 0):
        raise RuntimeError("Unlock your desktop keyring and try deleting the key again")
    # A tombstone prevents a legacy environment key from silently returning.
    data[name] = {"storage": "deleted"}
    _write(data)
    os.environ.pop(name, None)


def describe(name):
    try:
        record = _read().get(name, {})
        storage = record.get("storage")
        if storage == "keyring":
            return "key saved in desktop keyring"
        if storage == "file":
            return "key saved in private file (not encrypted)"
        if storage == "deleted":
            return "key missing; open setup to add a key"
        return (
            "key present in environment"
            if os.environ.get(name)
            else "key missing; open setup to add a key"
        )
    except RuntimeError:
        return "saved key unavailable; check credential file permissions"
