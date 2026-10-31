"""Signed native-package updates; no network or privileged work at import time."""

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
    "ubuntu-26.04": ("ubuntu", "26.04", ".deb"),
    "debian-12": ("debian", "12", ".deb"),
    "debian-13": ("debian", "13", ".deb"),
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
    signature = read_regular(pending / "update.json.sig", 64)
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
        read_regular(pending / "update.json.sig", 64),
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
