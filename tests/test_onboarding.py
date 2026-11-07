import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from caelum.config import Config
from caelum.onboarding import Progress, check_shortcut, practice, record_sample, validate_providers
from caelum.providers import ProviderError


def test_setup_progress_roundtrip_and_corrupt_recovery(tmp_path):
    path = tmp_path / "config.toml"
    assert not Progress.load(path).complete
    Progress(3, False).save(path)
    assert Progress.load(path).stage == 3
    Progress(4, True).save(path)
    assert Progress.load(path).complete
    path.with_name("onboarding.json").write_text("invalid")
    assert Progress.load(path) == Progress()


async def test_all_selected_models_must_validate(monkeypatch):
    config = Config()
    config.cleanup.model = "refinement"
    models = AsyncMock(side_effect=[[config.stt.model], []])
    monkeypatch.setattr("caelum.providers.Providers.models", models)
    with pytest.raises(ProviderError, match="Refinement model unavailable"):
        await validate_providers(config)
    assert models.await_count == 2


async def test_transcription_only_validation(monkeypatch):
    config = Config()
    models = AsyncMock(return_value=[config.stt.model])
    monkeypatch.setattr("caelum.providers.Providers.models", models)
    await validate_providers(config)
    models.assert_awaited_once()


async def test_hyprland_shortcut_conflict(monkeypatch):
    config = Config()
    monkeypatch.setattr("caelum.onboarding.backend_name", lambda _: "hyprland")
    monkeypatch.setattr("caelum.linux.shortcut_keys", lambda _: ([("", "V", 72)], False))
    monkeypatch.setattr(
        "caelum.linux.hypr_json",
        AsyncMock(
            side_effect=[
                {"configProvider": "lua"},
                [{"key": "V", "modmask": 72}],
            ]
        ),
    )
    with pytest.raises(RuntimeError, match="already in use"):
        await check_shortcut(config)


async def test_portable_shortcut_explains_permission_and_manual_fallback(monkeypatch):
    monkeypatch.setattr("caelum.onboarding.backend_name", lambda _: "portable")
    result = await check_shortcut(Config())
    assert "permission" in result and "Record / Finish" in result


def test_local_recording_cancel_closes_and_discards(monkeypatch):
    calls = []
    capture = SimpleNamespace(
        start=lambda: calls.append("start"),
        stop=lambda: calls.append("stop"),
        discard=lambda: calls.append("discard"),
        error=False,
        level=0,
        speech_ms=100,
    )
    monkeypatch.setattr("caelum.onboarding.Capture", lambda _: capture)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        record_sample(Config(), 3, cancelled)
    assert calls == ["start", "stop", "discard"]


@pytest.mark.parametrize("late_error", [False, True])
def test_local_recording_reports_transport_error_and_discards_partial_audio(monkeypatch, late_error):
    error = "Microphone stopped sending audio. Reconnect the headset."
    capture = SimpleNamespace(
        start=Mock(), stop=Mock(), discard=Mock(), snapshot=Mock(),
        error=None if late_error else error, level=0, speech_ms=100,
    )
    if late_error:
        capture.stop.side_effect = lambda: setattr(capture, "error", error)
    monkeypatch.setattr("caelum.onboarding.Capture", lambda _: capture)
    with pytest.raises(RuntimeError, match="Reconnect the headset"):
        record_sample(Config(), 0 if late_error else 1, threading.Event())
    capture.snapshot.assert_not_called()
    capture.discard.assert_called_once()


async def test_practice_success_uses_providers_without_history_or_insertion(monkeypatch):
    monkeypatch.setattr(
        "caelum.providers.Providers.stt", AsyncMock(return_value=SimpleNamespace(text="Hello"))
    )
    monkeypatch.setattr(
        "caelum.providers.Providers.cleanup", AsyncMock(return_value=("Hello.", True))
    )
    assert await practice(Config(), b"speech", threading.Event()) == ("Hello.", True)


async def test_practice_cancellation_ignores_late_work(monkeypatch):
    began = asyncio.Event()
    stopped = asyncio.Event()

    async def slow(*_args):
        began.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    monkeypatch.setattr("caelum.providers.Providers.stt", slow)
    cancelled = threading.Event()
    task = asyncio.create_task(practice(Config(), b"speech", cancelled))
    await began.wait()
    cancelled.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        await task
    assert stopped.is_set()


async def test_provider_validation_error_names_role_and_credential(monkeypatch):
    config = Config()
    config.cleanup.model = "refinement"
    config.cleanup.key_env = "REFINEMENT_KEY"
    models = AsyncMock(side_effect=[[config.stt.model], ProviderError("Invalid key", "auth")])
    monkeypatch.setattr("caelum.providers.Providers.models", models)
    with pytest.raises(ProviderError, match=r"Refinement \(REFINEMENT_KEY\): Invalid key") as error:
        await validate_providers(config)
    assert error.value.kind == "auth"
