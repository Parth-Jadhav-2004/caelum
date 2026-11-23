import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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
    result.media = SimpleNamespace(pause=AsyncMock(), resume=AsyncMock())
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
    core.config.desktop.auto_copy = True
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


async def test_update_shutdown_blocks_already_queued_start_and_resume(core, monkeypatch):
    from caelum.service import prepare_update

    core.pcm = None
    stop = asyncio.Event()
    await prepare_update(core, stop)
    monkeypatch.setattr("caelum.orchestrator.Capture", lambda _: pytest.fail("late capture"))
    await core.handle("resume")
    await core.handle("start", "queued-before-update")
    assert core.stopping
    assert core.capture is None
    assert (await core.handle("status"))["state"] == "hidden"


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
    core.config.desktop.auto_copy = True
    monkeypatch.setattr("caelum.orchestrator.insert", AsyncMock(return_value=False))
    await core.finalize(core.session)
    assert core.state == "copied"
    assert core.pcm is None


async def test_retry_copies_exact_finished_transcript_with_history_off(core):
    core.config.desktop.auto_copy = True
    from caelum.desktop_services import service_presentation
    from caelum.orchestrator import notify

    core.config.desktop.history_enabled = False
    core.bindings.insert = AsyncMock(side_effect=RuntimeError("Clipboard changed"))
    core.bindings.copy_result = AsyncMock(side_effect=[RuntimeError("Clipboard is busy"), None])
    await core.finalize(core.session)
    status = await core.handle("status")
    assert status["error_kind"] == "clipboard"
    assert "Retry to copy the finished text" in service_presentation(status)[1]
    assert "spoken words" not in str(status)
    await core.handle("retry")
    await core.work
    assert core.state == "error"
    await core.handle("retry")
    await core.work
    assert core.state == "copied"
    assert core.pending_copy is core.pcm is None
    core.bindings.copy_result.assert_awaited_with("Private spoken words.")
    core.bindings.insert.assert_awaited_once()
    core.provider.stt.assert_awaited_once()
    core.provider.cleanup.assert_awaited_once()
    notify.assert_awaited_with("Text copied. Paste manually in the intended application.")


@pytest.mark.parametrize("history", [False, True])
@pytest.mark.parametrize("auto_copy", [False, True])
async def test_in_app_clipboard_notice_survives_hud_changes(core, history, auto_copy):
    from caelum.orchestrator import notify

    core.in_app_notifications = True
    core.config.desktop.history_enabled = history
    core.config.desktop.auto_copy = auto_copy
    core.on_completed = Mock()
    core.bindings.insert = AsyncMock(return_value=False)  # Focus moved: no direct insertion.
    core.bindings.copy_result = AsyncMock()
    await core.finalize(core.session)
    core.bindings.insert.assert_awaited_once_with("Private spoken words.", core.target, auto_copy=auto_copy)
    assert core.state == ("copied" if auto_copy else "ready_to_copy")
    if history:
        core.on_completed.assert_called_once_with(core.session, "Private spoken words.", core.metrics, True, auto_copy)
    else:
        core.on_completed.assert_not_called()
    await core.event("model_loading")
    status = await core.handle("status")
    assert status["can_copy"] is (not auto_copy)
    if auto_copy:
        assert "copied to the clipboard" in status["notice"]
    else:
        assert "Automatic copy is off" in status["notice"] and "Copy transcript" in status["notice"]
        assert "copied" not in status["notice"]
        core.bindings.copy_result.assert_not_awaited()
        await core.handle("copy")
        core.bindings.copy_result.assert_awaited_once_with("Private spoken words.")
        assert "copied to the clipboard" in (await core.handle("status"))["notice"]
    assert "Ctrl+V" in status["notice"]
    assert "spoken words" not in str(status)
    notify.assert_not_awaited()


async def test_in_app_retry_expiry_explains_discard_after_hud_hides(core):
    from caelum.orchestrator import notify, recovery_notification

    core.in_app_notifications = True
    core.config.app.retry_expiry_seconds = 0
    core.provider.stt.side_effect = ProviderError("offline")
    await core.finalize(core.session)
    await core.expiry
    status = await core.handle("status")
    assert status["state"] == "hidden" and not status["pending_audio"]
    assert "expired" in status["notice"] and "record again" in status["notice"]
    notify.assert_not_awaited()
    recovery_notification.assert_not_called()


@pytest.mark.parametrize("ending", ["cancel", "expire", "locked"])
async def test_pending_transcript_discarded_on_cancel_expiry_or_lock(core, ending):
    core.config.desktop.auto_copy = True
    core.bindings.insert = AsyncMock(side_effect=RuntimeError("Clipboard unavailable"))
    core.bindings.copy_result = AsyncMock()
    await core.finalize(core.session)
    if ending == "expire":
        await core.expire(core.session, 0)
    elif ending == "locked":
        core.bindings.locked = AsyncMock(return_value=True)
        await core.handle("retry")
        await core.work
    else:
        await core.handle("cancel")
    await core.handle("retry")
    assert core.pending_copy is core.pcm is None
    core.bindings.copy_result.assert_not_awaited()


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


async def test_external_retry_retires_old_prompt_before_next_failure(core, monkeypatch):
    prompts = asyncio.Queue()
    cleaned = []

    async def prompt(_, session, seconds):
        answer = asyncio.get_running_loop().create_future()
        prompts.put_nowait(answer)
        try:
            await core.handle(await answer)
        finally:
            await asyncio.sleep(0)  # Allow asynchronous notification teardown.
            cleaned.append(answer)

    monkeypatch.setattr("caelum.orchestrator.recovery_notification", prompt)
    core.provider.stt.side_effect = ProviderError("offline")
    await core.finalize(core.session)
    first = await prompts.get()
    try:
        await core.handle("retry")
        assert cleaned == [first] and first.cancelled()
        await core.work
        second = await prompts.get()
        assert core.state == "error"
        # Retry from the notification itself must not cancel or await itself.
        core.provider.stt.side_effect = None
        core.bindings.insert = AsyncMock(return_value=True)
        notification = core.recovery_task
        second.set_result("retry")
        await notification
        await core.work
        assert core.state == "success"
    finally:
        await core.cancel()


async def test_retry_while_failure_notice_pending_cannot_publish_stale_prompt(core, monkeypatch):
    from caelum.orchestrator import recovery_notification

    notifying = asyncio.Event()

    async def pending_notice(message):
        notifying.set()
        await asyncio.Future()

    monkeypatch.setattr(core, "notify", pending_notice)
    core.provider.stt.side_effect = ProviderError("offline")
    core.work = asyncio.create_task(core.finalize(core.session))
    await notifying.wait()
    old_work = core.work
    try:
        core.provider.stt.side_effect = None
        core.bindings.insert = AsyncMock(return_value=True)
        await core.handle("retry")
        await core.work
        assert core.state == "success" and old_work.done()
        recovery_notification.assert_not_called()
    finally:
        old_work.cancel()
        await asyncio.gather(old_work, return_exceptions=True)


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
    core.config.desktop.auto_copy = True
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
    core.config.desktop.auto_copy = True
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


@pytest.mark.parametrize("dispatched", [True, False])
async def test_repeated_retry_after_delivery_does_not_duplicate(core, monkeypatch, dispatched):
    insertion = AsyncMock(return_value=dispatched)
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    core.state = "error"
    await core.handle("retry")
    work = core.work
    await work
    for _ in range(3):
        await core.handle("retry")
    assert core.work is work
    insertion.assert_awaited_once()
    assert core.pcm is None


async def test_expired_or_cancelled_audio_cannot_be_retried(core, monkeypatch):
    insertion = AsyncMock()
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    await core.expire(core.session, 0)
    await core.handle("retry")
    await core.handle("cancel")
    await core.handle("retry")
    insertion.assert_not_awaited()
    core.provider.stt.assert_not_awaited()


async def test_queued_retry_clicks_schedule_only_one_finalization(core, monkeypatch):
    insertion = AsyncMock(return_value=True)
    monkeypatch.setattr("caelum.orchestrator.insert", insertion)
    core.state = "error"
    await core.handle("retry")
    work = core.work
    await core.handle("retry")
    assert core.work is work
    await work
    insertion.assert_awaited_once()


async def test_portable_history_off_copies_once_without_storage(core, monkeypatch):
    core.config.desktop.auto_copy = True
    core.config.desktop.history_enabled = False
    core.bindings.save_only = True
    copy = AsyncMock()
    monkeypatch.setattr("caelum.portable.copy_private_result", copy)
    core.on_completed = lambda *args: pytest.fail("private result reached history")
    await core.finalize(core.session)
    assert core.state == "copied"
    assert core.pcm is None
    await core.handle("retry")
    copy.assert_awaited_once_with("Private spoken words.")
    assert "Private spoken words" not in str(core.hud.events) + str(core.recent_metrics)


@pytest.mark.parametrize("backend", ["hyprland", "portable", "windows-failed", "windows-inserted"])
@pytest.mark.parametrize("history", [True, False])
async def test_auto_copy_off_preserves_clipboard_and_manual_delivery(core, monkeypatch, backend, history):
    core.config.desktop.auto_copy = False
    core.config.desktop.history_enabled = history
    core.on_completed = Mock()
    clipboard = AsyncMock()
    monkeypatch.setattr("caelum.portable.copy_private_result", clipboard)
    # Exercise the actual Hyprland insertion path: it must not run wl-copy or dispatch paste.
    command = AsyncMock()
    monkeypatch.setattr("caelum.linux.command", command)
    if backend == "portable":
        core.bindings.save_only = True
    elif backend.startswith("windows"):
        core.bindings.insert = AsyncMock(return_value=True, side_effect=(
            RuntimeError("Incomplete insertion") if backend == "windows-failed" else None
        ))
        core.bindings.copy_result = clipboard

    await core.finalize(core.session)
    status = await core.handle("status")
    command.assert_not_awaited()
    clipboard.assert_not_awaited()
    if backend.startswith("windows"):
        core.bindings.insert.assert_awaited_once_with("Private spoken words.", core.target, auto_copy=False)
    assert core.state == ("success" if backend == "windows-inserted" else "ready_to_copy")
    assert core.pcm is None
    assert "Private spoken words." not in str(status) + str(core.hud.events)
    if history:
        core.on_completed.assert_called_once_with(core.session, "Private spoken words.", core.metrics, True, False)
    else:
        core.on_completed.assert_not_called()
    if not history or backend != "windows-inserted":
        assert status["can_copy"]
        await core.handle("copy")
        clipboard.assert_awaited_once_with("Private spoken words.")
        core.provider.stt.assert_awaited_once()
        await core.handle("pause")
        assert not (await core.handle("status"))["can_copy"]


async def test_portable_history_off_clipboard_failure_retains_retry_audio(core, monkeypatch):
    core.config.desktop.auto_copy = True
    core.config.desktop.history_enabled = False
    core.bindings.save_only = True
    monkeypatch.setattr("caelum.portable.copy_private_result", AsyncMock(side_effect=OSError()))
    await core.finalize(core.session)
    assert core.state == "error"
    assert core.pcm is not None
    await core.cancel(feedback=False)


@pytest.mark.parametrize("portable", [False, True])
async def test_default_delivery_inserts_directly_with_history_and_clipboard_off(core, monkeypatch, portable):
    from caelum.field_input import Field
    from caelum.linux import Target

    core.config.desktop.history_enabled = False
    core.bindings.save_only = portable
    core.target = Target("0xabc", 15, 0, "", field=Field("id", ":1.5", "/entry", "/win"))
    direct, clipboard = AsyncMock(return_value=True), AsyncMock()
    monkeypatch.setattr("caelum.field_input.insert_field", direct)
    monkeypatch.setattr("caelum.portable.copy_private_result", clipboard)
    monkeypatch.setattr("caelum.linux.command", clipboard)
    monkeypatch.setattr("caelum.linux.hypr_json", AsyncMock(return_value={"address": "0xabc", "pid": 15}))
    await core.finalize(core.session)
    direct.assert_awaited_once_with("Private spoken words.", core.target.field)
    clipboard.assert_not_awaited()
    assert core.state == "success"
    assert not core.metrics.get("manual_copy")


@pytest.mark.parametrize("ending", ["stop", "toggle", "cancel", "pause", "limit", "error", "silence"])
async def test_media_pauses_before_capture_and_resumes_when_capture_ends(core, monkeypatch, ending):
    from unittest.mock import Mock

    order = []
    capture = SimpleNamespace(
        size=32000, speech_ms=0 if ending == "silence" else 100,
        level=0, history=[0] * 17, full=False, error=None, speaking=False,
        start=Mock(side_effect=lambda: order.append("capture-start")),
        stop=Mock(side_effect=lambda: order.append("capture-stop")),
        discard=Mock(), snapshot=Mock(return_value=b"audio"),
    )
    core.media.pause.side_effect = lambda: order.append("media-pause")
    core.media.resume.side_effect = lambda: order.append("media-resume")
    core.pcm = None
    core.finalize = AsyncMock()
    monkeypatch.setattr("caelum.orchestrator.Capture", lambda _: capture)
    monkeypatch.setattr("caelum.orchestrator.target_at_press", AsyncMock(return_value=core.target))
    await core.handle("start", "media-session")
    assert order == ["media-pause", "capture-start"]
    core.media.resume.assert_not_awaited()
    if ending in {"limit", "error"}:
        core.poll_task.cancel()
        await asyncio.gather(core.poll_task, return_exceptions=True)
        capture.full = ending == "limit"
        capture.error = "disconnected" if ending == "error" else None
        await core.poll()
    else:
        await core.handle("stop" if ending == "silence" else ending)
    if core.work:
        await core.work
    assert order == ["media-pause", "capture-start", "capture-stop", "media-resume"]
    assert core.capture is None


async def test_microphone_start_failure_restores_media(core, monkeypatch):
    from unittest.mock import Mock

    core.pcm = None
    capture = SimpleNamespace(
        start=Mock(side_effect=OSError("No microphone")), stop=Mock(), discard=Mock(),
    )
    monkeypatch.setattr("caelum.orchestrator.Capture", lambda _: capture)
    monkeypatch.setattr("caelum.orchestrator.target_at_press", AsyncMock(return_value=core.target))
    await core.handle("start", "failed-microphone")
    core.media.pause.assert_awaited_once()
    core.media.resume.assert_awaited_once()
    assert core.state == "error"
    assert core.capture is None


@pytest.mark.parametrize("at_start", [True, False], ids=["unavailable", "interrupted"])
async def test_in_app_microphone_notice_until_next_recording(core, monkeypatch, at_start):
    from unittest.mock import Mock

    from caelum.orchestrator import notify

    core.in_app_notifications = True
    core.pcm = None
    core.bindings.target = AsyncMock(return_value=core.target)
    capture = SimpleNamespace(
        start=Mock(side_effect=OSError() if at_start else None), stop=Mock(), discard=Mock(),
        history=[], level=0, error="disconnected",
    )
    monkeypatch.setattr("caelum.orchestrator.Capture", lambda _: capture)
    await core.handle("start", "broken-mic")
    if not at_start:
        await core.poll_task
    status = await core.handle("status")
    assert status["error_kind"] == ("microphone" if at_start else "capture")
    assert ("Caelum Settings" if at_start else "record again") in status["notice"]
    notify.assert_not_awaited()

    capture.start.side_effect = None
    await core.handle("start", "replacement-mic")
    assert "notice" not in await core.handle("status")
    await core.cancel()


async def test_feedback_failure_during_release_still_stops_capture_and_restores_media(core):
    from unittest.mock import Mock

    core.capture = SimpleNamespace(stop=Mock())
    capture = core.capture
    core.hud.emit = AsyncMock(side_effect=RuntimeError("HUD closed"))
    with pytest.raises(RuntimeError, match="HUD closed"):
        await core.release()
    capture.stop.assert_called_once()
    core.media.resume.assert_awaited_once()


async def test_local_models_never_enter_online_chunker(core, monkeypatch):
    core.pcm = None
    core.config.stt.engine, core.config.stt.local_model = "local", "parakeet-v3"
    core.config.app.strategy = "chunked"
    core.bindings.target = AsyncMock(return_value=core.target)
    capture = SimpleNamespace(start=lambda: None, stop=lambda: None, discard=lambda: None)
    monkeypatch.setattr("caelum.orchestrator.Capture", lambda _: capture)
    monkeypatch.setattr("caelum.orchestrator.Chunker", lambda *_: pytest.fail("Online chunker used for local model"))
    core.poll = AsyncMock()
    await core.handle("start", "local-capture")
    assert core.chunker is None
    await core.cancel(feedback=False)


async def test_status_remains_responsive_while_loading_holds_control_lock(core):
    async with core.control_lock:
        status = await asyncio.wait_for(core.handle("status"), 0.1)
        assert status["state"] == core.state
