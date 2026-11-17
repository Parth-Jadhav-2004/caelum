from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from caelum.config import Config, load, save
from caelum.hardware import Hardware
from caelum.ipc_contract import METHODS, matches
from caelum.models import ModelManager
from caelum.sidecar import Backend


def test_model_list_contract_hardware_gate_and_extra(tmp_path, monkeypatch):
    monkeypatch.setattr("caelum.models.importlib.util.find_spec", lambda _: None)
    manager = ModelManager(tmp_path)
    hardware = Hardware(mem_total_mb=4096, mem_available_mb=2000, cores=2, arch="x86_64",
                        avx2=True, disk_free_mb=10000)
    result = {**manager.list(Config(), hardware), "pending_use": None}
    assert matches(METHODS["models.list"]["result"], result)
    cohere = next(m for m in result["models"] if m["id"] == "cohere-transcribe")
    assert cohere["visible"] is False
    assert cohere["disabled_reason"] == "Needs 8 GB memory"
    whisper = next(m for m in result["models"] if m["id"] == "whisper-turbo")
    assert whisper["disabled_reason"] == "Needs an extra component."
    assert manager.list(Config(), replace(hardware, mem_total_mb=16384))["recommended"]["id"] == "parakeet-110m"


async def test_models_use_persists_even_before_download_and_refuses_busy(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    save(Config(), path)
    backend = Backend(path)
    monkeypatch.setattr(backend, "status", AsyncMock(return_value={
        "running": False, "state": "hidden",
    }))
    result = await backend.dispatch("models.use", {"id": "parakeet-110m"})
    assert result == {"saved": True}
    config = load(path)
    assert config.stt.engine == "local"
    assert config.stt.local_model == "parakeet-110m"
    monkeypatch.setattr(backend, "status", AsyncMock(return_value={
        "running": True, "state": "recording",
    }))
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="Finish"):
        await backend.dispatch("models.use", {"id": "parakeet-v3"})
    assert path.read_bytes() == before


async def test_remove_in_use_and_fallback_model_is_blocked(tmp_path):
    path = tmp_path / "config.toml"
    config = Config()
    config.stt.engine, config.stt.local_model = "local", "parakeet-v3"
    save(config, path)
    backend = Backend(path)
    with pytest.raises(RuntimeError, match="Switch to another model first"):
        await backend.dispatch("models.remove", {"id": "parakeet-v3"})
    config.stt.engine, config.stt.fallback = "online", "local"
    save(config, path)
    with pytest.raises(RuntimeError, match="Switch to another model first"):
        await backend.dispatch("models.remove", {"id": "parakeet-v3"})


async def test_skip_practice_finishes_with_download_still_queued(tmp_path, monkeypatch):
    from caelum.onboarding import Progress

    path = tmp_path / "config.toml"
    config = Config()
    config.stt.engine, config.stt.local_model = "local", "parakeet-v3"
    save(config, path)
    backend = Backend(path)
    backend.setup_checks = {"microphone", "shortcut"}
    backend.models.states["parakeet-v3"] = {"state": "downloading"}
    monkeypatch.setattr(backend, "start", AsyncMock())
    await backend.dispatch("setup.finish", {"skip_practice": True})
    assert Progress.load(path).complete
    assert backend.models.states["parakeet-v3"]["state"] == "downloading"
