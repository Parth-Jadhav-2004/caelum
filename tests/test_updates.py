import asyncio
import hashlib
import importlib
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from caelum import updates
from caelum.desktop import install_queued_update
from caelum.service import prepare_update


@pytest.fixture
def release(tmp_path, monkeypatch):
    private = tmp_path / "private.pem"
    public = tmp_path / "update-public.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True
    )
    payload = b"test native package payload"
    now = int(time.time())
    asset = {
        "name": "caelum_0.3.0-1_ubuntu-24.04_amd64.deb",
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    manifest = {
        "schema": 1,
        "version": "0.3.0",
        "issued": now,
        "expires": now + 86400,
        "assets": {"ubuntu-24.04": asset},
    }
    info = {"version": "0.2.0", "target": "ubuntu-24.04", "python": "3.12"}
    monkeypatch.setattr(updates, "BASE", tmp_path)
    monkeypatch.setattr(updates, "installed", lambda: info)
    monkeypatch.setattr(updates, "compatible", lambda _: True)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    def signed(value=None):
        raw = json.dumps(manifest if value is None else value).encode()
        source = tmp_path / "sign-input"
        source.write_bytes(raw)
        signature = tmp_path / "sign-output"
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private),
                "-rawin",
                "-in",
                str(source),
                "-out",
                str(signature),
            ],
            check=True,
        )
        return {"version": "0.3.0", "raw": raw, "signature": signature.read_bytes()}

    return SimpleNamespace(
        private=private,
        public=public,
        payload=payload,
        manifest=manifest,
        asset=asset,
        info=info,
        signed=signed,
        now=now,
    )


def serve(monkeypatch, handler):
    client = httpx.Client

    def make_client(**kwargs):
        return client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", make_client)


def endpoint(release, update, *, package=None):
    def respond(request):
        if request.url.path.endswith("update.json.sig"):
            content = update["signature"]
        elif request.url.path.endswith("update.json"):
            content = update["raw"]
        else:
            assert "/download/v0.3.0/" in request.url.path
            content = release.payload if package is None else package
        return httpx.Response(200, content=content)

    return respond


def test_check_download_stage_and_discard(release, monkeypatch):
    update = release.signed()
    serve(monkeypatch, endpoint(release, update))
    found = updates.check()
    assert found == update
    assert not (updates.cache_dir() / "pending").exists()
    assert updates.stage(found) == "0.3.0"
    pending = updates.cache_dir() / "pending"
    assert (pending / release.asset["name"]).read_bytes() == release.payload
    assert (pending / "update.json").read_bytes() == update["raw"]
    assert pending.stat().st_mode & 0o777 == 0o700
    with pytest.raises(RuntimeError, match="already queued"):
        updates.stage(found)
    updates.discard_pending()
    assert not pending.exists()


@pytest.mark.parametrize("version", ["0.2.0", "0.1.9"])
def test_no_downgrades_or_reinstalls(release, monkeypatch, version):
    release.manifest["version"] = version
    update = release.signed()
    serve(monkeypatch, endpoint(release, update))
    assert updates.check() is None
    with pytest.raises(ValueError, match="older or already installed"):
        updates.stage(update)


@pytest.mark.parametrize("mutation", ["metadata", "signature", "missing-signature"])
def test_bad_signatures_rejected_before_download(release, monkeypatch, mutation):
    update = release.signed()
    if mutation == "metadata":
        update["raw"] = update["raw"].replace(b"0.3.0", b"9.3.0")
    else:
        update["signature"] = b"x" * (64 if mutation == "signature" else 0)
    monkeypatch.setattr(updates, "network_client", lambda _: pytest.fail("unverified download"))
    with pytest.raises(ValueError, match="signature"):
        updates.stage(update)


@pytest.mark.parametrize(
    "kind", ["expired", "future", "long-expiry", "path", "size", "hash", "version"]
)
def test_signed_invalid_metadata_is_rejected(release, kind):
    manifest = release.manifest
    if kind == "expired":
        manifest["expires"] = release.now - 1
    elif kind == "future":
        manifest["issued"] = release.now + 2 * 86400
        manifest["expires"] = release.now + 3 * 86400
    elif kind == "long-expiry":
        manifest["expires"] = release.now + 91 * 86400
    elif kind == "path":
        release.asset["name"] = "../../evil.deb"
    elif kind == "size":
        release.asset["size"] = updates.MAX_PACKAGE + 1
    elif kind == "hash":
        release.asset["sha256"] = "not a hash"
    elif kind == "version":
        manifest["version"] = "0.3.0;whoami"
    update = release.signed()
    with pytest.raises(ValueError):
        updates.verify_manifest(update["raw"], update["signature"], release.info)


@pytest.mark.parametrize("payload", [b"modified native package", b"", b"x" * 100])
def test_corrupt_partial_and_oversized_packages_never_queue(release, monkeypatch, payload):
    update = release.signed()
    serve(monkeypatch, endpoint(release, update, package=payload))
    with pytest.raises(ValueError):
        updates.stage(update)
    assert list(updates.cache_dir().iterdir()) == []


def test_network_failure_keeps_app_unchanged(release, monkeypatch):
    update = release.signed()

    def disconnected(request):
        raise httpx.ConnectError("offline", request=request)

    serve(monkeypatch, disconnected)
    with pytest.raises(RuntimeError, match="Could not check updates"):
        updates.check()
    with pytest.raises(RuntimeError, match="Download failed"):
        updates.stage(update)
    assert list(updates.cache_dir().iterdir()) == []


def test_https_redirect_downgrade_is_blocked_before_request(release, monkeypatch):
    seen = []

    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://insecure.invalid/package"})

    serve(monkeypatch, redirect)
    with pytest.raises(ValueError, match="HTTPS"):
        updates.check()
    assert len(seen) == 1


def test_metadata_response_size_is_bounded(release, monkeypatch):
    serve(monkeypatch, lambda _: httpx.Response(200, content=b"x" * 65537))
    with pytest.raises(ValueError, match="size limit"):
        updates.check()


def test_compressed_response_is_rejected(release, monkeypatch):
    serve(
        monkeypatch,
        lambda _: httpx.Response(200, headers={"content-encoding": "identity, gzip"}, content=b""),
    )
    with pytest.raises(ValueError, match="Compressed"):
        updates.check()


def test_source_installation_does_not_enable_privileged_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "BASE", tmp_path)
    (tmp_path / "release.json").write_text(
        json.dumps({"version": "0.2.0", "target": "arch", "python": "3.14"})
    )
    (tmp_path / "update-public.pem").write_text("not a production key")
    assert updates.installed() is None


@pytest.mark.parametrize(
    "distro,release_id,machine,python,expected",
    [
        ("ubuntu", "24.04", "x86_64", ("3", "12", "1"), True),
        ("ubuntu", "26.04", "x86_64", ("3", "12", "1"), False),
        ("linuxmint", "24.04", "x86_64", ("3", "12", "1"), False),
        ("ubuntu", "24.04", "aarch64", ("3", "12", "1"), False),
        ("ubuntu", "24.04", "x86_64", ("3", "14", "1"), False),
    ],
)
def test_target_compatibility(distro, release_id, machine, python, expected, monkeypatch):
    monkeypatch.setattr(
        updates.platform,
        "freedesktop_os_release",
        lambda: {
            "ID": distro,
            "VERSION_ID": release_id,
        },
    )
    monkeypatch.setattr(updates.platform, "machine", lambda: machine)
    monkeypatch.setattr(updates.platform, "python_version_tuple", lambda: python)
    assert updates.compatible({"target": "ubuntu-24.04", "python": "3.12"}) is expected


@pytest.mark.parametrize("python,expected", [("3.14", True), ("3.15", False)])
def test_omarchy_uses_arch_packages_with_matching_python(python, expected, monkeypatch):
    monkeypatch.setattr(
        updates.platform,
        "freedesktop_os_release",
        lambda: {
            "ID": "omarchy",
            "ID_LIKE": "arch",
            "VERSION_ID": "4.0.6",
        },
    )
    monkeypatch.setattr(updates.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(updates.platform, "python_version_tuple", lambda: (*python.split("."), "0"))
    assert updates.compatible({"target": "arch", "python": "3.14"}) is expected


def test_wrong_installation_never_contacts_network(release, monkeypatch):
    monkeypatch.setattr(updates, "compatible", lambda _: False)
    monkeypatch.setattr(updates, "network_client", lambda _: pytest.fail("unexpected network"))
    with pytest.raises(RuntimeError, match="package manager"):
        updates.check()
    with pytest.raises(RuntimeError, match="package manager"):
        updates.stage(release.signed())


def staged(release):
    pending = updates.cache_dir() / "pending"
    pending.mkdir(parents=True)
    update = release.signed()
    (pending / "update.json").write_bytes(update["raw"])
    (pending / "update.json.sig").write_bytes(update["signature"])
    (pending / release.asset["name"]).write_bytes(release.payload)
    return pending


def test_privileged_install_reverifies_and_uses_root_owned_snapshot(release, monkeypatch):
    pending = staged(release)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    original_run = subprocess.run
    commands = []

    def execute(command, **kwargs):
        if command[0] == "/usr/bin/openssl":
            return original_run(command, **kwargs)
        commands.append(command)
        snapshot = Path(command[-1])
        assert snapshot.parent != pending
        assert snapshot.parent.stat().st_mode & 0o777 == 0o700
        (pending / release.asset["name"]).write_bytes(b"changed after verification")
        assert snapshot.read_bytes() == release.payload
        assert kwargs["env"] == updates.SAFE_ENV
        assert kwargs["cwd"] == "/"
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", execute)
    updates.install_verified(pending)
    assert len(commands) == 1
    assert commands[0][:5] == ["/usr/bin/apt-get", "install", "-y", "--", commands[0][-1]]


@pytest.mark.parametrize("tamper", ["package", "manifest", "symlink", "expired", "downgrade"])
def test_tampered_pending_update_cannot_run_package_manager(release, monkeypatch, tamper):
    if tamper == "expired":
        release.manifest["expires"] = release.now - 1
    if tamper == "downgrade":
        release.manifest["version"] = "0.1.0"
    pending = staged(release)
    package = pending / release.asset["name"]
    if tamper == "package":
        package.write_bytes(b"tampered")
    elif tamper == "manifest":
        (pending / "update.json").write_bytes(b"{}")
    elif tamper == "symlink":
        package.unlink()
        source = pending / "other"
        source.write_bytes(release.payload)
        package.symlink_to(source)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    original_run = subprocess.run

    def execute(command, **kwargs):
        assert command[0] == "/usr/bin/openssl", "Package manager must not run"
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises((ValueError, OSError)):
        updates.install_verified(pending)


def test_cancelled_authorization_keeps_pending_update(release, monkeypatch):
    pending = staged(release)
    original_run = subprocess.run

    def cancelled(command, **kwargs):
        if command[0] == "/usr/bin/openssl":
            return original_run(command, **kwargs)
        assert command[:3] == ["/usr/bin/pkexec", "/usr/bin/python3", "-I"]
        raise subprocess.CalledProcessError(126, command)

    monkeypatch.setattr(subprocess, "run", cancelled)
    with pytest.raises(subprocess.CalledProcessError):
        updates.apply_pending()
    assert pending.is_dir()


def test_successful_apply_removes_pending(release, monkeypatch):
    pending = staged(release)
    original_run = subprocess.run

    def execute(command, **kwargs):
        if command[0] == "/usr/bin/openssl":
            return original_run(command, **kwargs)
        assert command[0] == "/usr/bin/pkexec"

    monkeypatch.setattr(subprocess, "run", execute)
    assert updates.apply_pending()
    assert not pending.exists()
    assert not updates.apply_pending()


def test_corrupt_pending_never_requests_authorization(release, monkeypatch):
    pending = staged(release)
    (pending / release.asset["name"]).write_bytes(b"tampered")
    original_run = subprocess.run

    def execute(command, **kwargs):
        assert command[0] == "/usr/bin/openssl", "Do not request authorization for corrupt files"
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(ValueError, match="corrupt"):
        updates.apply_pending()


def test_external_upgrade_clears_obsolete_pending_update(release, monkeypatch):
    pending = staged(release)
    release.info["version"] = "0.3.0"
    assert not updates.apply_pending()
    assert not pending.exists()


@pytest.mark.parametrize(
    "state,pending,capture",
    [
        ("recording", False, True),
        ("processing", False, False),
        ("refining", True, False),
        ("error", True, False),
    ],
)
async def test_busy_dictation_defers_update(state, pending, capture):
    stop = asyncio.Event()
    core = SimpleNamespace(
        control_lock=asyncio.Lock(),
        state=state,
        capture=object() if capture else None,
        work=None,
        pcm=b"audio" if pending else None,
    )
    with pytest.raises(RuntimeError, match="Finish dictation"):
        await prepare_update(core, stop)
    assert not stop.is_set()


async def test_idle_dictation_can_stop_for_update():
    stop = asyncio.Event()
    core = SimpleNamespace(
        control_lock=asyncio.Lock(), state="hidden", capture=None, pcm=None, work=None
    )
    assert await prepare_update(core, stop) == {"ok": True}
    assert stop.is_set()
    assert core.stopping


def test_restart_stops_daemon_before_installing(release, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    calls = []
    monkeypatch.setattr("caelum.desktop.request", lambda action: calls.append(action))
    monkeypatch.setattr(updates, "apply_pending", lambda: calls.append("install"))
    assert install_queued_update()
    assert calls == ["prepare-update", "install"]


def test_restart_leaves_active_dictation_untouched(release, monkeypatch):
    def busy(_):
        raise RuntimeError("Finish dictation")

    monkeypatch.setattr("caelum.desktop.request", busy)
    monkeypatch.setattr(updates, "apply_pending", lambda: pytest.fail("unexpected install"))
    with pytest.raises(RuntimeError, match="Finish dictation"):
        install_queued_update()


def test_release_signing_round_trip(release, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    signer = importlib.import_module("sign_release")
    root = tmp_path / "repo"
    (root / "src/caelum").mkdir(parents=True)
    (root / "src/caelum/update-public.pem").write_bytes(release.public.read_bytes())
    (root / "pyproject.toml").write_text('[project]\nversion="0.3.0"\n')
    monkeypatch.setattr(signer, "ROOT", root)
    assets = tmp_path / "assets"
    assets.mkdir()
    for target, (kind, _) in signer.TARGETS.items():
        name = {
            "deb": f"caelum_0.3.0-1_{target}_amd64.deb",
            "arch": "caelum-0.3.0-1-x86_64.pkg.tar.zst",
            "rpm": "caelum-0.3.0-1.fedora43.x86_64.rpm",
        }[kind]
        (assets / name).write_bytes(release.payload)
    signer.sign(assets, release.private, now=release.now)
    manifest, asset = updates.verify_manifest(
        (assets / "update.json").read_bytes(),
        (assets / "update.json.sig").read_bytes(),
        release.info,
    )
    assert set(manifest["assets"]) == set(signer.TARGETS)
    assert asset == release.asset
    assert manifest["expires"] == release.now + 90 * 86400
    (root / "src/caelum/update-public.pem").write_bytes(b"wrong key")
    with pytest.raises(ValueError, match="does not match"):
        signer.sign(assets, release.private)
