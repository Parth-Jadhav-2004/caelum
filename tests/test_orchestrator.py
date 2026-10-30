import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from caelum.config import Config
from caelum.orchestrator import Orchestrator
from caelum.providers import ProviderError


class HUD:
    def __init__(self):
        self.events = []

    async def emit(self, message):
        self.events.append(message.copy())


@pytest.fixture
def core(monkeypatch):
    monkeypatch.setattr("caelum.orchestrator.session_locked", AsyncMock(return_value=False))
    monkeypatch.setattr("caelum.orchestrator.notify", AsyncMock())
    monkeypatch.setattr("caelum.orchestrator.recovery_notification", AsyncMock())
    bindings = SimpleNamespace(active=AsyncMock())
    provider = SimpleNamespace(
        reset_metrics=lambda: None,
        metrics={},
        stt=AsyncMock(return_value=SimpleNamespace(text="private spoken words")),
        cleanup=AsyncMock(return_value=("Private spoken words.", True)),
    )
    result = Orchestrator(Config(), provider, HUD(), bindings)
    result.session = "test-session"
    result.started = result.released = time.monotonic()
    result.target = SimpleNamespace(output="eDP-1")
    result.pcm = b"\0" * 32000
    return result


async def test_final_insertion_once_and_no_transcript_in_hud(core, monkeypatch):
    insertion = AsyncMock(return_value=True)
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    await core.finalize(core.session)
    insertion.assert_awaited_once()
    assert core.state == "success"
    assert core.pcm is None
    assert not any("private" in str(event).casefold() for event in core.hud.events)
    assert core.recent_metrics[-1]["visible_insertion_observed"] is False


async def test_completion_hook_runs_only_after_insertion(core, monkeypatch):
    completed = []
    core.on_completed = lambda *arguments: completed.append(arguments)
    monkeypatch.setattr("caelum.orchestrator.insert", AsyncMock(return_value=False))
    await core.finalize(core.session)
    assert len(completed) == 1
    assert completed[0][1] == "Private spoken words."
    assert completed[0][-1] is True
    assert core.pcm is None


async def test_pause_discards_pending_audio_and_resume(core):
    await core.handle("pause")
    assert core.paused
    assert core.pcm is None
    session = core.session
    await core.handle("start", "while-paused")
    assert core.session == session
    assert (await core.handle("status"))["paused"]
    await core.handle("resume")
    assert not core.paused


async def test_storage_hook_failure_never_retries_insertion(core, monkeypatch):
    def failure(*arguments):
        raise RuntimeError("Storage unavailable")

    core.on_completed = failure
    insertion = AsyncMock(return_value=True)
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    await core.finalize(core.session)
    insertion.assert_awaited_once()
    assert core.state == "success"
    assert core.pcm is None


async def test_clipboard_fallback_is_distinct(core, monkeypatch):
    monkeypatch.setattr("caelum.orchestrator.insert", AsyncMock(return_value=False))
    await core.finalize(core.session)
    assert core.state == "copied"
    assert core.pcm is None


async def test_error_retains_audio_and_blocks_new_recording(core):
    core.provider.stt.side_effect = ProviderError("offline")
    await core.finalize(core.session)
    assert core.state == "error" and core.pcm is not None
    await core.handle("start", "new")
    assert core.session == "test-session"
    assert core.capture is None
    await core.cancel()
    assert core.pcm is None


async def test_cancel_prevents_late_insertion(core, monkeypatch):
    insertion = AsyncMock()
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    began = asyncio.Event()

    async def slow_stt(pcm):
        began.set()
        await asyncio.sleep(60)

    core.provider.stt = slow_stt
    old_session = core.session
    core.work = asyncio.create_task(core.finalize(old_session))
    await began.wait()
    await core.handle("cancel")
    assert core.work.cancelled()
    assert core.session != old_session
    assert core.pcm is None
    insertion.assert_not_awaited()


async def test_retry_expiry_discards_audio(core):
    core.state = "error"
    await core.expire(core.session, 0)
    assert core.state == "hidden"
    assert core.pcm is None


async def test_retry_uses_saved_audio(core, monkeypatch):
    core.state = "error"
    monkeypatch.setattr("caelum.orchestrator.insert", AsyncMock(return_value=True))
    await core.handle("retry")
    await core.work
    assert core.state == "success"


async def test_locked_session_never_inserts(core, monkeypatch):
    monkeypatch.setattr("caelum.orchestrator.session_locked", AsyncMock(return_value=True))
    insertion = AsyncMock()
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    await core.finalize(core.session)
    insertion.assert_not_awaited()
    assert core.pcm is None


async def test_cancel_before_delayed_start_cannot_resurrect_capture(core):
    core.pcm = None
    await core.handle("cancel", "delayed-start")
    cancelled_session = core.session
    await core.handle("start", "delayed-start")
    assert core.session == cancelled_session
    assert core.capture is None
    assert core.state == "hidden"


async def test_release_before_start_is_an_accidental_press(core, monkeypatch):
    core.pcm = None

    class Capture:
        def __init__(self, config):
            self.size = 1600  # 50 ms; retained duration, not delayed IPC delivery time
            self.speech_ms = 0
            self.level = 0
            self.history = [0] * 17

        def start(self):
            pass

        def stop(self):
            pass

        def discard(self):
            self.size = 0

    monkeypatch.setattr("caelum.orchestrator.Capture", Capture)
    monkeypatch.setattr("caelum.orchestrator.target_at_press", AsyncMock(return_value=core.target))
    await core.handle("stop", "reordered")
    await core.handle("start", "reordered")
    assert core.capture is None
    assert core.state == "hidden"
    core.provider.stt.assert_not_awaited()
    assert "reordered" not in core.early_stops


async def test_portable_delivery_waits_for_storage_and_never_injects(core, monkeypatch):
    core.bindings.save_only = True
    completed = AsyncMock(return_value=True)
    core.on_completed = completed
    insertion = AsyncMock()
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    await core.finalize(core.session)
    insertion.assert_not_awaited()
    completed.assert_awaited_once()
    assert completed.call_args.args[-1] is False  # not claimed as clipboard recovery
    assert core.state == "saved"
    assert core.pcm is None
    assert core.recent_metrics[-1]["manual_copy"]


async def test_portable_storage_failure_keeps_audio_for_retry(core, monkeypatch):
    core.bindings.save_only = True
    core.on_completed = AsyncMock(return_value=False)
    insertion = AsyncMock()
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    await core.finalize(core.session)
    assert core.state == "error"
    assert core.pcm is not None
    insertion.assert_not_awaited()
    await core.cancel()


async def test_toggle_stops_current_recording_inside_control_lock(core):
    core.capture = object()
    core.release = AsyncMock()
    await core.handle("toggle")
    core.release.assert_awaited_once()
