"""Desktop-neutral Linux recording with the optional GlobalShortcuts portal.

Wayland deliberately restricts focus inspection and synthetic paste. This backend
saves completed dictations for an explicit Copy action in the GTK application.
"""

import asyncio
import os
import uuid
from contextlib import suppress

from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import AuthError, DBusError, InvalidAddressError

from .linux import Target, command

PORTAL = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"


def backend_name(config):
    if config.app.backend != "auto":
        return config.app.backend
    return "hyprland" if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") else "portable"


async def session_locked():
    session = os.environ.get("XDG_SESSION_ID") or "auto"
    value = await command("loginctl", "show-session", session, "-p", "LockedHint", "--value")
    if value not in ("yes", "no"):
        raise RuntimeError("Cannot establish desktop session lock state; run caelum doctor")
    return value == "yes"


def portal_trigger(hotkey):
    parts = [part.strip() for part in hotkey.split("+")]
    names = {"SUPER": "LOGO", "CTRL": "CTRL", "ALT": "ALT", "SHIFT": "SHIFT"}
    if parts[-1] in names:
        # The XDG shortcut specification requires a non-modifier key.
        return None
    return "+".join([*(names[part] for part in parts[:-1]), parts[-1]])


class Bindings:
    save_only = True

    def __init__(self, hotkey):
        self.hotkey = hotkey
        self.installed = False
        self.bus = None
        self.session = None
        self.core = None
        self.mode = "manual"
        self.description = "Use Record in Caelum or a desktop shortcut for caelum control toggle"
        self.pending = {}
        self.events = asyncio.Queue()
        self.responses = {}
        self.owner = None
        self.request_paths = set()

    async def locked(self):
        return await session_locked()

    async def target(self, address=None):
        return Target("", -1, -1, "")

    async def call(self, interface, member, signature="", body=None, path=PATH, destination=PORTAL):
        reply = await self.bus.call(
            Message(
                destination=destination,
                path=path,
                interface=interface,
                member=member,
                signature=signature,
                body=body or [],
            )
        )
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"Desktop portal {member} unavailable")
        return reply.body

    def signal(self, message):
        if message.message_type != MessageType.SIGNAL or message.sender != self.owner:
            return
        if message.interface == "org.freedesktop.portal.Request" and message.member == "Response":
            if message.path in self.request_paths:
                self.responses[message.path] = message.body
                if future := self.pending.get(message.path):
                    if not future.done():
                        future.set_result(message.body)
        elif message.interface == SHORTCUTS and message.path == PATH:
            if message.member in ("Activated", "Deactivated") and len(message.body) >= 2:
                session, shortcut = message.body[:2]
                if session == self.session and shortcut == "dictate":
                    self.events.put_nowait(message.member)
        elif message.interface == "org.freedesktop.portal.Session":
            if message.member == "Closed" and message.path == self.session:
                self.events.put_nowait("Closed")

    async def request(self, member, signature, arguments, options):
        token = "caelum_" + uuid.uuid4().hex
        options["handle_token"] = Variant("s", token)
        sender = self.bus.unique_name[1:].replace(".", "_")
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        self.request_paths.add(path)
        future = asyncio.get_running_loop().create_future()
        self.pending[path] = future
        try:
            result = await asyncio.wait_for(
                self.call(SHORTCUTS, member, signature, [*arguments, options]), 5
            )
            if result != [path]:
                raise RuntimeError("Desktop portal returned an unexpected request path")
            response, values = await asyncio.wait_for(future, 60)
            if response:
                raise RuntimeError("Desktop shortcut permission was declined")
            return values
        except BaseException:
            with suppress(Exception):
                await asyncio.wait_for(
                    self.call("org.freedesktop.portal.Request", "Close", path=path), 2
                )
            raise
        finally:
            self.pending.pop(path, None)
            self.responses.pop(path, None)
            self.request_paths.discard(path)

    async def install(self):
        trigger = portal_trigger(self.hotkey)
        if not trigger:
            self.description = "Choose a shortcut with a letter or use Record in Caelum"
            return
        try:
            self.bus = await asyncio.wait_for(MessageBus().connect(), 5)
            # Resolve the unique sender before accepting signals from this service.
            await self.call(
                "org.freedesktop.DBus",
                "StartServiceByName",
                "su",
                [PORTAL, 0],
                path="/org/freedesktop/DBus",
                destination="org.freedesktop.DBus",
            )
            self.owner = (
                await self.call(
                    "org.freedesktop.DBus",
                    "GetNameOwner",
                    "s",
                    [PORTAL],
                    path="/org/freedesktop/DBus",
                    destination="org.freedesktop.DBus",
                )
            )[0]
            self.bus.add_message_handler(self.signal)
            for interface in (
                "org.freedesktop.portal.Request",
                SHORTCUTS,
                "org.freedesktop.portal.Session",
            ):
                await self.call(
                    "org.freedesktop.DBus",
                    "AddMatch",
                    "s",
                    [f"type='signal',sender='{PORTAL}',interface='{interface}'"],
                    path="/org/freedesktop/DBus",
                    destination="org.freedesktop.DBus",
                )
            values = await self.request(
                "CreateSession",
                "a{sv}",
                [],
                {
                    "session_handle_token": Variant("s", "caelum_" + uuid.uuid4().hex),
                },
            )
            self.session = values["session_handle"].value
            values = await self.request(
                "BindShortcuts",
                "oa(sa{sv})sa{sv}",
                [
                    self.session,
                    [
                        [
                            "dictate",
                            {
                                "description": Variant("s", "Hold to dictate in Caelum"),
                                "preferred_trigger": Variant("s", trigger),
                            },
                        ]
                    ],
                    "",
                ],
                {},
            )
            bound = dict(values.get("shortcuts", Variant("a(sa{sv})", [])).value)
            if "dictate" not in bound:
                raise RuntimeError("Desktop did not bind the recording shortcut")
            self.description = (
                bound["dictate"].get("trigger_description", Variant("s", self.hotkey)).value
            )
            self.mode = "portal"
            self.installed = True
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            KeyError,
            ValueError,
            AuthError,
            DBusError,
            InvalidAddressError,
        ):
            await self.remove()
            self.description = "Shortcut unavailable. Use Record or configure caelum control toggle"

    async def active(self, enabled):
        # Escape interception is compositor-specific. Cancel remains available in the app/CLI.
        pass

    async def monitor(self):
        if self.mode != "portal":
            await asyncio.Future()

        async def events():
            token = None
            while True:
                event = await self.events.get()
                if event == "Closed":
                    raise RuntimeError("Desktop shortcut session closed")
                if event == "Activated" and token is None:
                    token = "portal-" + uuid.uuid4().hex
                    await self.core.handle("start", token)
                elif event == "Deactivated" and token is not None:
                    await self.core.handle("stop", token)
                    token = None

        worker = asyncio.create_task(events())
        disconnected = asyncio.create_task(self.bus.wait_for_disconnect())
        try:
            done, _ = await asyncio.wait(
                [worker, disconnected], return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()
            raise RuntimeError("Desktop shortcut connection closed")
        finally:
            worker.cancel()
            disconnected.cancel()
            await asyncio.gather(worker, disconnected, return_exceptions=True)

    async def remove(self):
        if self.bus:
            if self.session:
                with suppress(Exception):
                    await asyncio.wait_for(
                        self.call("org.freedesktop.portal.Session", "Close", path=self.session), 2
                    )
            self.bus.remove_message_handler(self.signal)
            self.bus.disconnect()
        self.session = self.bus = None
        self.installed = False
        self.mode = "manual"


class HUD:
    """Notifications report transitions without creating a focus-taking overlay."""

    process = None

    def __init__(self, config):
        self.last = None
        self.notification_id = "0"

    async def start(self):
        pass

    async def emit(self, message):
        state = message["state"]
        phase = "recording" if state in ("starting", "listening", "recording") else state
        if phase == self.last:
            return
        self.last = phase
        labels = {
            "recording": "Recording. Release your shortcut or choose Finish recording in Caelum.",
            "processing": "Processing dictation…",
            "refining": "Cleaning up your words…",
            "saved": "Dictation saved. Open Caelum and choose Copy text, then paste where you want.",
            "error": "Dictation failed. Retry or cancel in Caelum.",
            "no_speech": "No speech detected.",
            "hidden": "Recording cancelled.",
        }
        if text := labels.get(phase):
            with suppress(OSError, RuntimeError, TimeoutError):
                result = await command(
                    "notify-send",
                    "--app-name=Caelum",
                    "--print-id",
                    f"--replace-id={self.notification_id}",
                    f"--expire-time={0 if phase == 'recording' else 5000}",
                    "Caelum",
                    text,
                )
                if result.isdigit():
                    self.notification_id = result

    async def close(self):
        pass
