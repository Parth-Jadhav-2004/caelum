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
preview = importlib.import_module("publish_prerelease")
resolver = importlib.import_module("resolve_candidate")


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
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {value}\n\nVerified user-visible changes.\n"
    )
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
    for name in candidate.desktop_assets(value):
        (assets / name).write_bytes(name.encode())
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


class PrereleaseGitHub(GitHub):
    def create(self, tag, sha, notes):
        super().create(tag, sha, notes)
        self.info["prerelease"] = True
        self.tag = tag
        return self.info

    def release(self, tag):
        return self.info if getattr(self, "tag", None) == tag else None


def publish_preview(data, github, channel="testing"):
    assets, identity, _ = data
    preview.publish(assets, identity["sha"], identity["run_id"], identity["run_attempt"],
                    channel, github)


@pytest.mark.parametrize("channel,tag", [
    ("development", "v0.4.2-dev.123.1"), ("testing", "v0.4.2-rc.123"),
])
def test_channel_tags_are_distinct_and_prereleases_never_use_stable_metadata(
    release_candidate, channel, tag,
):
    assets, identity, _ = release_candidate
    github = PrereleaseGitHub()
    expected_tag = tag.replace("0.4.2", identity["version"])
    assert preview.tag_for(identity, channel) == expected_tag
    packages = {path.name: path.read_bytes() for path in assets.iterdir()
                if path.name in candidate.package_names(identity["version"]).values()}
    publish_preview(release_candidate, github, channel)
    assert github.info == {"id": 1, "draft": False, "prerelease": True}
    assert "SHA256SUMS" in github.assets and "candidate.json" in github.assets
    assert not {"update.json", "update.json.sig", "update-signatures.json"} & github.assets.keys()
    assert all(github.assets[name] == value for name, value in packages.items())


def test_prerelease_resumes_failed_upload_without_replacing_assets(release_candidate):
    github = PrereleaseGitHub()
    github.interrupt = True
    with pytest.raises(RuntimeError, match="Interrupted"):
        publish_preview(release_candidate, github)
    assert github.info["draft"]
    publish_preview(release_candidate, github)
    uploads = github.upload_count
    publish_preview(release_candidate, github)
    assert github.upload_count == uploads and github.publish_count == 1
    name = next(iter(github.assets))
    github.assets[name] = b"changed"
    with pytest.raises(ValueError, match="incomplete|differs"):
        publish_preview(release_candidate, github)
    assert github.assets[name] == b"changed"


@pytest.mark.parametrize("state", ["missing", "draft", "stable", "changed"])
def test_production_requires_the_same_published_testing_candidate(release_candidate, state):
    github = PrereleaseGitHub()
    if state != "missing":
        publish_preview(release_candidate, github)
        if state == "draft":
            github.info["draft"] = True
        elif state == "stable":
            github.info["prerelease"] = False
        else:
            github.assets["candidate.json"] = b"wrong candidate"
    assets, identity, _ = release_candidate
    with pytest.raises(ValueError, match="testing|incomplete|differs"):
        preview.verify_testing(assets, identity["sha"], identity["run_id"],
                               identity["run_attempt"], github)


def test_testing_to_production_signs_the_same_packages_without_rebuilding(release_candidate):
    testing = PrereleaseGitHub()
    publish_preview(release_candidate, testing)
    assets, identity, _ = release_candidate
    preview.verify_testing(assets, identity["sha"], identity["run_id"],
                           identity["run_attempt"], testing)
    production = GitHub()
    promote(release_candidate, production)
    for name in candidate.package_names(identity["version"]).values():
        assert testing.assets[name] == production.assets[name]
    assert "update.json.sig" in production.assets
    assert "update.json.sig" not in testing.assets


def test_development_release_does_not_satisfy_production_testing_gate(release_candidate):
    github = PrereleaseGitHub()
    publish_preview(release_candidate, github, "development")
    assets, identity, _ = release_candidate
    with pytest.raises(ValueError, match="testing before production"):
        preview.verify_testing(assets, identity["sha"], identity["run_id"],
                               identity["run_attempt"], github)


def test_testing_rejects_a_version_already_in_production(release_candidate, monkeypatch):
    github = PrereleaseGitHub()
    monkeypatch.setattr(github, "latest_version", lambda: (999, 0, 0))
    with pytest.raises(ValueError, match="above production"):
        publish_preview(release_candidate, github)
    assert github.info is None and not github.assets


def test_published_testing_rerun_after_production_remains_an_immutable_noop(
    release_candidate, monkeypatch,
):
    github = PrereleaseGitHub()
    publish_preview(release_candidate, github)
    uploads = github.upload_count
    monkeypatch.setattr(github, "latest_version", lambda: (999, 0, 0))
    publish_preview(release_candidate, github)
    assert github.upload_count == uploads and github.publish_count == 1


def test_rebuilt_attempt_cannot_reuse_previously_tested_candidate(release_candidate):
    github = PrereleaseGitHub()
    publish_preview(release_candidate, github)
    assets, identity, _ = release_candidate
    identity["run_attempt"] = "2"
    for path in assets.glob("build-info-*.json"):
        info = json.loads(path.read_text())
        info["run_attempt"] = "2"
        path.write_text(json.dumps(info))
    (assets / "candidate.json").unlink()
    (assets / "SHA256SUMS").unlink()
    candidate.assemble(assets)
    with pytest.raises(ValueError, match="incomplete|differs"):
        preview.verify_testing(assets, identity["sha"], identity["run_id"], "2", github)


@pytest.mark.parametrize("field,value", [("run_id", "local"), ("run_attempt", "0")])
def test_prerelease_requires_real_run_identity(field, value):
    identity = {"version": "0.4.3", "run_id": "123", "run_attempt": "1", field: value}
    with pytest.raises(ValueError, match="GitHub candidate run"):
        preview.tag_for(identity, "development")


def test_preview_cannot_leak_signed_production_update_metadata(release_candidate):
    assets, _, _ = release_candidate
    (assets / "update.json").write_text("production metadata")
    with pytest.raises(ValueError, match="production update metadata"):
        publish_preview(release_candidate, PrereleaseGitHub())


def test_prerelease_commands_cannot_replace_the_production_latest(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(preview.subprocess, "run", lambda command, **_: commands.append(command))
    github = preview.PrereleaseGitHub()
    def create(path, data):
        assert data["make_latest"] == "false" and data["prerelease"] and data["draft"]
        return {"id": 45, **data}
    monkeypatch.setattr(github, "api", create)
    notes = tmp_path / "notes"
    notes.write_text("Testing")
    assert github.create("v0.4.3-rc.123", "a" * 40, notes)["id"] == 45
    github.publish("v0.4.3-rc.123")
    assert all("--latest=false" in command and "--prerelease" in command for command in commands)
    assert all("--clobber" not in command for command in commands)


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_candidate_resolution_accepts_only_successful_main_builds(event):
    run = {"workflow_id": 42, "head_repository": {"full_name": "owner/caelum"},
           "head_branch": "main", "event": event, "status": "completed",
           "conclusion": "success", "head_sha": "a" * 40, "run_attempt": 1}
    assert resolver.resolve(run, 42, "owner/caelum", "main") == {"sha": "a" * 40, "attempt": 1}


@pytest.mark.parametrize("field,value", [
    ("workflow_id", 43), ("head_repository", {"full_name": "fork/caelum"}),
    ("head_branch", "feature"), ("event", "pull_request"),
    ("status", "in_progress"), ("conclusion", "failure"),
    ("head_sha", "main"), ("run_attempt", 0), ("run_attempt", True),
])
def test_candidate_resolution_rejects_untrusted_or_incomplete_builds(field, value):
    run = {"workflow_id": 42, "head_repository": {"full_name": "owner/caelum"},
           "head_branch": "main", "event": "push", "status": "completed",
           "conclusion": "success", "head_sha": "a" * 40, "run_attempt": 1, field: value}
    with pytest.raises(ValueError, match="successful candidate"):
        resolver.resolve(run, 42, "owner/caelum", "main")


def test_production_resolution_requires_manual_acceptance(monkeypatch):
    monkeypatch.setenv("RUN_ID", "123")
    monkeypatch.setenv("CHANNEL", "production")
    monkeypatch.setenv("QUALIFIED", "false")
    with pytest.raises(ValueError, match="manual desktop acceptance"):
        resolver.main()


def test_publication_cannot_use_a_workflow_dispatched_from_an_old_tag(monkeypatch):
    monkeypatch.setenv("RUN_ID", "123")
    monkeypatch.setenv("CHANNEL", "development")
    monkeypatch.setenv("GH_REPO", "owner/caelum")
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v0.4.0")
    monkeypatch.setattr(resolver.subprocess, "check_output",
                        lambda _: json.dumps({"default_branch": "main"}).encode())
    with pytest.raises(ValueError, match="channel branch"):
        resolver.main()


def promote(data, github):
    assets, identity, key = data
    publisher.publish(
        assets, identity["sha"], identity["run_id"], identity["run_attempt"], key, github
    )


def test_local_runtime_is_vendored_by_default_and_has_size_budget(tmp_path):
    import build_package

    command = build_package.requirements_command(tmp_path / "requirements.txt")
    assert command[command.index("--extra") + 1] == "local"
    assert "--locked" in command
    assert "whisper" not in command
    library = tmp_path / "lib"
    package = library / "sherpa_onnx"
    package.mkdir(parents=True)
    binary = package / "runtime.so"
    binary.write_bytes(b"runtime")
    assert build_package.check_local_runtime(library) == 7
    with binary.open("wb") as stream:
        stream.truncate(build_package.LOCAL_RUNTIME_BUDGET + 1)
    with pytest.raises(RuntimeError, match="50 MB"):
        build_package.check_local_runtime(library)


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


def test_release_notes_selects_only_requested_version(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher, "ROOT", tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 0.4.1\n\nNew changes.\n\n### Upgrade\n\nInstructions.\n"
        "\n## 0.4.0\n\nOlder changes.\n"
    )
    notes = publisher.release_notes("0.4.1")
    assert "New changes." in notes
    assert "### Upgrade" in notes
    assert "Older changes." not in notes
    with pytest.raises(ValueError, match="Reviewed release notes"):
        publisher.release_notes("0.5.0")
