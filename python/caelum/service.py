import asyncio
import json
import os
import signal
import socket
import sqlite3
import struct
import sys
from contextlib import suppress
from copy import deepcopy
from dataclasses import replace

from .config import STT, App, Cleanup, Config, Desktop, load, save, validate
from .credentials import get as credential
from .desktop_services import CONTROL_FRAME_LIMIT, SettingsBusy
from .history import History
from .linux import Bindings, hypr_json, runtime_dir, session_locked
from .orchestrator import HUD, Orchestrator
from .portable import backend_name
from .providers import Providers


async def owner_monitor(owner):
    """Stop owned services after a desktop sidecar crash; standalone serve is unaffected."""
    while os.getppid() == owner:
        await asyncio.sleep(0.5)
    raise RuntimeError("Desktop owner exited")


async def prepare_update(core, stop):
    async with core.control_lock:
        if (
            core.capture
            or core.pcm is not None
            or core.work
            and not core.work.done()
            or core.state
            not in {"hidden", "success", "unrefined", "saved", "copied", "ready_to_copy", "error", "no_speech",
                    "success_fallback_online", "success_fallback_local", "model_ready", "model_failed"}
        ):
            raise RuntimeError("Finish dictation or discard pending audio before updating")
        core.stopping = True
        stop.set()
        return {"ok": True}


async def model_download_feedback(core, state):
    transient = {"model_downloading", "model_stalled", "model_loading"}
    kind = {"downloading": "model_downloading", "stalled": "model_stalled",
            "verifying": "model_loading", "installing": "model_loading",
            "failed": "model_failed", "paused": "hidden", "cancelled": "hidden",
            "ready": "hidden"}.get(state)
    if kind is None:
        return
    async with core.control_lock:
        if core.capture is not None or core.pcm is not None or core.work and not core.work.done():
            return
        # Ending a download clears only its transient feedback. Preserve
        # dictation results and the outcome of any subsequent model activation.
        eligible = transient if kind == "hidden" else transient | {
            "hidden", "success", "unrefined", "saved", "copied", "no_speech", "model_ready", "model_failed",
        }
        if core.state in eligible and core.state != kind:
            await core.event(kind)


async def safety_monitor(core):
    """Fail closed on suspend/lock signals. Also monitor compositor reconnect/reload."""
    process = await asyncio.create_subprocess_exec(
        "gdbus",
        "monitor",
        "--system",
        "--dest",
        "org.freedesktop.login1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        while line := await process.stdout.readline():
            if (
                b"PrepareForSleep (true" in line
                or b"LockedHint': <true>" in line
                or b".Session.Lock ()" in line
            ):
                await core.handle("cancel")
        raise RuntimeError("Session safety monitor disconnected")
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()


async def lock_monitor(core, locked=session_locked):
    while True:
        if core.capture or core.pcm is not None or core.manual_result is not None:
            try:
                is_locked = await locked()
            except (OSError, RuntimeError, TimeoutError):
                is_locked = True  # missing capture safety feedback fails closed
            if is_locked:
                await core.handle("cancel")
        await asyncio.sleep(0.2)


async def compositor_monitor(core, bindings):
    path = os.path.join(
        os.environ["XDG_RUNTIME_DIR"],
        "hypr",
        os.environ["HYPRLAND_INSTANCE_SIGNATURE"],
        ".socket2.sock",
    )
    reader, writer = await asyncio.open_unix_connection(path)
    try:
        while line := await reader.readline():
            if line.startswith(b"configreloaded>>"):
                await core.handle("cancel")
                bindings.installed = False
                await bindings.install()
            if line.startswith(b"monitorremoved>>") and core.target:
                monitors = await hypr_json("monitors")
                if not any(m["name"] == core.target.output for m in monitors):
                    core.target.output = next((m["name"] for m in monitors if m.get("focused")), "")
                    await core.event()
        raise RuntimeError("Compositor disconnected")
    finally:
        writer.close()
        await writer.wait_closed()


async def reload_settings(core, bindings, provider, path=None, updated=None, persist=False):
    async with core.control_lock:
        if core.capture or core.work and not core.work.done():
            raise SettingsBusy("Finish or cancel dictation before applying settings")
        updated = updated or await asyncio.to_thread(load, path)
        validate(updated)
        recovering = core.pcm is not None
        if recovering:
            # Retained audio may gain a local model, never a different upload
            # policy, backend, or other settings. Retry remains an explicit action.
            expected = replace(core.config, stt=replace(core.config.stt, local_model=updated.stt.local_model))
            if (getattr(core, "state", "") != "missing_model" or updated.stt.engine != "local"
                    or not updated.stt.local_model or expected != updated):
                raise SettingsBusy("Finish or cancel dictation before applying settings")
        previous = bindings.hotkey
        previous_mode = getattr(bindings, "recording_mode", "hold")
        if backend_name(updated) != backend_name(core.config):
            raise RuntimeError("Restart the service to change desktop backend")
        # Stage native loading before either configuration or the active engine changes.
        staged = hasattr(provider, "signature") and (
            provider.signature(updated) != provider.local_signature
            or updated.stt.engine == "local" and provider.local_state in ("missing", "error")
        )
        candidate = None
        if staged:
            if provider.local_task:
                await asyncio.gather(provider.local_task, return_exceptions=True)
            show_model = not recovering and hasattr(core, "event") and bool(provider.signature(updated)[0])
            if show_model:
                with suppress(RuntimeError, OSError, TimeoutError):
                    await core.event("model_loading")
            try:
                candidate = await provider.prepare_local(updated)
            except BaseException:
                if show_model:
                    with suppress(RuntimeError, OSError, TimeoutError):
                        await core.event("model_failed")
                raise
        # A portal session keeps its original binding until the user restarts.
        rebind = not getattr(bindings, "save_only", False) and (
            previous != updated.app.hotkey or previous_mode != updated.app.recording_mode
        )
        try:
            if rebind:
                await bindings.remove()
                bindings.hotkey = updated.app.hotkey
                bindings.recording_mode = updated.app.recording_mode
                await bindings.install()
            if persist:
                await asyncio.to_thread(save, updated, path)
        except BaseException:
            if rebind:
                await bindings.remove()
                bindings.hotkey = previous
                bindings.recording_mode = previous_mode
                await bindings.install()
            if candidate:
                await candidate.aclose()
                if hasattr(core, "event"):
                    with suppress(RuntimeError, OSError, TimeoutError):
                        await core.event("model_failed")
            raise
        bindings.recording_mode = updated.app.recording_mode
        core.config = updated
        provider.config = updated
        provider.semaphore = asyncio.Semaphore(updated.stt.concurrency)
        if staged:
            await provider.commit_local(updated, candidate)
            if candidate and not recovering and hasattr(core, "event"):
                with suppress(RuntimeError, OSError, TimeoutError):
                    await core.event("model_ready")
        elif hasattr(provider, "arm_idle"):
            provider.arm_idle()


async def serve(config, config_path=None):
    if config.stt.engine != "local" and not await asyncio.to_thread(credential, config.stt.key_env):
        raise ValueError(
            "Add the transcription key in Settings → Open setup / Manage keys "
            "before starting Caelum; run caelum doctor"
        )
    windows = os.name == "nt"
    path = lock = None
    if not windows:
        import fcntl

        directory = runtime_dir()
        lock = (directory / "daemon.lock").open("w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Caelum is already running") from None
        path = directory / "control.sock"
        path.unlink(missing_ok=True)
    native = backend_name(config) == "hyprland"
    if windows:
        from . import windows_desktop

        bindings = windows_desktop.Bindings(config.app.hotkey, config.app.recording_mode)
        hud = windows_desktop.HUD(config.app)
        locked = bindings.locked
    elif native:
        bindings, hud = Bindings(config.app.hotkey, config.app.recording_mode), HUD(config.app)
        locked = session_locked
    else:
        from .portable import HUD as PortableHUD
        from .portable import Bindings as PortableBindings
        from .portable import session_locked as locked

        bindings, hud = PortableBindings(config.app.hotkey, config.app.recording_mode), PortableHUD(config.app)
    provider = Providers(config)
    core = Orchestrator(config, provider, hud, bindings)
    if windows:
        core.media = windows_desktop.RecordingMedia()
    if not native:
        bindings.core = core
    history = History(config_path)
    pending_writes = set()
    storage_error = False

    async def persist(arguments, snapshot):
        nonlocal storage_error
        try:
            recorded = await asyncio.to_thread(
                history.record, *arguments[:3], snapshot, *arguments[3:]
            )
            storage_error = False
            return recorded is not False
        except (OSError, ValueError, RuntimeError, sqlite3.Error):
            storage_error = True
            return False

    def completed(*arguments):
        task = asyncio.create_task(persist(arguments, deepcopy(core.config)))
        pending_writes.add(task)
        task.add_done_callback(pending_writes.discard)
        return task

    core.on_completed = completed
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    if not windows:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
    tasks = []
    server = None

    async def dispatch(message):
        try:
            if stop.is_set():
                raise RuntimeError("Caelum is shutting down")
            if message.get("action") not in {
                "start",
                "stop",
                "toggle",
                "cancel",
                "retry",
                "copy",
                "status",
                "reload",
                "settings",
                "model-progress",
                "shutdown",
                "prepare-update",
                "pause",
                "resume",
            }:
                raise ValueError("Unknown command")
            token = str(message.get("token") or "")[:80]
            if message["action"] == "prepare-update":
                result = await prepare_update(core, stop)
            elif message["action"] == "shutdown":
                await core.handle("cancel")
                stop.set()
                result = {"ok": True}
            elif message["action"] == "model-progress":
                from .models import get_model

                progress = message.get("progress", {})
                get_model(progress.get("id"))
                await model_download_feedback(core, progress.get("state"))
                result = {"ok": True}
            elif message["action"] == "settings":
                from .ipc_contract import CONFIG, matches

                data = message.get("config")
                if not matches(CONFIG, data):
                    raise ValueError("Invalid settings")
                updated = Config(**{name: cls(**data[name]) for name, cls in (
                    ("app", App), ("stt", STT), ("cleanup", Cleanup), ("desktop", Desktop)
                )})
                await reload_settings(core, bindings, provider, config_path, updated, True)
                result = {"ok": True}
            elif message["action"] == "reload":
                await reload_settings(core, bindings, provider, config_path)
                result = {"ok": True}
            else:
                result = await core.handle(message["action"], token, message.get("address"))
                if message["action"] == "status":
                    result["engine"] = provider.engine_status()
                    result["storage_error"] = storage_error
                    result["hotkey"] = bindings.hotkey
                    result["recording_mode"] = core.config.app.recording_mode
                    result["backend"] = backend_name(core.config)
                    result["shortcut_mode"] = "native" if native else bindings.mode
                    result["shortcut_description"] = (
                        core.config.app.hotkey if native else bindings.description
                    )
            return result or {"ok": True}
        except Exception as error:
            if core.capture is None and core.pcm is None:
                with suppress(RuntimeError, OSError, TimeoutError):
                    await bindings.active(False)
            from .providers import ProviderError

            safe = str(error) if isinstance(error, (ProviderError, SettingsBusy)) else "Command failed; run caelum doctor"
            payload = {"error": safe}
            if isinstance(error, SettingsBusy):
                payload["error_code"] = "settings_busy"
            return payload

    async def handle(reader, writer):
        try:
            peer = writer.get_extra_info("socket").getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, 12
            )
            if struct.unpack("3i", peer)[1] != os.getuid():
                return
            line = await asyncio.wait_for(reader.readline(), 1)
            result = await dispatch(json.loads(line))
            writer.write(json.dumps(result).encode() + b"\n")
        finally:
            with suppress(ConnectionError):
                await writer.drain()
            writer.close()

    try:
        if await locked():
            raise RuntimeError("Unlock your desktop before starting Caelum")
        await hud.start()
        if windows or native:
            await bindings.install()
        if windows:
            windows_desktop.endpoint = loop, dispatch
        else:
            server = await asyncio.start_unix_server(handle, path=str(path), limit=CONTROL_FRAME_LIMIT)
            path.chmod(0o600)
        provider.on_loading = lambda: core.event("loading") if core.capture is None else asyncio.sleep(0)
        provider.on_processing = lambda: core.event("processing") if core.capture is None else asyncio.sleep(0)
        provider.configure_local()

        async def monitor_shortcuts():
            if native:
                await compositor_monitor(core, bindings)
            else:
                if not windows:
                    # The optional portal can prompt. Keep the control socket available
                    # for settings, manual dictation, and cancellation during approval.
                    await bindings.install()
                await bindings.monitor()

        tasks = [
            asyncio.create_task(lock_monitor(core, locked)),
            asyncio.create_task(monitor_shortcuts()),
        ]
        if not windows:
            tasks.append(asyncio.create_task(safety_monitor(core)))

        if owner := os.environ.get("CAELUM_OWNER_PID"):
            tasks.append(asyncio.create_task(owner_monitor(int(owner))))
        if hud.process:
            tasks.append(asyncio.create_task(hud.process.wait()))

        def failed(task):
            if not task.cancelled():
                if task.exception():
                    print("Caelum safety/helper connection closed; stopping.", file=sys.stderr, flush=True)
                stop.set()

        for task in tasks:
            task.add_done_callback(failed)
        if not windows:
            print(
                f"Caelum ready · {config.app.recording_mode} {config.app.hotkey} · Escape cancels"
                if native else f"Caelum ready · {bindings.description} · manual paste",
                flush=True,
            )
        await stop.wait()
    finally:
        if windows:
            windows_desktop.endpoint = None
        if server:
            server.close()
            await server.wait_closed()
        async with core.control_lock:
            core.paused = True
            await core.cancel(feedback=False)
        await asyncio.gather(*pending_writes, return_exceptions=True)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bindings.remove()
        await hud.close()
        await provider.aclose()
        if path:
            path.unlink(missing_ok=True)
        if lock:
            lock.close()
