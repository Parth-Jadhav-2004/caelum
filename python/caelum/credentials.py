"""Provider credentials in the OS key store, with platform-specific file fallbacks."""

import base64
import json
import os
import re
import stat
import subprocess
import tempfile
from contextlib import nullcontext
from pathlib import Path
from threading import Lock

from .config import config_path

_WINDOWS = os.name == "nt"
# Reads may upgrade legacy records; serialize these with sidecar worker writes.
_lock = Lock() if _WINDOWS else nullcontext()
_CRYPTPROTECT_UI_FORBIDDEN = 1


class _MigrationError(RuntimeError):
    pass


def _dpapi():
    try:
        import pywintypes
        import win32crypt

        return win32crypt, pywintypes.error
    except ImportError:
        raise RuntimeError("Windows data protection is unavailable") from None


def _protect(value):
    crypt, api_error = _dpapi()
    try:
        # Current user (no LOCAL_MACHINE flag); never prompt from the sidecar.
        blob = crypt.CryptProtectData(value.encode(), Flags=_CRYPTPROTECT_UI_FORBIDDEN)
        return base64.b64encode(blob).decode("ascii")
    except (api_error, ValueError):
        raise RuntimeError("Windows could not protect the key for this user; key not saved") from None


def _unprotect(value):
    crypt, api_error = _dpapi()
    try:
        blob = base64.b64decode(value, validate=True)
        return crypt.CryptUnprotectData(blob, Flags=_CRYPTPROTECT_UI_FORBIDDEN)[1].decode()
    except (api_error, ValueError):
        raise RuntimeError("Cannot unlock the saved key; use the original Windows account or replace the key") from None


def _path():
    return config_path().with_name("credentials.json")


def _read():
    path = _path()
    if not path.exists():
        return {}
    if (
        path.is_symlink()
        or os.name != "nt" and (
            path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o600
        )
    ):
        raise RuntimeError("Credential file must be owned by you with mode 600")
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or any(
            not isinstance(record, dict)
            or record.get("storage") not in ("file", "dpapi", "keyring", "deleted")
            or (record.get("storage") in ("file", "dpapi") and not isinstance(record.get("value"), str))
            for record in data.values()
        ):
            raise ValueError("Invalid credential metadata")
    except (ValueError, OSError):
        raise RuntimeError("Could not read saved credentials") from None
    return data


def _read_protected():
    with _lock:
        data = _read()
        if _WINDOWS and any(r["storage"] == "file" for r in data.values()):
            try:
                _write(data)
            except (RuntimeError, OSError):
                raise _MigrationError(
                    "Older key file is still unencrypted; restore Windows data protection "
                    "and write access to the credential file, then retry"
                ) from None
        return data


def _write(data):
    if _WINDOWS:
        # Upgrade *all* old file records before opening even the temporary file.
        for record in data.values():
            if record["storage"] == "file":
                record.update(storage="dpapi", value=_protect(record["value"]))
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
    if _WINDOWS:
        try:
            import pywintypes
            import win32cred
        except ImportError:
            if action == "lookup":
                raise RuntimeError("Windows Credential Manager is unavailable") from None
            return None

        target = f"Caelum/{name}"
        output = ""
        try:
            if action == "store":
                win32cred.CredWrite({"Type": win32cred.CRED_TYPE_GENERIC, "TargetName": target,
                                     # pywin32's CredWrite takes text and encodes it;
                                     # CredRead returns the native UTF-16LE bytes.
                                     "CredentialBlob": value,
                                     "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE}, 0)
            elif action == "lookup":
                output = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)["CredentialBlob"].decode("utf-16-le")
            else:
                win32cred.CredDelete(target, win32cred.CRED_TYPE_GENERIC)
        except pywintypes.error as exc:
            if action == "store" or (action == "clear" and exc.winerror != 1168):
                return None
            if exc.winerror != 1168:
                raise RuntimeError("Windows Credential Manager is unavailable") from None
            if action == "lookup":
                return None
        return subprocess.CompletedProcess([], 0, output)
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
    record = _read_protected().get(name)
    if record:
        if record["storage"] == "deleted":
            return None
        if record["storage"] == "file":
            return record["value"]
        if record["storage"] == "dpapi":
            return _unprotect(record["value"])
        result = _secret("lookup", name)
        return result.stdout.strip() if result and result.returncode == 0 else None
    return os.environ.get(name)


def store(name, value):
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
        raise ValueError("Credential name must be an uppercase environment variable")
    if not value or any(char.isspace() for char in value):
        raise ValueError("Enter a nonempty key without spaces or line breaks")
    with _lock:
        return _store(name, value)


def _store(name, value):
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
    return data[name]["storage"]


def delete(name):
    with _lock:
        _delete(name)


def _delete(name):
    data = _read()
    result = _secret("clear", name)
    if (
        data.get(name, {}).get("storage") == "keyring" or data.get(name, {}).get("keyring_copy")
    ) and (not result or result.returncode != 0):
        if _WINDOWS:
            raise RuntimeError("Restore access to Windows Credential Manager and try deleting the key again")
        raise RuntimeError("Unlock your desktop keyring and try deleting the key again")
    # A tombstone prevents a legacy environment key from silently returning.
    data[name] = {"storage": "deleted"}
    _write(data)
    os.environ.pop(name, None)


def describe(name):
    try:
        record = _read_protected().get(name, {})
        storage = record.get("storage")
        if storage == "keyring":
            description = "key saved in Windows Credential Manager" if _WINDOWS else "key saved in desktop keyring"
        elif storage == "dpapi":
            description = "key encrypted for your Windows account (DPAPI)"
        elif storage == "file":
            description = "key saved in private file (not encrypted)"
        elif storage == "deleted":
            description = "key missing; open setup to add a key"
        elif os.environ.get(name):
            storage = "environment"
            description = "key present in environment"
        else:
            storage = "missing"
            description = "key missing; open setup to add a key"
        return {"description": description, "storage": storage}
    except _MigrationError as exc:
        return {"description": str(exc), "storage": "unavailable"}
    except (OSError, RuntimeError):
        return {
            "description": (
                "saved key unavailable; check Windows credential protection and file permissions"
                if _WINDOWS else "saved key unavailable; check credential file permissions"
            ),
            "storage": "unavailable",
        }
