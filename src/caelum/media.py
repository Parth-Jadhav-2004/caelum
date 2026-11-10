"""Best-effort MPRIS pause/resume, scoped to one microphone capture."""

import asyncio
from contextlib import suppress

from dbus_next import Message, MessageType
from dbus_next.aio import MessageBus

PLAYER = "org.mpris.MediaPlayer2.Player"
PATH = "/org/mpris/MediaPlayer2"


class RecordingMedia:
    def __init__(self):
        self.bus = None
        self.paused = {}

    async def call(self, destination, path, interface, member, signature="", body=None):
        reply = await asyncio.wait_for(
            self.bus.call(Message(
                destination=destination, path=path, interface=interface, member=member,
                signature=signature, body=body or [],
            )),
            0.3,
        )
        if reply is None or reply.message_type == MessageType.ERROR:
            raise RuntimeError("Media player unavailable")
        return reply.body

    async def properties(self, owner):
        body = await self.call(
            owner, PATH, "org.freedesktop.DBus.Properties", "GetAll", "s", [PLAYER]
        )
        return {key: value.value for key, value in body[0].items()}

    @staticmethod
    def track(properties):
        track = properties.get("Metadata", {}).get("mpris:trackid")
        return track.value if track else None

    async def pause(self):
        if self.bus is not None:
            return
        try:
            self.bus = MessageBus()
            await asyncio.wait_for(self.bus.connect(), 0.3)
            names, = await self.call(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus", "ListNames",
            )
            names = [name for name in names if name.startswith("org.mpris.MediaPlayer2.")][:32]

            async def owner(name):
                with suppress(Exception):
                    result = await self.call(
                        "org.freedesktop.DBus", "/org/freedesktop/DBus",
                        "org.freedesktop.DBus", "GetNameOwner", "s", [name],
                    )
                    return result[0]
                return None

            owners = set(await asyncio.gather(*(owner(name) for name in names))) - {None}

            async def pause_player(owner):
                with suppress(Exception):
                    properties = await self.properties(owner)
                    if (
                        properties.get("PlaybackStatus") != "Playing"
                        or not properties.get("CanPause")
                        or not properties.get("CanControl", True)
                    ):
                        return
                    # A timeout can occur after the player accepted Pause. Keep enough
                    # state to restore it even if the reply never arrives.
                    self.paused[owner] = self.track(properties)
                    await self.call(owner, PATH, PLAYER, "Pause")

            await asyncio.gather(*(pause_player(owner) for owner in owners))
        except Exception:
            # No media service, unsupported player, or timeout must never block dictation.
            await self.resume()
        except asyncio.CancelledError:
            await self.resume()
            raise

    async def resume(self):
        if self.bus is None:
            return
        try:
            async def resume_player(owner, track):
                with suppress(Exception):
                    properties = await self.properties(owner)
                    if (
                        properties.get("PlaybackStatus") == "Paused"
                        and properties.get("CanPlay")
                        and self.track(properties) == track
                    ):
                        # Address the original bus owner, never a replacement player.
                        await self.call(owner, PATH, PLAYER, "Play")

            await asyncio.gather(*(
                resume_player(owner, track) for owner, track in self.paused.items()
            ))
        finally:
            self.paused.clear()
            with suppress(Exception):
                self.bus.disconnect()
            self.bus = None
