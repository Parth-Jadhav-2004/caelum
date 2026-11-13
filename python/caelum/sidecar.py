"""Versioned JSON-lines desktop boundary. stdout is protocol only, never diagnostics."""

import asyncio
import json
import os
import signal
import sys
import threading
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path

from . import credentials
from .config import config_path, load, save
from .desktop_services import connection_status, microphones, request, service_presentation
from .history import History
from .onboarding import (
    PRIVACY,
    Progress,
    check_shortcut,
    practice,
    record_sample,
    validate_providers,
)

VERSION = 1
MAX_FRAME = 1_048_576


class Backend:
    def __init__(self, path=None, emit=lambda event, data: None):
        self.path = Path(path or os.environ.get("CAELUM_CONFIG") or config_path())
        self.history = History(self.path)
        self.process = None
        self.emit = emit
        self.cancelled = threading.Event()
        self.sample_lock = asyncio.Lock()
        self.mutation_lock = asyncio.Lock()
        self.update = None
        self.setup_checks = set()

    async def status(self):
        try:
            value = await asyncio.to_thread(request, "status")
            value["running"] = True
        except (FileNotFoundError, ConnectionRefusedError):
            value = {"running": False, "state": "hidden", "paused": False}
        title, detail = service_presentation(value if value["running"] else None)
        return {**value, "title": title, "detail": detail}

    async def idle(self):
        status = await self.status()
        if status.get("pending_audio") or status.get("state") in {
            "starting",
            "listening",
            "recording",
            "processing",
            "refining",
        }:
            raise RuntimeError("Finish dictation or discard pending audio first")

    async def start(self):
        if (await self.status())["running"]:
            return
        if self.process and self.process.returncode is None:
            raise RuntimeError("Service is still starting")
        args = [sys.executable, "-m", "caelum.cli", "--config", str(self.path), "serve"]
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdout=sys.stderr,
            stderr=sys.stderr,
            env={**os.environ, "CAELUM_OWNER_PID": str(os.getpid())},
        )
        for _ in range(100):
            await asyncio.sleep(0.1)
            if (await self.status())["running"]:
                return
            if self.process.returncode is not None:
                raise RuntimeError("Service could not start; check provider key and desktop access")
        await self.stop()
        raise RuntimeError("Service startup timed out; run caelum doctor")

    async def stop(self):
        with suppress(OSError, RuntimeError):
            await asyncio.to_thread(request, "shutdown")
        if self.process and self.process.returncode is None:
            try:
                await asyncio.wait_for(self.process.wait(), 8)
            except TimeoutError:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 2)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        self.process = None

    async def dispatch(self, method, params):
        config = load(self.path)
        if method == "bootstrap":
            from .launcher import entry_path

            return {
                "version": VERSION,
                "config": asdict(config),
                "privacy": PRIVACY,
                "setup": asdict(Progress.load(self.path)),
                "autostart": entry_path(True).exists(),
                "credentials": {
                    name: credentials.describe(name)
                    for name in {config.stt.key_env, config.cleanup.key_env}
                },
            }
        if method == "status":
            return await self.status()
        if method == "devices":
            return [
                {"label": label, "value": value}
                for label, value in await asyncio.to_thread(microphones)
            ]
        if method == "history":
            return await asyncio.to_thread(self.history.read, str(params.get("query", "")))
        if method == "summary":
            return await asyncio.to_thread(self.history.summary)
        if method == "history.delete":
            await asyncio.to_thread(self.history.delete, params.get("id"))
        elif method == "history.export":
            await asyncio.to_thread(self.history.export, Path(params["path"]))
        elif method == "service.start":
            if self.sample_lock.locked():
                raise RuntimeError("Finish the microphone test first")
            await self.start()
        elif method == "service.stop":
            if not params.get("discard"):
                await self.idle()
            await self.stop()
        elif method == "control":
            action = params.get("action")
            if self.sample_lock.locked() and action in {"start", "retry"}:
                raise RuntimeError("Finish the microphone test first")
            if action not in {"start", "stop", "retry", "cancel", "pause", "resume"}:
                raise ValueError("Unknown recording action")
            if action == "pause" and not params.get("discard"):
                await self.idle()
            return await asyncio.to_thread(request, action)
        elif method == "settings.save":
            # Read current defaults to preserve values the frontend does not edit.
            data = params["config"]
            if not isinstance(data, dict) or set(data) - {"app", "stt", "cleanup", "desktop"}:
                raise ValueError("Invalid configuration")
            for section, values in data.items():
                target = getattr(config, section)
                for key, value in values.items():
                    if key not in asdict(target):
                        raise ValueError("Unknown configuration option")
                    setattr(target, key, value)
            previous = load(self.path)
            await asyncio.to_thread(save, config, self.path)
            if config.stt != previous.stt or config.cleanup != previous.cleanup:
                self.setup_checks.discard("provider")
                self.setup_checks.discard("practice")
            if "app" in data:
                # Invalidate only checks affected by changed configuration.
                if previous.app.microphone != config.app.microphone:
                    self.setup_checks.discard("microphone")
                    self.setup_checks.discard("practice")
                if previous.app.hotkey != config.app.hotkey:
                    self.setup_checks.discard("shortcut")
            if (await self.status())["running"]:
                try:
                    await asyncio.to_thread(request, "reload")
                except (RuntimeError, OSError) as error:
                    return {"saved": True, "warning": f"Saved; service not updated: {error}"}
            return {"saved": True}
        elif method == "providers.check":
            return await connection_status(config)
        elif method == "credentials.store":
            name = params["name"]
            value = params.get("value")
            if not isinstance(value, str) or not value or any(c.isspace() for c in value):
                raise ValueError("Enter a nonempty provider key without whitespace")
            if name not in {config.stt.key_env, config.cleanup.key_env}:
                raise ValueError("Credential is not used by configured providers")
            # Validate without persisting the entered secret. Providers read env fallback.
            from .providers import Providers

            client = Providers(
                config,
                credential_resolver=lambda key: (
                    params["value"] if key == name else credentials.get(key)
                ),
            )
            try:
                for provider in (config.stt, config.cleanup):
                    if provider.key_env == name and provider.model:
                        if provider.model not in await client.models(provider):
                            raise ValueError("Configured model unavailable")
            finally:
                await client.client.aclose()
            return await asyncio.to_thread(credentials.store, name, params["value"])
        elif method == "credentials.delete":
            if params["name"] not in {config.stt.key_env, config.cleanup.key_env}:
                raise ValueError("Credential is not used by configured providers")
            await asyncio.to_thread(credentials.delete, params["name"])
        elif method == "setup.validate":
            if params.get("consent") is not True:
                raise ValueError("Provider-processing consent is required")
            keys = params.get("keys", {})
            allowed = {config.stt.key_env, config.cleanup.key_env}
            if (
                not isinstance(keys, dict)
                or set(keys) - allowed
                or any(
                    not isinstance(value, str) or not value or any(c.isspace() for c in value)
                    for value in keys.values()
                )
            ):
                raise ValueError("Enter valid provider keys without whitespace")
            self.cancelled.clear()
            validation = asyncio.create_task(
                validate_providers(
                    config, credential_resolver=lambda name: keys.get(name) or credentials.get(name)
                )
            )
            try:
                while not validation.done():
                    if self.cancelled.is_set():
                        raise RuntimeError("Validation cancelled; keys were not saved")
                    await asyncio.sleep(0.05)
                await validation
                if self.cancelled.is_set():
                    raise RuntimeError("Validation cancelled; keys were not saved")
                stored = {}
                for name, value in keys.items():
                    stored[name] = await asyncio.to_thread(credentials.store, name, value)
                self.setup_checks.add("provider")
                return {"storage": stored}
            finally:
                validation.cancel()
                await asyncio.gather(validation, return_exceptions=True)
        elif method == "shortcut.check":
            result = await check_shortcut(config)
            self.setup_checks.add("shortcut")
            return result
        elif method in {"microphone.test", "practice"}:
            await self.idle()
            if self.sample_lock.locked():
                raise RuntimeError("A microphone test is already running")
            async with self.sample_lock:
                self.cancelled.clear()
                if method == "practice" and params.get("consent") is not True:
                    raise ValueError("Explicit audio upload consent is required")
                pcm = await asyncio.to_thread(
                    record_sample,
                    config,
                    5 if method == "practice" else 3,
                    self.cancelled,
                    lambda level: self.emit("microphone", {"level": level}),
                )
                if not pcm:
                    raise RuntimeError("No speech detected. Try again")
                if method == "practice":
                    text, refined = await practice(config, pcm, self.cancelled)
                    self.setup_checks.add("practice")
                    return {"text": text, "refined": refined}
                self.setup_checks.add("microphone")
        elif method == "sample.cancel":
            self.cancelled.set()
        elif method == "setup.finish":
            if self.setup_checks != {"provider", "microphone", "shortcut", "practice"}:
                raise ValueError("Validate providers, microphone, shortcut, and practice first")
            Progress(4, True).save(self.path)
            await self.start()
        elif method == "launcher":
            from .launcher import install

            return str(
                await asyncio.to_thread(
                    install, self.path, params.get("autostart", False), params.get("enabled", True)
                )
            )
        elif method == "updates.check":
            from .updates import check

            self.update = await asyncio.to_thread(check)
            return {"version": self.update["version"]} if self.update else None
        elif method == "updates.stage":
            from .updates import stage

            await self.idle()
            if not self.update:
                raise ValueError("Check for updates first")
            return await asyncio.to_thread(stage, self.update)
        elif method == "updates.apply":
            from .desktop_services import install_queued_update

            await self.idle()
            return await asyncio.to_thread(install_queued_update)
        elif method == "updates.discard":
            from .updates import discard_pending

            await asyncio.to_thread(discard_pending)
        elif method == "updates.pending":
            from .updates import cache_dir

            return (cache_dir() / "pending").is_dir()
        elif method == "shutdown":
            if not params.get("discard"):
                await self.idle()
            await self.stop()
        else:
            raise ValueError("Unknown method")
        return {"ok": True}


async def run():
    loop = asyncio.get_running_loop()

    def emit(event, data):
        frame = json.dumps({"v": VERSION, "event": event, "data": data}, allow_nan=False)
        loop.call_soon_threadsafe(lambda: print(frame, flush=True))

    backend = Backend(emit=emit)
    tasks = set()
    reader = asyncio.StreamReader(limit=MAX_FRAME)
    protocol = asyncio.StreamReaderProtocol(reader)
    transport, _ = await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, transport.close)

    async def respond(message):
        identifier = message.get("id")
        try:
            if message.get("v") != VERSION or type(identifier) is not int:
                raise ValueError("Unsupported protocol version or request ID")
            method, params = message["method"], message.get("params", {})
            if not isinstance(method, str) or not isinstance(params, dict):
                raise ValueError("Invalid request envelope")
            if method in {
                "status",
                "history",
                "summary",
                "devices",
                "microphone.test",
                "practice",
                "sample.cancel",
            }:
                result = await backend.dispatch(method, params)
            else:
                async with backend.mutation_lock:
                    result = await backend.dispatch(method, params)
            frame = json.dumps({"v": VERSION, "id": identifier, "result": result}, allow_nan=False)
            if len(frame.encode()) > 16 * MAX_FRAME:
                raise ValueError("Result is too large; narrow your history search")
            print(frame, flush=True)
        except Exception as error:
            # Only explicit application errors cross IPC, never HTTP bodies or traceback.
            detail = (
                str(error)
                if isinstance(error, (ValueError, RuntimeError))
                else "Operation failed; check local permissions and desktop access"
            )
            print(json.dumps({"v": VERSION, "id": identifier, "error": detail}), flush=True)

    async def events():
        while True:
            try:
                emit("status", await backend.status())
            except Exception:
                emit("status-error", {"message": "Service status unavailable. Retrying…"})
            await asyncio.sleep(0.1)

    watcher = asyncio.create_task(events())
    try:
        while line := await reader.readline():
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    continue
            except ValueError:
                continue
            if len(tasks) >= 64:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            task = asyncio.create_task(respond(message))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
    finally:
        backend.cancelled.set()
        watcher.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await backend.stop()
        transport.close()


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
