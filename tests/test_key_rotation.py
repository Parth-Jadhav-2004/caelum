"""Real Ed25519 transitions, keeping raw signatures usable by old updaters."""

import base64
import importlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
from caelum import updates


def keypair(root, name):
    private, public = root / f"{name}.pem", root / f"{name}-public.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)], check=True
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True
    )
    return private, public


def record(public, revoked=False):
    pem = public.read_bytes()
    return {
        "id": updates.public_key_id(pem),
        "pem": pem.decode(),
        "not_before": 0,
        "not_after": 4102444800,
        "revoked": revoked,
    }


@pytest.fixture
def rotation(tmp_path, monkeypatch):
    old, old_public = keypair(tmp_path, "old")
    new, new_public = keypair(tmp_path, "new")
    (tmp_path / "update-public.pem").write_bytes(old_public.read_bytes())
    policy = tmp_path / "update-trust.json"
    policy.write_text(json.dumps({"schema": 1, "keys": [record(old_public), record(new_public)]}))
    monkeypatch.setattr(updates, "BASE", tmp_path)
    return tmp_path, old, old_public, new, new_public, policy


def test_overlap_and_revocation_use_only_installed_keys(rotation):
    root, old, old_public, new, new_public, policy = rotation
    assert len(updates.trusted_public_keys(root)) == 2
    policy.write_text(
        json.dumps({"schema": 1, "keys": [record(old_public, True), record(new_public)]})
    )
    assert updates.trusted_public_keys(root) == [new_public.read_bytes()]
    policy.write_text(
        json.dumps({"schema": 1, "keys": [record(old_public, True), record(new_public, True)]})
    )
    with pytest.raises(ValueError, match="No active"):
        updates.trusted_public_keys(root)


def test_bad_policy_never_falls_back_to_legacy_anchor(rotation):
    root, _, old_public, _, _, policy = rotation
    entry = record(old_public)
    entry["id"] = "0" * 64
    policy.write_text(json.dumps({"schema": 1, "keys": [entry]}))
    with pytest.raises(ValueError, match="identity"):
        updates.trusted_public_keys(root)
    entry["id"] = updates.public_key_id(old_public.read_bytes())
    entry["not_after"] = 1
    policy.write_text(json.dumps({"schema": 1, "keys": [entry]}))
    with pytest.raises(ValueError, match="No active"):
        updates.trusted_public_keys(root)


def test_dual_signing_preserves_legacy_clients_and_allows_new_key_only_policy(
    rotation, monkeypatch
):
    root, old, old_public, new, new_public, policy = rotation
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    signer = importlib.import_module("sign_release")
    source = root / "repo"
    (source / "python/caelum").mkdir(parents=True)
    (source / "pyproject.toml").write_text('[project]\nversion="0.9.0"\n')
    (source / "python/caelum/update-public.pem").write_bytes(old_public.read_bytes())
    (source / "python/caelum/update-trust.json").write_bytes(policy.read_bytes())
    monkeypatch.setattr(signer, "ROOT", source)
    assets = root / "assets"
    assets.mkdir()
    for target, (kind, _) in signer.TARGETS.items():
        name = {
            "deb": f"caelum_0.9.0-1_{target}_amd64.deb",
            "arch": "caelum-0.9.0-1-x86_64.pkg.tar.zst",
            "rpm": "caelum-0.9.0-1.fedora43.x86_64.rpm",
        }[kind]
        (assets / name).write_bytes(b"synthetic package")
    with pytest.raises(ValueError, match="legacy signing key"):
        signer.sign(assets, new)
    signer.sign(assets, new, legacy_private_key=old)
    raw = (assets / "update.json").read_bytes()
    legacy = (assets / "update.json.sig").read_bytes()
    bundle = (assets / "update-signatures.json").read_bytes()
    info = {"target": "arch"}
    # The old single pinned-key verifier still accepts the raw 64-byte signature.
    assert len(legacy) == 64

    fixture = Path(__file__).with_name("fixtures") / "upgrades/v0.4.0/verify_update.py"
    spec = importlib.util.spec_from_file_location("old_verifier", fixture)
    old_verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_verifier)
    assert old_verifier.verify_manifest(raw, legacy, info, key=old_public)[0]["version"] == "0.9.0"
    policy.write_text(
        json.dumps({"schema": 1, "keys": [record(old_public, True), record(new_public)]})
    )
    assert updates.verify_manifest(raw, bundle, info)[0]["version"] == "0.9.0"
    with pytest.raises(ValueError, match="verification failed"):
        updates.verify_manifest(raw, legacy, info)
    forged = json.loads(bundle)
    forged["signatures"] = [
        {
            "key_id": updates.public_key_id(new_public.read_bytes()),
            "signature": base64.b64encode(legacy).decode(),
        }
    ]
    with pytest.raises(ValueError, match="verification failed"):
        updates.verify_manifest(raw, json.dumps(forged).encode(), info)


def test_trust_policy_edit_cannot_remove_last_active_key(rotation, monkeypatch):
    root, _, old_public, _, new_public, policy = rotation
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    manager = importlib.import_module("manage_update_keys")
    manager.edit(policy, "revoke", updates.public_key_id(old_public.read_bytes()))
    before = policy.read_bytes()
    with pytest.raises(ValueError, match="No active"):
        manager.edit(policy, "revoke", updates.public_key_id(new_public.read_bytes()))
    assert policy.read_bytes() == before


def test_dangling_trust_policy_does_not_fall_back(rotation):
    root, _, _, _, _, policy = rotation
    policy.unlink()
    policy.symlink_to(root / "missing-policy")
    with pytest.raises(OSError):
        updates.trusted_public_keys(root)


def test_rotated_network_stage_and_privileged_verifier(rotation, monkeypatch):
    import hashlib
    import time

    import httpx

    root, old, old_public, new, new_public, policy = rotation
    now = int(time.time())
    payload = b"synthetic signed package"
    name = "caelum-0.9.0-1-x86_64.pkg.tar.zst"
    raw = json.dumps(
        {
            "schema": 1,
            "version": "0.9.0",
            "issued": now,
            "expires": now + 86400,
            "assets": {
                "arch": {
                    "name": name,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            },
        }
    ).encode()
    manifest = root / "manifest"
    manifest.write_bytes(raw)
    entries = []
    for private, public in ((old, old_public), (new, new_public)):
        signature = root / "signature"
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private),
                "-rawin",
                "-in",
                str(manifest),
                "-out",
                str(signature),
            ],
            check=True,
        )
        entries.append(
            {
                "key_id": updates.public_key_id(public.read_bytes()),
                "signature": base64.b64encode(signature.read_bytes()).decode(),
            }
        )
    legacy = base64.b64decode(entries[0]["signature"])
    signatures = json.dumps({"schema": 1, "signatures": entries}).encode()
    policy.write_text(
        json.dumps({"schema": 1, "keys": [record(old_public, True), record(new_public)]})
    )
    info = {"version": "0.8.0", "target": "arch", "python": "3.14"}
    monkeypatch.setattr(updates, "installed", lambda: info)
    monkeypatch.setattr(updates, "compatible", lambda _: True)
    requests = []

    def response(request):
        requests.append(request.url.path)
        content = {
            "update.json": raw,
            "update.json.sig": legacy,
            "update-signatures.json": signatures,
            name: payload,
        }[request.url.path.rsplit("/", 1)[-1]]
        return httpx.Response(200, content=content)

    monkeypatch.setattr(
        updates, "network_client", lambda _: httpx.Client(transport=httpx.MockTransport(response))
    )
    found = updates.check()
    assert found["signature"] == signatures
    assert updates.stage(found) == "0.9.0"
    pending = updates.cache_dir() / "pending"
    assert (pending / "update.json.sig").read_bytes() == signatures
    monkeypatch.setattr(updates.os, "geteuid", lambda: 0)
    installed = []
    original = subprocess.run

    def run(args, **kwargs):
        if args[0] == "/usr/bin/pacman":
            installed.append(args)
            return subprocess.CompletedProcess(args, 0)
        return original(args, **kwargs)

    monkeypatch.setattr(updates.subprocess, "run", run)
    updates.install_verified(pending)
    assert len(installed) == 1
    assert all(".pem" not in path and "trust" not in path for path in requests)
