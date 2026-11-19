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
from .desktop_services import (
    SettingsBusy,
    connection_status,
    microphones,
    request,
    service_presentation,
)
from .hardware import detect
from .history import History
from .ipc_contract import METHODS, error_payload, matches, validate_request
from .models import ModelManager, get_model, installed, models_dir, verify
from .onboarding import (
    Progress,
    check_shortcut,
    practice,
    privacy,
    record_sample,
    setup_fingerprint,
    validate_providers,
)

VERSION = 1
MAX_FRAME = 1_048_576


class Backend:
    def __init__(self, path=None, emit=lambda event, data: None):
        self.path = Path(path or os.environ.get("CAELUM_CONFIG") or config_path())
        self.history = History(self.path)
        self.process = None
        self.service_task = None
        self.emit = emit
        self.cancelled = threading.Event()
        self.sample_lock = asyncio.Lock()
        self.sample_finished = threading.Event()
        self.mutation_lock = asyncio.Lock()
        self.model_feedback_lock = asyncio.Lock()
        self.update = None
        self.setup_checks = set()
        self.shutdown_complete = False
        progress = Progress.load(self.path)
        if progress.fingerprint == setup_fingerprint(load(self.path)):
            self.setup_checks.update(progress.checks)
        self.models = ModelManager(progress=self.model_progress)
        self.pending_model = None
        try:
            self.pending_model = json.loads((models_dir() / "pending-use.json").read_text())["id"]
            get_model(self.pending_model)
        except (OSError, ValueError, KeyError, RuntimeError):
            self.pending_model = None
        self._download_tray = (0, "")
        self.reload_model = None
        self.model_tasks = set()
        self.switching_model = None
        self.model_failures = {}

    def model_progress(self, data):
        self.emit("model-download", data)
        if data["id"] in {self.pending_model, load(self.path).stt.local_model}:
            task = asyncio.create_task(self.notify_model_state(data))
            self.model_tasks.add(task)
            task.add_done_callback(self.model_tasks.discard)
        if data["state"] == "ready":
            # Reload a model chosen during onboarding, even though its id has
            # not changed since the download began.
            task = asyncio.create_task(self.model_ready(data["id"]))
            self.model_tasks.add(task)
            def completed(done):
                self.model_tasks.discard(done)
                if not done.cancelled() and done.exception():
                    self.emit("model-attention", {"message": "Couldn't switch speech model. Open Settings."})
            task.add_done_callback(completed)

    async def notify_model_state(self, data):
        # Preserve emission order on the socket: a late progress notification
        # must not reinstate downloading after pause/cancel.
        async with self.model_feedback_lock:
            await self._send_model_state(data)

    async def _send_model_state(self, data):
        with suppress(OSError, RuntimeError, ValueError):
            await asyncio.to_thread(request, "model-progress", progress={
                "id": data["id"], "state": data["state"],
            })

    async def model_ready(self, model_id):
        async with self.mutation_lock:
            config = load(self.path)
            if config.stt.engine == "local" and config.stt.local_model == model_id:
                self.reload_model = model_id
                await self.apply_ready_reload()
            await self.apply_pending()

    async def apply_ready_reload(self):
        if self.reload_model is None:
            return
        config = load(self.path)
        if config.stt.local_model != self.reload_model:
            self.reload_model = None
            return
        try:
            await self.idle(allow_missing_model=True)
            if (await self.status())["running"]:
                await asyncio.to_thread(request, "reload")
            self.reload_model = None
        except (OSError, RuntimeError):
            pass

    async def apply_pending(self):
        if not self.pending_model or self.pending_model in self.model_failures or not installed(self.pending_model):
            return
        try:
            await self.idle(allow_missing_model=True)
        except RuntimeError:
            return  # The event watcher retries after the dictation ends.
        model_id = self.pending_model
        try:
            await self.use_model(model_id, downloaded=True)
        except SettingsBusy:
            return  # Capture/retry won the race; keep the queued selection.
        self.pending_model = None
        (models_dir() / "pending-use.json").unlink(missing_ok=True)

    async def save_settings(self, config, previous):
        """The process owning the active engine commits a validated model switch."""
        from .config import validate
        from .providers import Providers

        validate(config)
        running = (await self.status())["running"]
        changed = Providers.signature(config) != Providers.signature(previous)
        if running and changed:
            # The daemon stages the candidate, persists, then swaps. A failed load
            # leaves both the saved config and the previous engine untouched.
            await asyncio.to_thread(request, "settings", config=asdict(config))
        elif changed and (config.stt.engine == "local" or config.stt.fallback == "local"):
            provider = Providers(config)
            candidate = None
            try:
                candidate = await provider.prepare_local(config)
                await asyncio.to_thread(save, config, self.path)
            finally:
                if candidate:
                    await candidate.aclose()
                await provider.aclose()
        else:
            await asyncio.to_thread(save, config, self.path)
            if running:
                try:
                    await asyncio.to_thread(request, "reload")
                except (RuntimeError, OSError) as error:
                    return f"Saved; service not updated: {error}"
        return None

    async def use_model(self, model_id, *, downloaded=False):
        get_model(model_id)
        await self.idle(allow_missing_model=downloaded)
        previous = load(self.path)
        config = load(self.path)
        config.stt.engine, config.stt.local_model = "local", model_id
        if config.stt.fallback == "local":
            config.stt.fallback = "none"
        self.switching_model = model_id
        self.model_failures.pop(model_id, None)
        self.emit("models-changed", {"id": model_id})
        try:
            await self.save_settings(config, previous)
        except SettingsBusy:
            raise
        except Exception as error:
            from .providers import ProviderError

            self.model_failures[model_id] = (str(error) if isinstance(error, (ProviderError, RuntimeError))
                                           else "Couldn't load this speech model. Try again.")
            raise
        finally:
            self.switching_model = None
            self.emit("models-changed", {"id": model_id})
        self.pending_model = None
        (models_dir() / "pending-use.json").unlink(missing_ok=True)
        self.setup_checks.discard("provider")
        self.setup_checks.discard("practice")

    async def status(self):
        try:
            value = await asyncio.to_thread(request, "status")
            value["running"] = True
        except (FileNotFoundError, ConnectionRefusedError):
            value = {"running": False, "state": "hidden", "paused": False}
        if value.get("feedback") == {}:
            value.pop("feedback")
        config = load(self.path)
        if "engine" not in value:
            ready = (config.stt.engine != "local" or bool(
                config.stt.local_model and installed(config.stt.local_model)
            ))
            value["engine"] = {"kind": config.stt.engine, "model": config.stt.local_model or None,
                               "state": ("unloaded" if ready and config.stt.engine == "local" else
                                         "ready" if ready else "missing"), "message": ""}
        title, detail = service_presentation(value if value["running"] else None)
        selected = self.switching_model or self.pending_model or config.stt.local_model
        progress = self.models.states.get(selected, {})
        if value.get("state") in ("hidden", "success", "unrefined", "saved", "copied", "no_speech"):
            if self.switching_model:
                title, detail = "Loading speech model", get_model(selected)["label"]
            elif progress.get("state") in ("queued", "downloading", "stalled", "verifying", "installing", "failed"):
                labels = {"queued": "Download queued", "downloading": "Downloading speech model",
                          "stalled": "Download stalled", "verifying": "Checking speech model",
                          "installing": "Installing speech model", "failed": "Model download failed"}
                title = labels[progress["state"]]
                detail = (progress.get("error") or {}).get("message", get_model(selected)["label"])
        return {**value, "title": title, "detail": detail}

    async def idle(self, *, allow_missing_model=False):
        status = await self.status()
        if allow_missing_model and status.get("state") == "missing_model" and load(self.path).stt.engine == "local":
            return
        if status.get("pending_audio") or status.get("state") in {
            "starting",
            "listening",
            "recording",
            "processing",
            "refining",
            "loading",
        }:
            raise RuntimeError("Finish dictation or discard pending audio first")

    async def start(self):
        if (await self.status())["running"]:
            return
        if os.name == "nt":
            from .service import serve

            self.service_task = asyncio.create_task(serve(load(self.path), self.path))
            for _ in range(100):
                await asyncio.sleep(0.1)
                if self.service_task.done():
                    finished, self.service_task = self.service_task, None
                    await finished
                    raise RuntimeError("Windows dictation service stopped during startup")
                if (await self.status())["running"]:
                    return
            self.service_task.cancel()
            await asyncio.gather(self.service_task, return_exceptions=True)
            raise RuntimeError("Windows dictation service took too long to start")
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

    async def stop(self, *, request_shutdown=True):
        if self.shutdown_complete:
            return
        if request_shutdown:
            with suppress(OSError, RuntimeError):
                await asyncio.to_thread(request, "shutdown")
        if self.service_task:
            await self.service_task
            self.service_task = None
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

    async def stop_idle(self):
        await self.idle()
        # Recheck under the daemon's control lock and block already queued starts.
        # A shortcut can begin recording after the sidecar's status snapshot.
        with suppress(FileNotFoundError, ConnectionRefusedError):
            await asyncio.to_thread(request, "prepare-update")
        # prepare-update already stops the daemon. A second command can connect
        # to its closing socket and wait for the full socket timeout.
        await self.stop(request_shutdown=False)

    async def dispatch(self, method, params):
        config = load(self.path)
        if method == "bootstrap":
            from .launcher import entry_path
            progress = Progress.load(self.path)
            stage = progress.stage if progress.fingerprint in ("", setup_fingerprint(config)) else 0

            return {
                "version": VERSION,
                "config": asdict(config),
                "privacy": privacy(config),
                "setup": {"stage": stage, "complete": progress.complete},
                "autostart": entry_path(True).exists(),
                "credentials": {
                    name: credentials.describe(name)
                    for name in {config.stt.key_env, config.cleanup.key_env}
                },
            }
        if method == "status":
            return await self.status()
        if method == "models.list":
            await self.models.recover()
            if os.name == "nt" and "language" in params:
                config.stt.language = params["language"]
            hardware = await asyncio.to_thread(detect, config)
            if os.name != "nt" and params.get("language"):
                hardware.language = params["language"]
            result = await asyncio.to_thread(self.models.list, config, hardware)
            status = await self.status()
            for model in result["models"]:
                if model["id"] == self.switching_model:
                    model["runtime_state"] = "loading"
                elif model["id"] in self.model_failures:
                    model["runtime_state"] = "failed"
                    model["runtime_message"] = self.model_failures[model["id"]]
                elif model["in_use"]:
                    engine = status.get("engine", {})
                    model["runtime_state"] = engine.get("state", "unloaded")
                    model["runtime_message"] = engine.get("message", "")
            return {**result, "pending_use": self.pending_model}
        if method.startswith("models."):
            model_id = params["id"]
            get_model(model_id)
            if method == "models.download" or method == "models.resume":
                await self.models.submit(model_id)
            elif method == "models.pause":
                await self.models.pause(model_id)
            elif method == "models.cancel":
                await self.models.cancel(model_id)
                if self.pending_model == model_id:
                    self.pending_model = None
                    (models_dir() / "pending-use.json").unlink(missing_ok=True)
            elif method == "models.remove":
                if config.stt.local_model == model_id and (
                    config.stt.engine == "local" or config.stt.fallback == "local"
                ):
                    raise RuntimeError("Switch to another model first.")
                return {"freed_bytes": await asyncio.to_thread(self.models.remove, model_id)}
            elif method == "models.verify":
                await self.idle()
                result = await asyncio.to_thread(verify, model_id)
                if not result["ok"]:
                    (models_dir() / model_id / "receipt.json").unlink(missing_ok=True)
                return result
            elif method == "models.use":
                if params.get("when_ready") and not installed(model_id):
                    self.pending_model = model_id
                    models_dir().mkdir(parents=True, exist_ok=True)
                    (models_dir() / "pending-use.json").write_text(json.dumps({"id": model_id}))
                    await self.models.submit(model_id)
                else:
                    await self.use_model(model_id)
                return {"saved": True}
            else:
                raise ValueError("Unknown model operation")
            return {"ok": True}
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
            await self.models.recover()
            if self.sample_lock.locked():
                raise RuntimeError("Finish the microphone test first")
            await self.start()
        elif method == "service.stop":
            if params.get("discard"):
                await self.stop()
            else:
                await self.stop_idle()
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
            if config.stt != previous.stt:
                await self.idle()
            warning = await self.save_settings(config, previous)
            if (config.stt.engine != previous.stt.engine or config.stt.local_model != previous.stt.local_model) and (
                config.stt.engine == "online" or config.stt.local_model
            ):
                self.pending_model = None
                (models_dir() / "pending-use.json").unlink(missing_ok=True)
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
            return {"saved": True, **({"warning": warning} if warning else {})}
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
                await client.aclose()
            return await asyncio.to_thread(credentials.store, name, params["value"])
        elif method == "credentials.delete":
            if params["name"] not in {config.stt.key_env, config.cleanup.key_env}:
                raise ValueError("Credential is not used by configured providers")
            await asyncio.to_thread(credentials.delete, params["name"])
        elif method == "setup.validate":
            if config.stt.engine != "local" and params.get("consent") is not True:
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
            interactive = method == "practice" and params.get("interactive") is True
            if self.sample_lock.locked():
                raise RuntimeError("A microphone test is already running")
            self.sample_finished.clear()
            await self.idle()
            if self.sample_lock.locked():
                raise RuntimeError("A microphone test is already running")
            async with self.sample_lock:
                self.cancelled.clear()
                if method == "practice" and params.get("consent") is not True and config.stt.engine != "local":
                    raise ValueError("Explicit audio upload consent is required")
                target = None
                if method == "practice" and params.get("insert") is True:
                    from .portable import backend_name
                    if backend_name(config) == "hyprland":
                        from .linux import target_at_press
                        target = await target_at_press()
                        # Setup only inserts into the desktop window that owns this sidecar.
                        # If focus changed before capture began, return text to the UI instead.
                        if target.pid != os.getppid():
                            target = None
                pcm = await asyncio.to_thread(
                    record_sample,
                    config,
                    15 if interactive else 5 if method == "practice" else 3,
                    self.cancelled,
                    lambda level: self.emit("microphone", {"level": level}),
                    **({"finished": self.sample_finished} if interactive else {}),
                )
                if not pcm:
                    raise RuntimeError("No speech detected. Try again")
                if method == "practice":
                    text, refined = await practice(config, pcm, self.cancelled)
                    self.setup_checks.add("practice")
                    if config.stt.engine == "local":
                        self.setup_checks.add("provider")
                    result = {"text": text, "refined": refined}
                    if self.cancelled.is_set():
                        raise RuntimeError("Practice cancelled; sample discarded")
                    if params.get("insert") is True:
                        from .linux import insert
                        result["inserted"] = await insert(text, target) if target else False
                    return result
                self.setup_checks.add("microphone")
        elif method == "sample.cancel":
            if params.get("finish") is True:
                self.sample_finished.set()
            else:
                self.cancelled.set()
        elif method == "setup.finish":
            skip = params.get("skip_practice") is True
            required = ({"microphone", "shortcut"} | (
                {"provider"} if config.stt.engine != "local" else set()
            )) if skip else {
                "provider", "microphone", "shortcut", "practice"
            }
            if not required <= self.setup_checks:
                raise ValueError("Validate providers, microphone, shortcut, and practice first")
            await self.start()
            Progress(4, True).save(self.path)
        elif method == "setup.stage":
            Progress(int(params["stage"]), False, sorted(self.setup_checks),
                     setup_fingerprint(config)).save(self.path)
        elif method == "setup.skip":
            config.stt.engine, config.stt.fallback = "online", "none"
            await asyncio.to_thread(save, config, self.path)
            self.setup_checks.clear()
            Progress(0, False).save(self.path)
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
        elif method == "updates.testing":
            from .updates import check_testing

            return await asyncio.to_thread(check_testing)
        elif method == "updates.stage":
            from .updates import stage

            await self.idle()
            if not self.update:
                raise ValueError("Check for updates first")
            return await asyncio.to_thread(stage, self.update)
        elif method == "updates.apply":
            from .desktop_services import install_queued_update

            await self.idle()
            if os.name == "nt":
                from .updates import apply_pending

                await self.stop_idle()
                return await asyncio.to_thread(apply_pending)
            return await asyncio.to_thread(install_queued_update)
        elif method == "updates.discard":
            from .updates import discard_pending

            await asyncio.to_thread(discard_pending)
        elif method == "updates.pending":
            from .updates import pending_update

            return await asyncio.to_thread(pending_update)
        elif method == "shutdown":
            if self.shutdown_complete:
                return {"ok": True}
            self.cancelled.set()
            if params.get("discard"):
                await self.stop()
            else:
                await self.stop_idle()
            self.shutdown_complete = True
        else:
            raise ValueError("Unknown method")
        return {"ok": True}


async def run(output=None):
    loop = asyncio.get_running_loop()

    def emit(event, data):
        frame = json.dumps({"v": VERSION, "event": event, "data": data}, allow_nan=False)
        loop.call_soon_threadsafe(lambda: print(frame, file=output, flush=True))

    backend = Backend(emit=emit)
    tasks = set()
    reader = asyncio.StreamReader(limit=MAX_FRAME)
    protocol = asyncio.StreamReaderProtocol(reader)
    transport = None
    if os.name == "nt":
        # Inherited Windows stdio handles aren't overlapped asyncio pipes.
        async def readline():
            data = await asyncio.to_thread(sys.stdin.buffer.readline, MAX_FRAME + 1)
            if len(data) > MAX_FRAME:
                raise ValueError("Oversized desktop request")
            return data
    else:
        transport, _ = await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, transport.close)
        readline = reader.readline

    async def respond(message):
        identifier = message.get("id")
        try:
            if message.get("v") != VERSION or type(identifier) is not int:
                raise ValueError("Unsupported protocol version or request ID")
            method, params = message["method"], message.get("params", {})
            if not isinstance(method, str) or not isinstance(params, dict):
                raise ValueError("Invalid request envelope")
            validate_request(method, params)
            if method in {
                "status",
                "history",
                "summary",
                "devices",
                "microphone.test",
                "practice",
                "sample.cancel",
                "updates.check",
                "updates.testing",
                "models.list",
            }:
                result = await backend.dispatch(method, params)
            else:
                async with backend.mutation_lock:
                    result = await backend.dispatch(method, params)
            if not matches(METHODS[method]["result"], result):
                raise RuntimeError("Engine result does not match the desktop contract")
            frame = json.dumps({"v": VERSION, "id": identifier, "result": result}, allow_nan=False)
            if len(frame.encode()) > 16 * MAX_FRAME:
                raise ValueError("Result is too large; narrow your history search")
            print(frame, file=output, flush=True)
        except Exception as error:
            info = error_payload(error)
            # Preserve the JSONL v1 string for older clients; typed metadata is additive.
            print(
                json.dumps(
                    {"v": VERSION, "id": identifier, "error": info["message"], "error_info": info}
                ),
                file=output, flush=True,
            )

    async def events():
        previous = None
        while True:
            try:
                status = await backend.status()
                if status != previous:
                    emit("status", status)
                    previous = status
                if backend.pending_model:
                    async with backend.mutation_lock:
                        await backend.apply_pending()
                if backend.reload_model:
                    async with backend.mutation_lock:
                        await backend.apply_ready_reload()
            except Exception:
                emit("status-error", {"message": "Service status unavailable. Retrying…"})
            await asyncio.sleep(0.1)

    watcher = asyncio.create_task(events())
    try:
        while line := await readline():
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
        # EOF/termination must not wait indefinitely for a provider operation.
        if tasks:
            await asyncio.wait(tasks, timeout=2)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await backend.stop()
        await backend.models.aclose()
        for task in list(backend.model_tasks):
            task.cancel()
        await asyncio.gather(*backend.model_tasks, return_exceptions=True)
        if transport:
            transport.close()


def main():
    if os.name == "nt":
        # The shared service and native decoders run in this process on
        # Windows. Only protocol frames may reach Tauri, even if a DLL writes
        # progress to stdout. Never send decoder diagnostics to a log file.
        with os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", newline="\n") as out:
            with open(os.devnull, "wb") as sink:
                os.dup2(sink.fileno(), sys.stdout.fileno())
            asyncio.run(run(out))
    else:
        asyncio.run(run())


if __name__ == "__main__":
    main()
