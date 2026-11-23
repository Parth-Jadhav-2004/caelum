"""One authoritative session, bounded retry memory, cancellable asynchronous work."""

import asyncio
import inspect
import json
import time
import uuid
from contextlib import suppress

from .audio import RATE, Capture
from .linux import (
    Target,
    insert,
    notify,
    recovery_notification,
    session_locked,
    target_at_press,
    wayland_env,
)
from .media import RecordingMedia
from .providers import ProviderError
from .segmenter import Chunker

WINDOWS_COPIED_NOTICE = (
    "Your transcript was copied to the clipboard. Switch to the intended app and press Ctrl+V."
)


async def cancel_tasks(*tasks):
    current = asyncio.current_task()
    for task in tasks:
        if task and task is not current and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


class HUD:
    def __init__(self, config):
        self.config = config
        self.process = None

    async def start(self):
        import sys

        args = [sys.executable, "-m", "caelum.hud"]
        if self.config.reduced_motion:
            args.append("--reduced-motion")
        if self.config.high_contrast:
            args.append("--high-contrast")
        self.process = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, env=wayland_env()
        )
        if await asyncio.wait_for(self.process.stdout.readline(), 5) != b"ready\n":
            raise RuntimeError("Native Wayland recording HUD failed to initialize")

    async def emit(self, message):
        if not self.process or self.process.returncode is not None:
            raise RuntimeError("HUD unavailable")
        self.process.stdin.write(json.dumps(message).encode() + b"\n")
        await asyncio.wait_for(self.process.stdin.drain(), 0.25)

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 2)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()


class Orchestrator:
    def __init__(self, config, provider, hud, bindings, *, in_app_notifications=False):
        self.config, self.provider, self.hud, self.bindings = config, provider, hud, bindings
        self.in_app_notifications = in_app_notifications
        self.notice = None
        self.session = None
        self.state = "hidden"
        self.sequence = 0
        self.capture = None
        self.pcm = None
        self.pending_copy = None
        self.manual_result = None
        self.chunker = None
        self.work = None
        self.expiry = None
        self.recovery_task = None
        self.started = 0
        self.released = 0
        self.failed_at = None
        self.token = ""
        self.target = None
        self.metrics = {}
        self.recent_metrics = []  # numeric only, bounded, in-memory
        self.early_stops = set()
        self.accepted_tokens = set()
        self.control_lock = asyncio.Lock()
        self.poll_task = None
        self.on_completed = None
        self.paused = False
        self.stopping = False
        self.error_kind = ""
        self.feedback = {}
        self.media = RecordingMedia()

    async def notify(self, message):
        if self.in_app_notifications:
            self.notice = message
        else:
            await notify(message)

    async def event(self, state=None, error_code=""):
        if state:
            self.state = state
            self.error_kind = error_code if state == "error" else ""
        self.sequence += 1
        capture = self.capture
        history = (
            list(capture.history)
            if capture and self.state in ("listening", "recording")
            else [0] * 17
        )
        self.feedback = {
                "session_id": self.session or "idle",
                "sequence": self.sequence,
                "state": self.state,
                "elapsed_ms": int((time.monotonic() - self.started) * 1000),
                "level": capture.level if capture else 0,
                "history": history,
                "output": self.target.output if self.target else "",
                "error_code": error_code,
            }
        await self.hud.emit(self.feedback)

    async def handle(self, action, token="", address=None):
        # Native model staging can hold the control lock for seconds. Status is
        # read-only and must remain available to the sidecar throughout loading.
        if action == "status":
            return {
                "feedback": self.feedback, "paused": self.paused, "state": self.state,
                "pending_audio": self.pcm is not None, "error_kind": self.error_kind,
                "can_copy": self.manual_result is not None,
                "metrics": self.recent_metrics[-1:],
                **({"notice": self.notice} if self.notice else {}),
            }
        async with self.control_lock:
            if self.stopping and action != "status":
                return
            if action == "toggle":
                action = "stop" if self.capture else "start"
                token = ""
            if action == "start":
                if self.paused:
                    return
                token = token or f"manual-{time.monotonic_ns()}"
                if token in self.accepted_tokens:
                    if (
                        not self.capture
                        and self.pcm is None
                        and not (self.work and not self.work.done())
                    ):
                        await self.bindings.active(False)
                    return
                self.accepted_tokens.add(token)
                if len(self.accepted_tokens) > 1024:
                    self.accepted_tokens = {token}
                if self.capture or self.work and not self.work.done() or self.pcm is not None:
                    return
                if await getattr(self.bindings, "locked", session_locked)():
                    await self.bindings.active(False)
                    return
                self.session = uuid.uuid4().hex
                self.notice = None
                self.manual_result = None
                self.sequence = 0
                self.token = token
                self.started = time.monotonic()
                self.failed_at = None
                self.target = await getattr(self.bindings, "target", target_at_press)(address)
                self.provider.reset_metrics()
                self.metrics = {}
                await self.event("starting")
                await self.bindings.active(True)
                # Do not delay opening the microphone while desktop apps answer.
                field_lookup = None
                if not self.config.desktop.auto_copy and isinstance(self.target, Target):
                    field_lookup = asyncio.create_task(self.target.remember_field(
                        portable=getattr(self.bindings, "save_only", False)
                    ))
                try:
                    await self.media.pause()
                    self.capture = Capture(self.config.app)
                    await asyncio.to_thread(self.capture.start)
                    await self.event("listening")
                    if field_lookup:
                        await field_lookup
                except Exception:
                    await self.abort_capture()
                    await self.event("error", "microphone")
                    await self.bindings.active(False)
                    await self.notify(
                        "Microphone unavailable. Choose a microphone in Caelum Settings and test it."
                        if self.in_app_notifications else
                        "Microphone unavailable. Run caelum devices and caelum doctor; check microphone configuration."
                    )
                    return
                finally:
                    await cancel_tasks(field_lookup)
                self.chunker = (
                    Chunker(self.provider, self.config.stt)
                    if self.config.app.strategy == "chunked"
                    and self.config.stt.fallback == "none"
                    and self.config.stt.engine == "online"
                    else None
                )
                self.poll_task = asyncio.create_task(self.poll())
                if token in self.early_stops:
                    self.early_stops.discard(token)
                    await self.release()
            elif action == "stop":
                if self.capture and (not token or token == self.token):
                    await self.release()
                elif token not in self.accepted_tokens:
                    if len(self.early_stops) < 1024:
                        self.early_stops.add(token)
            elif action == "cancel":
                if token:
                    self.accepted_tokens.add(token)
                await self.cancel()
            elif action == "retry" and self.pcm is not None and self.state in ("error", "missing_model"):
                # Reserve the retry before scheduling work: two queued UI clicks
                # must not create concurrent finalization tasks.
                self.state = "processing"
                self.notice = None
                # The failed finalizer may still be posting its error notice.
                # Stop it before it can install a late expiry or recovery prompt.
                await cancel_tasks(self.work, self.expiry, self.recovery_task)
                self.expiry = self.recovery_task = None
                self.work = asyncio.create_task(self.finalize(self.session))
            elif action == "pause":
                await self.cancel()
                self.paused = True
            elif action == "resume":
                self.paused = False
            elif action == "copy":
                if self.manual_result is None or await getattr(self.bindings, "locked", session_locked)():
                    raise ProviderError("No finished transcript available to copy.", "clipboard")
                from .portable import copy_private_result

                try:
                    await getattr(self.bindings, "copy_result", copy_private_result)(self.manual_result)
                except (RuntimeError, OSError, TimeoutError):
                    raise ProviderError("Clipboard unavailable. Try Copy transcript again.", "clipboard") from None
                if self.in_app_notifications:
                    await self.notify(WINDOWS_COPIED_NOTICE)

    async def poll(self):
        try:
            while self.capture:
                capture = self.capture
                if capture.error:
                    await self.abort_capture()
                    if self.chunker:
                        self.chunker.cancel()
                    await self.event("error", "capture")
                    await self.bindings.active(False)
                    await self.notify(
                        "Capture interrupted; no text inserted. Check the microphone and record again."
                    )
                    return
                if capture.full:
                    async with self.control_lock:
                        if self.capture:
                            await self.release()
                    await self.notify("Recording reached its configured limit and was finalized.")
                    return
                if self.chunker:
                    self.chunker.feed(capture.snapshot, capture.size // 2)
                await self.event("recording" if capture.speaking else "listening")
                await asyncio.sleep(1 / 30)
        except (RuntimeError, BrokenPipeError, TimeoutError, ConnectionError):
            await self.cancel(feedback=False)
            await self.notify(
                "Recording stopped because the feedback pill is unavailable. Restart Caelum."
            )

    async def abort_capture(self):
        try:
            if self.capture:
                capture, self.capture = self.capture, None
                try:
                    await asyncio.to_thread(capture.stop)
                finally:
                    capture.discard()
        finally:
            await self.media.resume()

    async def release(self):
        capture, self.capture = self.capture, None
        if not capture:
            return
        self.released = time.monotonic()
        # Immediately freeze the presentation; closing PortAudio runs off the event loop.
        try:
            await self.event("processing")
        finally:
            try:
                await asyncio.to_thread(capture.stop)
            finally:
                await self.media.resume()
        duration = capture.size / (RATE * 2)
        self.metrics["capture_ms"] = duration * 1000
        if duration * 1000 < self.config.app.minimum_recording_ms:
            capture.discard()
            await self.cancel()
            return
        if capture.speech_ms < 80:
            capture.discard()
            if self.chunker:
                self.chunker.cancel()
            await self.event("no_speech")
            await self.bindings.active(False)
            return
        self.pcm = capture.snapshot()
        capture.discard()
        self.work = asyncio.create_task(self.finalize(self.session))

    async def finished_transcript(self):
        if self.pending_copy is not None:
            return self.pending_copy
        began = time.monotonic()
        raw = (
            await self.chunker.finish(self.pcm)
            if self.chunker
            else (await self.provider.stt(self.pcm)).text
        )
        self.metrics["remaining_stt_ms"] = (time.monotonic() - began) * 1000
        if raw:
            return await self.provider.cleanup(raw, lambda: self.event("refining"))
        return None

    async def deliver(self, transcript):
        text, _ = transcript
        auto_copy = self.config.desktop.auto_copy
        if getattr(self.bindings, "save_only", False):
            if not auto_copy:
                from .field_input import insert_field

                if await insert_field(text, getattr(self.target, "field", None)):
                    return "inserted"
                return "ready_to_copy"
            if self.config.desktop.history_enabled:
                return "saved"
            from .portable import copy_private_result

            await copy_private_result(text)
            return "copied"
        try:
            if self.pending_copy is not None:
                await self.bindings.copy_result(text)
                return "copied"
            if await getattr(self.bindings, "insert", insert)(text, self.target, auto_copy=auto_copy):
                return "inserted"
        except (RuntimeError, OSError, TimeoutError):
            if not auto_copy:
                return "ready_to_copy"
            if hasattr(self.bindings, "copy_result"):
                self.pending_copy = transcript
                raise ProviderError("Choose Retry to copy the finished text.", "clipboard") from None
            raise ProviderError("Insertion unavailable; retry or cancel") from None
        return "copied" if auto_copy else "ready_to_copy"

    async def finalize(self, session):
        try:
            async with asyncio.timeout(
                (self.config.stt.local_timeout_seconds if self.config.stt.engine == "local"
                 or self.config.stt.fallback == "local"
                 else self.config.stt.timeout_seconds) * 2 + self.config.cleanup.timeout_seconds + 5
            ):
                await self.event("processing")
                transcript = await self.finished_transcript()
                if session != self.session:
                    return
                if transcript is None:
                    self.pcm = None
                    await self.event("no_speech")
                    await self.bindings.active(False)
                    return
                text, refined = transcript
                await self.event("processing")
                began = time.monotonic()
                if await getattr(self.bindings, "locked", session_locked)():
                    await self.cancel()
                    return
                delivery = await self.deliver(transcript)
                portable = getattr(self.bindings, "save_only", False)
                copied = delivery == "copied" and not portable
                self.metrics.update(self.provider.metrics)
                if portable and delivery != "inserted":
                    self.metrics["manual_copy"] = True
                else:
                    self.metrics["insertion_dispatch_ms"] = (time.monotonic() - began) * 1000
                self.metrics["release_to_dispatch_ms"] = (time.monotonic() - self.released) * 1000
                self.metrics["visible_insertion_observed"] = False
                self.metrics["clipboard_fallback"] = copied
                if delivery == "ready_to_copy" or (
                    not self.config.desktop.auto_copy and not self.config.desktop.history_enabled
                ):
                    self.manual_result = text
                if delivery == "saved":
                    if not self.on_completed:
                        raise RuntimeError("History storage is required for portable delivery")
                    result = self.on_completed(session, text, self.metrics.copy(), refined, False)
                    if inspect.isawaitable(result):
                        result = await result
                    if result is False:
                        raise RuntimeError("Could not save dictation")
                elif self.on_completed and self.config.desktop.history_enabled:
                    with suppress(Exception):
                        self.on_completed(session, text, self.metrics.copy(), refined, copied)
                self.recent_metrics.append(self.metrics.copy())
                self.recent_metrics = self.recent_metrics[-100:]
                self.pending_copy = self.pcm = self.chunker = self.failed_at = None
                await self.bindings.active(False)
                await self.event(
                    ("success_fallback_" + self.provider.metrics["fallback"]
                     if self.provider.metrics.get("fallback") else
                     ("success" if refined else "unrefined")) if delivery == "inserted" else delivery
                )
                if delivery == "copied":
                    await self.notify(
                        WINDOWS_COPIED_NOTICE if self.in_app_notifications else
                        "Text copied. Paste manually; history saving is off." if portable else
                        "Text copied. Paste manually in the intended application."
                    )
                elif delivery == "ready_to_copy" and self.in_app_notifications:
                    await self.notify(
                        "Automatic copy is off. Choose Copy transcript in Caelum, "
                        "then switch to the intended app and press Ctrl+V."
                    )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if session != self.session:
                return
            if self.chunker:
                self.chunker.cancel()
                self.chunker = None
            self.failed_at = self.failed_at or time.monotonic()
            self.error_kind = error.kind if isinstance(error, ProviderError) else "unavailable"
            await self.event(
                "missing_model" if self.error_kind == "missing_model" else "error",
                "missing_model" if self.error_kind == "missing_model" else
                "clipboard" if self.error_kind == "clipboard" else
                "local_setup" if self.error_kind == "local_setup" else
                "local_decode" if self.config.stt.engine == "local" else "network",
            )
            self.error_kind = error.kind if isinstance(error, ProviderError) else "unavailable"
            if isinstance(error, ProviderError):
                with suppress(RuntimeError, OSError, TimeoutError):
                    await self.notify(str(error))
            remaining = self.config.app.retry_expiry_seconds - (time.monotonic() - self.failed_at)
            self.expiry = asyncio.create_task(self.expire(session, max(0, remaining)))
            if not self.in_app_notifications:  # The dashboard already offers Retry and Discard.
                self.recovery_task = asyncio.create_task(
                    recovery_notification(self, session, max(0, remaining))
                )

    async def expire(self, session, seconds):
        await asyncio.sleep(seconds)
        async with self.control_lock:
            if session == self.session and self.pcm is not None:
                await self.cancel()
                await self.notify("Retry window expired. Pending audio discarded; record again.")

    async def cancel(self, feedback=True):
        self.notice = None
        self.session = uuid.uuid4().hex  # invalidate every late callback
        await cancel_tasks(self.work, self.poll_task, self.expiry, self.recovery_task)
        if self.chunker:
            self.chunker.cancel()
        await self.abort_capture()
        self.chunker = self.pcm = self.pending_copy = self.manual_result = self.failed_at = None
        await self.bindings.active(False)
        if feedback:
            await self.event("hidden")
        self.state = "hidden"
