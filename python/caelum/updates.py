"""Signed native-package updates; no network or privileged work at import time."""

import base64
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path

REPOSITORY = "Parth-Jadhav-2004/caelum"
RELEASES = f"https://github.com/{REPOSITORY}/releases"
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


def installed():
    try:
        info = json.loads((BASE / "release.json").read_text())
        version_tuple(info["version"])
        if info["target"] not in TARGETS or BASE != Path("/opt/caelum/lib/caelum"):
            return None
        if not (BASE / "update-public.pem").is_file():
            return None
        return info
    except (OSError, ValueError, KeyError, TypeError):
        return None


def cache_dir():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "caelum/updates"


def compatible(info):
    distro, release, _ = TARGETS[info["target"]]
    current = platform.freedesktop_os_release()
    return (
        platform.machine() == "x86_64"
        and (current.get("ID") == distro or distro == "arch" and current.get("ID") == "omarchy")
        and (release is None or current.get("VERSION_ID") == release)
        and info["python"]
        == platform.python_version_tuple()[0] + "." + platform.python_version_tuple()[1]
    )


def trusted_public_keys(directory, *, now=None):
    """Trust is installed with the package, never supplied by a download or XDG file.

    Legacy installations without a bundle retain their original pinned key.
    An installed policy is authoritative: malformed/expired policies fail closed.
    """
    directory = Path(directory)
    policy = directory / "update-trust.json"
    if not policy.exists() and not policy.is_symlink():
        return [read_regular(directory / "update-public.pem", 4096)]
    bundle = json.loads(read_regular(policy, 32768))
    if (
        bundle.get("schema") != 1
        or not isinstance(bundle.get("keys"), list)
        or not 1 <= len(bundle["keys"]) <= 4
    ):
        raise ValueError("Invalid installed update trust policy")
    now = int(time.time()) if now is None else now
    keys, seen = [], set()
    for entry in bundle["keys"]:
        if not isinstance(entry, dict) or set(entry) != {
            "id",
            "pem",
            "not_before",
            "not_after",
            "revoked",
        }:
            raise ValueError("Invalid update key record")
        if (
            not isinstance(entry["pem"], str)
            or len(entry["pem"]) > 4096
            or type(entry["revoked"]) is not bool
        ):
            raise ValueError("Invalid update key")
        if (
            any(type(entry[field]) is not int for field in ("not_before", "not_after"))
            or not 0 <= entry["not_before"] < entry["not_after"]
        ):
            raise ValueError("Invalid update key validity")
        der = subprocess.check_output(
            ["/usr/bin/openssl", "pkey", "-pubin", "-outform", "DER"],
            input=entry["pem"].encode(),
            stderr=subprocess.DEVNULL,
            env=SAFE_ENV,
            timeout=2,
        )
        identifier = hashlib.sha256(der).hexdigest()
        if (
            len(der) != 44
            or not der.startswith(bytes.fromhex("302a300506032b6570032100"))
            or entry["id"] != identifier
            or identifier in seen
        ):
            raise ValueError("Update key identity mismatch")
        seen.add(identifier)
        if not entry["revoked"] and entry["not_before"] <= now < entry["not_after"]:
            keys.append(entry["pem"].encode())
    if not keys:
        raise ValueError("No active update verification keys; use a trusted native package")
    return keys


def public_key_id(public):
    der = subprocess.check_output(
        ["/usr/bin/openssl", "pkey", "-pubin", "-outform", "DER"],
        input=public,
        stderr=subprocess.DEVNULL,
        env=SAFE_ENV,
        timeout=2,
    )
    if len(der) != 44 or not der.startswith(bytes.fromhex("302a300506032b6570032100")):
        raise ValueError("An Ed25519 update key is required")
    return hashlib.sha256(der).hexdigest()


def signature_candidates(signature):
    if len(signature) == 64:
        return {None: signature}
    try:
        bundle = json.loads(signature)
        entries = bundle["signatures"]
        if bundle["schema"] != 1 or not isinstance(entries, list) or not 1 <= len(entries) <= 4:
            raise ValueError()
        result = {}
        for entry in entries:
            identifier = entry["key_id"]
            if (
                not isinstance(identifier, str)
                or not re.fullmatch(r"[0-9a-f]{64}", identifier)
                or identifier in result
            ):
                raise ValueError()
            raw = base64.b64decode(entry["signature"], validate=True)
            if len(raw) != 64:
                raise ValueError()
            result[identifier] = raw
        return result
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("Invalid update signature bundle") from error


def verify_manifest(raw, signature, info, *, key=None, now=None):
    if len(raw) > 65536 or not 0 < len(signature) <= 4096:
        raise ValueError("Invalid update signature or metadata size")
    with tempfile.TemporaryDirectory(prefix="caelum-verify-", dir="/tmp") as directory:
        work = Path(directory)
        (work / "manifest").write_bytes(raw)
        signatures = signature_candidates(signature)
        keys = [read_regular(Path(key), 4096)] if key else trusted_public_keys(BASE, now=now)
        verified = False
        for public in keys:
            matching = (
                signatures.get(None)
                if None in signatures
                else signatures.get(public_key_id(public))
            )
            if matching is None:
                continue
            (work / "signature").write_bytes(matching)
            (work / "public.pem").write_bytes(public)
            result = subprocess.run(
                [
                    "/usr/bin/openssl",
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(work / "public.pem"),
                    "-rawin",
                    "-in",
                    str(work / "manifest"),
                    "-sigfile",
                    str(work / "signature"),
                ],
                capture_output=True,
                env=SAFE_ENV,
                timeout=2,
            )
            if result.returncode == 0:
                verified = True
                break
        if not verified:
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


def fetch(client, url, maximum, output=None):
    size = 0
    chunks = []
    with client.stream("GET", url) as response:
        response.raise_for_status()
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise ValueError("Compressed update responses are not supported")
        if response.url.scheme != "https" or any(
            item.url.scheme != "https" for item in response.history
        ):
            raise ValueError("Updates require HTTPS")
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > maximum:
                raise ValueError("Update download exceeds its size limit")
            if output is None:
                chunks.append(chunk)
            else:
                output.write(chunk)
    return b"".join(chunks)


def require_https(request):
    if request.url.scheme != "https":
        raise ValueError("Updates require HTTPS")


def network_client(timeout):
    import httpx

    return httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        trust_env=False,
        headers={"Accept-Encoding": "identity"},
        event_hooks={"request": [require_https]},
    )


def check():
    info = installed()
    if not info or not compatible(info):
        raise RuntimeError("Use your package manager for updates to this installation")
    import httpx

    try:
        with network_client(30) as client:
            root = RELEASES + "/latest/download/"
            raw = fetch(client, root + "update.json", 65536)
            signature = fetch(client, root + "update.json.sig", 64)
            if (BASE / "update-trust.json").exists():
                try:
                    signature = fetch(client, root + "update-signatures.json", 4096)
                except httpx.HTTPStatusError as error:
                    if error.response.status_code != 404:
                        raise
        manifest, _ = verify_manifest(raw, signature, info)
    except httpx.HTTPError as error:
        raise RuntimeError(
            "Could not check updates. Check your connection and try again."
        ) from error
    if version_tuple(manifest["version"]) <= version_tuple(info["version"]):
        return None
    return {"version": manifest["version"], "raw": raw, "signature": signature}


def stage(update):
    info = installed()
    if not info or not compatible(info):
        raise RuntimeError("This installation must be updated using its package manager")
    manifest, asset = verify_manifest(update["raw"], update["signature"], info)
    if version_tuple(manifest["version"]) <= version_tuple(info["version"]):
        raise ValueError("Refusing an older or already installed update")
    import httpx

    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending = root / "pending"
    if pending.exists():
        raise RuntimeError("An update is already queued; restart Caelum to install it")
    with tempfile.TemporaryDirectory(prefix="download-", dir=root) as directory:
        work = Path(directory)
        try:
            with network_client(120) as client:
                with (work / asset["name"]).open("wb") as output:
                    fetch(
                        client,
                        RELEASES + f"/download/v{manifest['version']}/" + asset["name"],
                        asset["size"],
                        output,
                    )
        except httpx.HTTPError as error:
            raise RuntimeError("Download failed; no update was queued. Try again.") from error
        verify_package(work / asset["name"], asset)
        (work / "update.json").write_bytes(update["raw"])
        (work / "update.json.sig").write_bytes(update["signature"])
        ready = work / "ready"
        ready.mkdir(mode=0o700)
        for path in list(work.iterdir()):
            if path != ready:
                path.rename(ready / path.name)
        ready.rename(pending)
    return manifest["version"]


def verify_package(path, asset):
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    if path.stat().st_size != asset["size"] or checksum != asset["sha256"]:
        raise ValueError("Update package is corrupt; nothing was installed")


def read_regular(path, maximum):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("Update files must be regular files")
        data = source.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("Update file exceeds its size limit")
        return data


def install_verified(pending):
    """Privileged entry point: trust installed code/key, never caller-supplied commands."""
    info = installed()
    if os.geteuid() != 0 or not info or not compatible(info):
        raise RuntimeError("Updates require the official matching native package")
    raw = read_regular(pending / "update.json", 65536)
    signature = read_regular(pending / "update.json.sig", 4096)
    manifest, asset = verify_manifest(raw, signature, info)
    if version_tuple(manifest["version"]) <= version_tuple(info["version"]):
        raise ValueError("Refusing to downgrade or reinstall Caelum")
    with tempfile.TemporaryDirectory(prefix="caelum-install-", dir="/tmp") as directory:
        package = Path(directory) / asset["name"]
        descriptor = os.open(pending / asset["name"], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source, package.open("wb") as output:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("Update package must be a regular file")
            remaining = asset["size"] + 1
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                output.write(chunk)
                remaining -= len(chunk)
        verify_package(package, asset)
        suffix = TARGETS[info["target"]][2]
        command = {
            ".deb": ["/usr/bin/apt-get", "install", "-y", "--", str(package)],
            ".rpm": ["/usr/bin/dnf", "install", "-y", "--", str(package)],
            ".pkg.tar.zst": ["/usr/bin/pacman", "-U", "--noconfirm", "--", str(package)],
        }[suffix]
        subprocess.run(command, check=True, env=SAFE_ENV, cwd="/")


def apply_pending():
    info = installed()
    pending = cache_dir() / "pending"
    if not info or not pending.is_dir():
        return False
    if not compatible(info):
        raise RuntimeError("Use your package manager after changing OS or Python versions")
    manifest, asset = verify_manifest(
        read_regular(pending / "update.json", 65536),
        read_regular(pending / "update.json.sig", 4096),
        info,
    )
    if version_tuple(manifest["version"]) <= version_tuple(info["version"]):
        discard_pending()
        return False
    verify_package(pending / asset["name"], asset)
    subprocess.run(
        [
            "/usr/bin/pkexec",
            "/usr/bin/python3",
            "-I",
            str(BASE / "updates.py"),
            str(pending),
        ],
        check=True,
    )
    shutil.rmtree(pending)
    return True


def discard_pending():
    pending = cache_dir() / "pending"
    if pending.exists():
        shutil.rmtree(pending)


if __name__ == "__main__":
    import sys

    try:
        if len(sys.argv) != 2:
            raise ValueError("Expected a staged update directory")
        install_verified(Path(sys.argv[1]).resolve(strict=True))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        sys.exit(
            "Caelum update failed verification or installation; the pending update was retained."
        )
