"""One authoritative session, bounded retry memory, cancellable asynchronous work."""

import asyncio
import inspect
import json
import time
import uuid
from contextlib import suppress

from .audio import RATE, Capture
from .linux import (
    insert,
    notify,
    recovery_notification,
    session_locked,
    target_at_press,
    wayland_env,
)
from .providers import ProviderError
from .segmenter import Chunker


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
    def __init__(self, config, provider, hud, bindings):
        self.config, self.provider, self.hud, self.bindings = config, provider, hud, bindings
        self.session = None
        self.state = "hidden"
        self.sequence = 0
        self.capture = None
        self.pcm = None
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
        self.error_kind = ""

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
        await self.hud.emit(
            {
                "session_id": self.session or "idle",
                "sequence": self.sequence,
                "state": self.state,
                "elapsed_ms": int((time.monotonic() - self.started) * 1000),
                "level": capture.level if capture else 0,
                "history": history,
                "output": self.target.output if self.target else "",
                "error_code": error_code,
            }
        )

    async def handle(self, action, token="", address=None):
        async with self.control_lock:
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
                self.sequence = 0
                self.token = token
                self.started = time.monotonic()
                self.failed_at = None
                self.target = await getattr(self.bindings, "target", target_at_press)(address)
                self.provider.reset_metrics()
                self.metrics = {}
                await self.event("starting")
                await self.bindings.active(True)
                self.capture = Capture(self.config.app)
                try:
                    await asyncio.to_thread(self.capture.start)
                    await self.event("listening")
                except Exception:
                    await self.abort_capture()
                    await self.event("error", "microphone")
                    await self.bindings.active(False)
                    await notify(
                        "Microphone unavailable. Run caelum devices and caelum doctor; check microphone configuration."
                    )
                    return
                self.chunker = (
                    Chunker(self.provider, self.config.stt)
                    if self.config.app.strategy == "chunked"
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
            elif action == "retry" and self.pcm is not None and self.state == "error":
                # Reserve the retry before scheduling work: two queued UI clicks
                # must not create concurrent finalization tasks.
                self.state = "processing"
                if self.expiry:
                    self.expiry.cancel()
                self.work = asyncio.create_task(self.finalize(self.session))
            elif action == "pause":
                await self.cancel()
                self.paused = True
            elif action == "resume":
                self.paused = False
            elif action == "status":
                return {
                    "paused": self.paused,
                    "state": self.state,
                    "pending_audio": self.pcm is not None,
                    "error_kind": self.error_kind,
                    "metrics": self.recent_metrics[-1:],
                }

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
                    await notify(
                        "Capture interrupted; no text inserted. Check the microphone and record again."
                    )
                    return
                if capture.full:
                    async with self.control_lock:
                        if self.capture:
                            await self.release()
                    await notify("Recording reached its configured limit and was finalized.")
                    return
                if self.chunker:
                    self.chunker.feed(capture.snapshot, capture.size // 2)
                await self.event("recording" if capture.speaking else "listening")
                await asyncio.sleep(1 / 30)
        except (RuntimeError, BrokenPipeError, TimeoutError, ConnectionError):
            await self.cancel(feedback=False)
            await notify(
                "Recording stopped because the feedback pill is unavailable. Restart Caelum."
            )

    async def abort_capture(self):
        if self.capture:
            capture, self.capture = self.capture, None
            await asyncio.to_thread(capture.stop)
            capture.discard()

    async def release(self):
        capture, self.capture = self.capture, None
        if not capture:
            return
        self.released = time.monotonic()
        # Immediately freeze the presentation; closing PortAudio runs off the event loop.
        await self.event("processing")
        await asyncio.to_thread(capture.stop)
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

    async def finalize(self, session):
        try:
            async with asyncio.timeout(
                self.config.stt.timeout_seconds * 2 + self.config.cleanup.timeout_seconds + 5
            ):
                await self.event("processing")
                began = time.monotonic()
                raw = (
                    await self.chunker.finish(self.pcm)
                    if self.chunker
                    else (await self.provider.stt(self.pcm)).text
                )
                self.metrics["remaining_stt_ms"] = (time.monotonic() - began) * 1000
                if not raw:
                    self.pcm = None
                    await self.event("no_speech")
                    await self.bindings.active(False)
                    return
                text, refined = await self.provider.cleanup(raw, lambda: self.event("refining"))
                if session != self.session:
                    return
                await self.event("processing")
                began = time.monotonic()
                if await getattr(self.bindings, "locked", session_locked)():
                    await self.cancel()
                    return
                if getattr(self.bindings, "save_only", False):
                    self.metrics.update(self.provider.metrics)
                    self.metrics["release_to_dispatch_ms"] = (
                        time.monotonic() - self.released
                    ) * 1000
                    self.metrics["manual_copy"] = True
                    self.metrics["clipboard_fallback"] = False
                    self.metrics["visible_insertion_observed"] = False
                    if not self.on_completed:
                        raise RuntimeError("History storage is required for portable delivery")
                    result = self.on_completed(session, text, self.metrics.copy(), refined, False)
                    if inspect.isawaitable(result):
                        result = await result
                    if result is False:
                        raise RuntimeError("Could not save dictation")
                    self.recent_metrics.append(self.metrics.copy())
                    self.recent_metrics = self.recent_metrics[-100:]
                    self.pcm = self.chunker = self.failed_at = None
                    await self.bindings.active(False)
                    await self.event("saved")
                    return
                try:
                    dispatched = await insert(text, self.target)
                except (RuntimeError, OSError, TimeoutError):
                    # Retain audio for explicit retry if even clipboard dispatch fails.
                    raise ProviderError("Insertion unavailable; retry or cancel") from None
                self.metrics.update(self.provider.metrics)
                self.metrics["insertion_dispatch_ms"] = (time.monotonic() - began) * 1000
                self.metrics["release_to_dispatch_ms"] = (time.monotonic() - self.released) * 1000
                self.metrics["visible_insertion_observed"] = False
                self.metrics["clipboard_fallback"] = not dispatched
                self.recent_metrics.append(self.metrics.copy())
                self.recent_metrics = self.recent_metrics[-100:]
                self.pcm = None
                self.chunker = None
                self.failed_at = None
                await self.bindings.active(False)
                await self.event(
                    ("success" if refined else "unrefined") if dispatched else "copied"
                )
                if self.on_completed:
                    with suppress(Exception):
                        self.on_completed(
                            session, text, self.metrics.copy(), refined, not dispatched
                        )
                if not dispatched:
                    await notify(
                        "Target focus changed. Text copied; paste manually in the intended application."
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
            await self.event("error", "network")
            self.error_kind = error.kind if isinstance(error, ProviderError) else "unavailable"
            if isinstance(error, ProviderError):
                with suppress(RuntimeError, OSError, TimeoutError):
                    await notify(str(error))
            remaining = self.config.app.retry_expiry_seconds - (time.monotonic() - self.failed_at)
            self.expiry = asyncio.create_task(self.expire(session, max(0, remaining)))
            self.recovery_task = asyncio.create_task(
                recovery_notification(self, session, max(0, remaining))
            )

    async def expire(self, session, seconds):
        await asyncio.sleep(seconds)
        async with self.control_lock:
            if session == self.session and self.pcm is not None:
                await self.cancel()
                await notify("Retry window expired. Pending audio discarded; record again.")

    async def cancel(self, feedback=True):
        self.session = uuid.uuid4().hex  # invalidate every late callback
        current = asyncio.current_task()
        for task in (self.work, self.poll_task, self.expiry, self.recovery_task):
            if task and task is not current and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        if self.chunker:
            self.chunker.cancel()
        await self.abort_capture()
        self.chunker, self.pcm, self.failed_at = None, None, None
        await self.bindings.active(False)
        if feedback:
            await self.event("hidden")
        self.state = "hidden"
