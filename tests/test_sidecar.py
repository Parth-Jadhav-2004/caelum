"""Desktop boundary tests use temporary XDG roots and never touch real microphones."""

import asyncio
import json
import os
import sys
from dataclasses import asdict
from unittest.mock import AsyncMock

import pytest
from caelum.config import Config, load, save
from caelum.sidecar import Backend


@pytest.fixture
def backend(tmp_path):
    path = tmp_path / "settings.toml"
    save(Config(), path)
    return Backend(path)


async def test_configuration_round_trip_preserves_hidden_values(backend):
    config = load(backend.path)
    config.stt.vocabulary = "Caelum, local words"
    save(config, backend.path)
    result = await backend.dispatch("settings.save", {"config": {"desktop": {"theme": "dark"}}})
    assert result == {"saved": True}
    assert load(backend.path).stt.vocabulary == "Caelum, local words"
    assert load(backend.path).desktop.theme == "dark"
    with pytest.raises(ValueError):
        await backend.dispatch("settings.save", {"config": {"app": {"unknown": 1}}})


async def test_failed_save_preserves_original_config(backend):
    original = backend.path.read_bytes()
    with pytest.raises(ValueError):
        await backend.dispatch("settings.save", {"config": {"desktop": {"retention_days": 0}}})
    assert backend.path.read_bytes() == original


async def test_busy_stop_does_not_discard_without_confirmation(backend, monkeypatch):
    monkeypatch.setattr(
        backend,
        "status",
        AsyncMock(return_value={"running": True, "state": "error", "pending_audio": True}),
    )
    stop = AsyncMock()
    monkeypatch.setattr(backend, "stop", stop)
    with pytest.raises(RuntimeError, match="discard"):
        await backend.dispatch("service.stop", {})
    stop.assert_not_awaited()
    await backend.dispatch("service.stop", {"discard": True})
    stop.assert_awaited_once()


async def test_reload_failure_reports_saved_but_not_applied(backend, monkeypatch):
    monkeypatch.setattr(backend, "status", AsyncMock(return_value={"running": True}))
    monkeypatch.setattr(
        "caelum.sidecar.request", lambda _: (_ for _ in ()).throw(RuntimeError("Busy"))
    )
    result = await backend.dispatch("settings.save", {"config": {"desktop": {"theme": "light"}}})
    assert result["saved"] and "service not updated" in result["warning"]
    assert load(backend.path).desktop.theme == "light"


async def test_onboarding_requires_all_checks_and_upload_consent(backend, monkeypatch):
    with pytest.raises(ValueError):
        await backend.dispatch("setup.finish", {})
    monkeypatch.setattr(backend, "status", AsyncMock(return_value={"running": False}))
    with pytest.raises(ValueError, match="consent"):
        await backend.dispatch("practice", {"consent": False})
    monkeypatch.setattr("caelum.sidecar.validate_providers", AsyncMock())
    await backend.dispatch("setup.validate", {"consent": True})
    backend.setup_checks.update({"microphone", "shortcut", "practice"})
    # Appearance changes do not invalidate successful audio/provider checks.
    await backend.dispatch("settings.save", {"config": {"desktop": {"theme": "dark"}}})
    monkeypatch.setattr(backend, "start", AsyncMock())
    await backend.dispatch("setup.finish", {})
    assert (await backend.dispatch("bootstrap", {}))["setup"]["complete"]


async def test_credentials_validated_before_persistence(backend, monkeypatch):
    monkeypatch.setattr("caelum.providers.Providers.models", AsyncMock(return_value=[]))
    store = AsyncMock()
    monkeypatch.setattr("caelum.credentials.store", store)
    with pytest.raises(ValueError, match="model"):
        await backend.dispatch("credentials.store", {"name": "GROQ_API_KEY", "value": "test-only"})
    store.assert_not_called()


async def test_history_schema_and_lifetime_totals_remain_compatible(backend):
    config = load(backend.path)
    backend.history.record("session", "one two three", {"capture_ms": 1000}, config, True, False)
    assert len(await backend.dispatch("history", {})) == 1
    await backend.dispatch("history.delete", {"id": "session"})
    summary = await backend.dispatch("summary", {})
    assert summary["total_words"] == 3 and summary["sessions"] == 0


async def test_json_lines_process_eof_and_unknown_method(tmp_path):
    env = {**os.environ, "CAELUM_CONFIG": str(tmp_path / "settings.toml")}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "caelum.sidecar",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    frames = [
        {"v": 1, "id": 1, "method": "bootstrap"},
        {"v": 1, "id": 2, "method": "not.allowed"},
        {"v": 999, "id": 3, "method": "bootstrap"},
    ]
    stdout, stderr = await asyncio.wait_for(
        process.communicate(b"\n".join(json.dumps(frame).encode() for frame in frames) + b"\n"), 10
    )
    assert process.returncode == 0, stderr.decode()
    replies = {
        frame["id"]: frame for line in stdout.splitlines() if "id" in (frame := json.loads(line))
    }
    assert replies[1]["result"]["version"] == 1
    assert "credentials" in replies[1]["result"]
    assert "Unknown method" in replies[2]["error"]
    assert "Unsupported protocol" in replies[3]["error"]
    assert not any("value" in item for item in replies[1]["result"]["credentials"].values())


async def test_supervised_process_terminates_after_grace_deadline(backend, monkeypatch):
    class Process:
        returncode = None
        terminated = False

        async def wait(self):
            if not self.terminated:
                raise TimeoutError()
            return 0

        def terminate(self):
            self.terminated = True

    process = Process()
    backend.process = process
    monkeypatch.setattr("caelum.sidecar.request", lambda _: {})
    await backend.stop()
    assert process.terminated
    assert backend.process is None


async def test_configuration_contract_matches_python_dataclasses():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    output = root / "src/lib/config.generated.ts"
    previous = output.read_text()
    spec = importlib.util.spec_from_file_location(
        "generate", root / "scripts/generate-contracts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert output.read_text() == previous
    assert set(asdict(Config())) == {"app", "stt", "cleanup", "desktop"}


async def test_cancelled_validation_does_not_save_keys(backend, monkeypatch):
    entered = asyncio.Event()

    async def validate(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("caelum.sidecar.validate_providers", validate)
    stored = AsyncMock()
    monkeypatch.setattr("caelum.credentials.store", stored)
    task = asyncio.create_task(
        backend.dispatch("setup.validate", {"consent": True, "keys": {"GROQ_API_KEY": "test-only"}})
    )
    await entered.wait()
    await backend.dispatch("sample.cancel", {})
    with pytest.raises(RuntimeError, match="cancelled"):
        await task
    stored.assert_not_called()
    assert "provider" not in backend.setup_checks


async def test_staged_keys_saved_only_after_all_providers_validate(backend, monkeypatch):
    captured = []

    async def validate(config, credential_resolver=None):
        assert credential_resolver("GROQ_API_KEY") == "test-only"
        captured.append("validated")

    def store(name, value):
        captured.append("stored")
        return "file"

    monkeypatch.setattr("caelum.sidecar.validate_providers", validate)
    monkeypatch.setattr("caelum.credentials.store", store)
    result = await backend.dispatch(
        "setup.validate", {"consent": True, "keys": {"GROQ_API_KEY": "test-only"}}
    )
    assert captured == ["validated", "stored"]
    assert result == {"storage": {"GROQ_API_KEY": "file"}}


async def test_daemon_owner_loss_is_detected(monkeypatch):
    from caelum.service import owner_monitor

    monkeypatch.setattr("caelum.service.os.getppid", lambda: 1)
    with pytest.raises(RuntimeError, match="owner exited"):
        await owner_monitor(999)
