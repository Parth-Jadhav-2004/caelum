"""Exercise promotion and interrupted publication without contacting GitHub."""

import importlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
candidate = importlib.import_module("release_candidate")
publisher = importlib.import_module("publish_release")
signer = importlib.import_module("sign_release")


@pytest.fixture
def release_candidate(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    actual = Path(__file__).resolve().parents[1]
    for name in (
        "pyproject.toml",
        "package.json",
        "src-tauri/Cargo.toml",
        "src-tauri/tauri.conf.json",
        "uv.lock",
        "package-lock.json",
        "src-tauri/Cargo.lock",
    ):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(actual / name, destination)
    monkeypatch.setattr(candidate, "ROOT", root)
    monkeypatch.setattr(publisher, "ROOT", root)
    monkeypatch.setattr(signer, "ROOT", root)
    value = candidate.version()
    (root / "docs").mkdir()
    (root / f"docs/release-{value}.md").write_text("# Release\n\nVerified user-visible changes.\n")
    (root / "python/caelum").mkdir(parents=True)
    key = tmp_path / "private.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)], check=True)
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            str(key),
            "-pubout",
            "-out",
            str(root / "python/caelum/update-public.pem"),
        ],
        check=True,
    )
    identity = {"sha": "a" * 40, "version": value, "run_id": "123", "run_attempt": "1"}
    monkeypatch.setattr(candidate, "source_identity", lambda: identity)
    assets = tmp_path / "assets"
    assets.mkdir()
    for target, name in candidate.package_names(value).items():
        (assets / name).write_bytes(f"package for {target}".encode())
        info = {
            **identity,
            "target": target,
            "package": name,
            "asset": candidate.digest(assets / name),
            "checks": [
                "package-install",
                "backend-ipc",
                "simulated-audio",
                "native-react-bootstrap",
            ],
            "locks": {
                name: candidate.digest(root / name)["sha256"]
                for name in ("uv.lock", "package-lock.json", "src-tauri/Cargo.lock")
            },
        }
        (assets / f"build-info-{target}.json").write_text(json.dumps(info))
    candidate.assemble(assets)
    return assets, identity, key


class GitHub:
    def __init__(self):
        self.info = None
        self.assets = {}
        self.tag_sha = None
        self.upload_count = 0
        self.interrupt = False
        self.publish_count = 0

    def latest_version(self):
        return None

    def ensure_tag(self, tag, sha):
        if self.tag_sha and self.tag_sha != sha:
            raise ValueError("Existing version tag points to another commit")
        self.tag_sha = sha

    def release(self, tag):
        return self.info

    def create(self, tag, sha, notes):
        self.info = {"id": 1, "draft": True}

    def api(self, path):
        return [
            {"name": name, "state": "uploaded", "size": len(data)}
            for name, data in self.assets.items()
        ]

    def upload(self, tag, path):
        assert path.name not in self.assets, "must not overwrite any asset"
        if self.interrupt and self.upload_count == 2:
            self.interrupt = False
            raise RuntimeError("Interrupted network upload")
        self.assets[path.name] = path.read_bytes()
        self.upload_count += 1

    def download(self, tag, name, directory):
        (directory / name).write_bytes(self.assets[name])

    def publish(self, tag):
        self.info["draft"] = False
        self.publish_count += 1


def promote(data, github):
    assets, identity, key = data
    publisher.publish(
        assets, identity["sha"], identity["run_id"], identity["run_attempt"], key, github
    )


def test_interrupted_publication_resumes_then_published_rerun_is_noop(release_candidate):
    github = GitHub()
    github.interrupt = True
    with pytest.raises(RuntimeError, match="Interrupted"):
        promote(release_candidate, github)
    assert github.info["draft"] and github.upload_count == 2
    promote(release_candidate, github)
    assert not github.info["draft"]
    count = github.upload_count
    promote(release_candidate, github)
    assert github.upload_count == count and github.publish_count == 1
    assert {
        "SHA256SUMS",
        "update.json",
        "update.json.sig",
        "candidate.json",
    } <= github.assets.keys()


def test_published_assets_are_never_replaced(release_candidate):
    github = GitHub()
    promote(release_candidate, github)
    name = next(iter(github.assets))
    github.assets[name] = b"different bytes"
    with pytest.raises(ValueError, match="incomplete|differs"):
        promote(release_candidate, github)
    assert github.assets[name] == b"different bytes"


def test_existing_version_tag_cannot_move(release_candidate):
    github = GitHub()
    github.tag_sha = "b" * 40
    with pytest.raises(ValueError, match="another commit"):
        promote(release_candidate, github)
    assert github.info is None and not github.assets


@pytest.mark.parametrize("failure", ["checksum", "missing", "origin", "expired", "attempt", "lock"])
def test_candidate_verification_rejects_bad_evidence(release_candidate, failure):
    assets, identity, _ = release_candidate
    if failure == "lock":
        (candidate.ROOT / "uv.lock").write_text("changed lockfile")
    elif failure == "checksum":
        next(assets.glob("*.deb")).write_bytes(b"changed package")
    elif failure == "missing":
        next(assets.glob("*.deb")).unlink()
    elif failure == "origin":
        identity = {**identity, "sha": "c" * 40}
    elif failure == "attempt":
        identity = {**identity, "run_attempt": "2"}
    now = int(time.time()) + 8 * 86400 if failure == "expired" else None
    with pytest.raises((ValueError, FileNotFoundError)):
        candidate.verify(assets, identity["sha"], identity["run_id"], identity["run_attempt"], now)


def test_promotion_cannot_roll_back_latest_stable(release_candidate, monkeypatch):
    github = GitHub()
    monkeypatch.setattr(github, "latest_version", lambda: (999, 0, 0))
    with pytest.raises(ValueError, match="older stable"):
        promote(release_candidate, github)
    assert github.info is None and not github.assets


def test_incomplete_remote_asset_keeps_draft_without_replacing_it(release_candidate, monkeypatch):
    github = GitHub()
    github.interrupt = True
    with pytest.raises(RuntimeError):
        promote(release_candidate, github)
    api = github.api
    monkeypatch.setattr(
        github, "api", lambda path: [{**item, "state": "starter"} for item in api(path)]
    )
    with pytest.raises(ValueError, match="incomplete"):
        promote(release_candidate, github)
    assert github.info["draft"] and github.upload_count == 2 and github.publish_count == 0
