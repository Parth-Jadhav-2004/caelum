"""Portable session, portal protocol, and delivery behavior without cloud access."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from dbus_next import Message, MessageType, Variant

from caelum.config import Config
from caelum.portable import (
    HUD,
    PATH,
    SHORTCUTS,
    Bindings,
    backend_name,
    portal_trigger,
    session_locked,
)


def test_backend_selection(monkeypatch):
    config = Config()
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert backend_name(config) == "portable"
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    assert backend_name(config) == "hyprland"
    config.app.backend = "portable"
    assert backend_name(config) == "portable"


def test_portal_trigger():
    assert portal_trigger("SUPER + ALT + V") == "LOGO+ALT+V"
    assert portal_trigger("CTRL + SHIFT + D") == "CTRL+SHIFT+D"
    assert portal_trigger("CTRL + SUPER") is None


async def test_portable_lock_state_fails_closed(monkeypatch):
    command = AsyncMock(side_effect=["no", "yes", "unknown"])
    monkeypatch.setattr("caelum.portable.command", command)
    assert not await session_locked()
    assert await session_locked()
    with pytest.raises(RuntimeError, match="lock state"):
        await session_locked()


async def test_absent_portal_keeps_manual_controls(monkeypatch):
    monkeypatch.setattr(
        "caelum.portable.MessageBus",
        lambda: SimpleNamespace(connect=AsyncMock(side_effect=OSError("No session bus"))),
    )
    bindings = Bindings("SUPER + ALT + V")
    await bindings.install()
    assert bindings.mode == "manual"
    assert bindings.bus is None
    assert "Record" in bindings.description


async def test_modifier_only_never_requests_portal():
    bindings = Bindings("CTRL + SUPER")
    await bindings.install()
    assert bindings.bus is None
    assert bindings.mode == "manual"


async def test_portal_request_accepts_response_before_method_reply():
    bindings = Bindings("SUPER + ALT + V")
    bindings.bus = SimpleNamespace(unique_name=":1.42")
    bindings.owner = ":1.7"

    async def call(interface, member, signature, body):
        token = body[-1]["handle_token"].value
        path = f"/org/freedesktop/portal/desktop/request/1_42/{token}"
        bindings.signal(
            Message(
                path=path,
                interface="org.freedesktop.portal.Request",
                member="Response",
                message_type=MessageType.SIGNAL,
                sender=":1.7",
                signature="ua{sv}",
                body=[0, {"session_handle": Variant("s", "/session/test")}],
            )
        )
        return [path]

    bindings.call = call
    result = await bindings.request("CreateSession", "a{sv}", [], {})
    assert result["session_handle"].value == "/session/test"
    assert not bindings.pending and not bindings.request_paths


async def test_portal_rejects_spoofed_and_unrelated_signals():
    bindings = Bindings("SUPER + ALT + V")
    bindings.owner = ":1.7"
    bindings.session = "/session/test"
    for sender, session in ((":1.8", "/session/test"), (":1.7", "/session/other")):
        bindings.signal(
            Message(
                path=PATH,
                interface=SHORTCUTS,
                member="Activated",
                sender=sender,
                message_type=MessageType.SIGNAL,
                signature="osta{sv}",
                body=[session, "dictate", 1, {}],
            )
        )
    assert bindings.events.empty()
    bindings.signal(
        Message(
            path=PATH,
            interface=SHORTCUTS,
            member="Activated",
            sender=":1.7",
            message_type=MessageType.SIGNAL,
            signature="osta{sv}",
            body=["/session/test", "dictate", 1, {}],
        )
    )
    assert bindings.events.get_nowait() == "Activated"


async def test_portal_press_repeat_and_release_have_one_session():
    bindings = Bindings("SUPER + ALT + V")
    bindings.mode = "portal"
    disconnected = asyncio.Future()

    async def wait_for_disconnect():
        await disconnected

    bindings.bus = SimpleNamespace(wait_for_disconnect=wait_for_disconnect)
    bindings.core = SimpleNamespace(handle=AsyncMock())
    monitor = asyncio.create_task(bindings.monitor())
    try:
        for event in ("Activated", "Activated", "Deactivated"):
            bindings.events.put_nowait(event)
        for _ in range(10):
            await asyncio.sleep(0)
        assert not monitor.done()
        calls = bindings.core.handle.call_args_list
        assert [call.args[0] for call in calls] == ["start", "stop"]
        assert calls[0].args[1] == calls[1].args[1]
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)


async def test_notifications_deduplicate_recording_frames(monkeypatch):
    command = AsyncMock(return_value="42")
    monkeypatch.setattr("caelum.portable.command", command)
    hud = HUD(Config().app)
    for state in ("starting", "listening", "recording", "recording", "processing", "saved"):
        await hud.emit({"state": state})
    assert command.await_count == 3
    assert "--replace-id=42" in command.call_args.args
    assert "Copy text" in command.call_args.args[-1]


async def test_portable_service_controls_without_hyprland_or_audio(tmp_path, monkeypatch):
    import json

    from caelum.service import serve

    config = Config()
    config.app.backend = "portable"
    config.cleanup.model = ""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv(config.stt.key_env, "unused-test-credential")
    monkeypatch.setattr("caelum.portable.Bindings.install", AsyncMock())
    monkeypatch.setattr("caelum.portable.session_locked", AsyncMock(return_value=False))
    monkeypatch.setattr("caelum.portable.HUD.emit", AsyncMock())

    async def monitor(*args):
        await asyncio.Future()

    monkeypatch.setattr("caelum.service.safety_monitor", monitor)

    class Capture:
        size = 0
        level = 0
        error = False
        full = False
        speaking = False
        history = [0] * 17
        speech_ms = 0

        def __init__(self, config):
            pass

        def start(self):
            pass

        def stop(self):
            pass

        def discard(self):
            pass

    monkeypatch.setattr("caelum.orchestrator.Capture", Capture)
    service = asyncio.create_task(serve(config, tmp_path / "config.toml"))
    path = tmp_path / "caelum/control.sock"

    async def control(action):
        reader, writer = await asyncio.open_unix_connection(str(path))
        writer.write(json.dumps({"action": action}).encode() + b"\n")
        await writer.drain()
        reply = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        assert "error" not in reply
        return reply

    try:
        async with asyncio.timeout(5):
            while not path.exists():
                if service.done():
                    service.result()
                await asyncio.sleep(0.01)
        assert (await control("status"))["backend"] == "portable"
        for _ in range(2):
            await control("toggle")
            assert (await control("status"))["state"] == "listening"
            await control("toggle")
            assert (await control("status"))["state"] == "hidden"
        await control("shutdown")
        await asyncio.wait_for(service, 5)
        assert not path.exists()
    finally:
        if not service.done():
            service.cancel()
        await asyncio.gather(service, return_exceptions=True)
