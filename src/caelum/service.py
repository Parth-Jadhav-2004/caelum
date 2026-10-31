import asyncio
import fcntl
import json
import os
import signal
import socket
import sqlite3
import struct
from contextlib import suppress
from copy import deepcopy

from .config import load
from .credentials import get as credential
from .history import History
from .linux import Bindings, hypr_json, runtime_dir, session_locked
from .orchestrator import HUD, Orchestrator
from .portable import backend_name
from .providers import Providers


async def prepare_update(core, stop):
    async with core.control_lock:
        if (
            core.capture
            or core.pcm is not None
            or core.work
            and not core.work.done()
            or core.state
            not in {"hidden", "success", "unrefined", "saved", "copied", "error", "no_speech"}
        ):
            raise RuntimeError("Finish dictation or discard pending audio before updating")
        core.stopping = True
        stop.set()
        return {"ok": True}


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
        if core.capture or core.pcm is not None:
            try:
                is_locked = await locked()
            except (OSError, RuntimeError, TimeoutError):
                locked = True  # missing capture safety feedback fails closed
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


async def reload_settings(core, bindings, provider, path=None):
    async with core.control_lock:
        if core.capture or core.pcm is not None or core.work and not core.work.done():
            raise RuntimeError("Finish or cancel dictation before applying settings")
        updated = await asyncio.to_thread(load, path)
        previous = bindings.hotkey
        if backend_name(updated) != backend_name(core.config):
            raise RuntimeError("Restart the service to change desktop backend")
        if previous != updated.app.hotkey and getattr(bindings, "save_only", False):
            raise RuntimeError("Restart the service to change the desktop portal shortcut")
        if previous != updated.app.hotkey:
            await bindings.remove()
            bindings.hotkey = updated.app.hotkey
            try:
                await bindings.install()
            except Exception:
                bindings.hotkey = previous
                await bindings.install()
                raise
        core.config = updated
        provider.config = updated
        provider.semaphore = asyncio.Semaphore(updated.stt.concurrency)


async def serve(config, config_path=None):
    if not await asyncio.to_thread(credential, config.stt.key_env):
        raise ValueError(f"Export {config.stt.key_env} before starting Caelum; run caelum doctor")
    directory = runtime_dir()
    lock = (directory / "daemon.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Caelum is already running") from None
    path = directory / "control.sock"
    path.unlink(missing_ok=True)
    native = backend_name(config) == "hyprland"
    if native:
        bindings, hud = Bindings(config.app.hotkey), HUD(config.app)
        locked = session_locked
    else:
        from .portable import HUD as PortableHUD
        from .portable import Bindings as PortableBindings
        from .portable import session_locked as locked

        bindings, hud = PortableBindings(config.app.hotkey), PortableHUD(config.app)
    provider = Providers(config)
    core = Orchestrator(config, provider, hud, bindings)
    if not native:
        bindings.core = core
    history = History(config_path)
    pending_writes = set()
    storage_error = False

    async def persist(arguments, snapshot):
        nonlocal storage_error
        try:
            await asyncio.to_thread(history.record, *arguments[:3], snapshot, *arguments[3:])
            storage_error = False
            return True
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
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    tasks = []
    server = None

    async def handle(reader, writer):
        try:
            peer = writer.get_extra_info("socket").getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, 12
            )
            if struct.unpack("3i", peer)[1] != os.getuid():
                return
            line = await asyncio.wait_for(reader.readline(), 1)
            message = json.loads(line)
            if stop.is_set():
                raise RuntimeError("Caelum is shutting down")
            if message.get("action") not in {
                "start",
                "stop",
                "toggle",
                "cancel",
                "retry",
                "status",
                "reload",
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
            elif message["action"] == "reload":
                await reload_settings(core, bindings, provider, config_path)
                result = {"ok": True}
            else:
                result = await core.handle(message["action"], token, message.get("address"))
                if message["action"] == "status":
                    result["storage_error"] = storage_error
                    result["hotkey"] = core.config.app.hotkey
                    result["backend"] = "hyprland" if native else "portable"
                    result["shortcut_mode"] = "native" if native else bindings.mode
                    result["shortcut_description"] = (
                        core.config.app.hotkey if native else bindings.description
                    )
            writer.write(json.dumps(result or {"ok": True}).encode() + b"\n")
        except Exception:
            if core.capture is None and core.pcm is None:
                with suppress(RuntimeError, OSError, TimeoutError):
                    await bindings.active(False)
            writer.write(b'{"error":"Command failed; run caelum doctor"}\n')
        finally:
            with suppress(ConnectionError):
                await writer.drain()
            writer.close()

    try:
        if await locked():
            raise RuntimeError("Unlock your desktop before starting Caelum")
        await hud.start()
        await bindings.install()
        server = await asyncio.start_unix_server(handle, path=str(path), limit=4096)
        path.chmod(0o600)
        tasks = [
            asyncio.create_task(safety_monitor(core)),
            asyncio.create_task(lock_monitor(core, locked)),
            asyncio.create_task(
                compositor_monitor(core, bindings) if native else bindings.monitor()
            ),
        ]

        if hud.process:
            tasks.append(asyncio.create_task(hud.process.wait()))

        def failed(task):
            if not task.cancelled():
                if task.exception():
                    print("Caelum safety/helper connection closed; stopping.", flush=True)
                stop.set()

        for task in tasks:
            task.add_done_callback(failed)
        print(
            f"Caelum ready · hold {config.app.hotkey} · Escape cancels"
            if native
            else f"Caelum ready · {bindings.description} · results in Caelum history",
            flush=True,
        )
        await stop.wait()
    finally:
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
        await provider.client.aclose()
        path.unlink(missing_ok=True)
        lock.close()
