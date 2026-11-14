"""Opt-in real D-Bus round trips, launched in a private bus with synthetic players."""

# D-Bus signature strings are protocol grammar rather than Python type names.
# ruff: noqa: F722, F821
import os

import pytest
from caelum.media import RecordingMedia
from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method

pytestmark = pytest.mark.skipif(
    os.environ.get("CAELUM_DBUS_TESTS") != "1", reason="Run inside an isolated dbus-run-session"
)


class Player(ServiceInterface):
    def __init__(self, state):
        super().__init__("org.mpris.MediaPlayer2.Player")
        self.state, self.track = state, "/track/one"
        self.pauses = self.plays = 0

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":
        return self.state

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        return {"mpris:trackid": Variant("o", self.track)}

    @method()
    def Pause(self):
        self.state = "Paused"
        self.pauses += 1

    @method()
    def Play(self):
        self.state = "Playing"
        self.plays += 1


@pytest.mark.parametrize("change_track", [False, True])
async def test_mpris_real_bus_pause_resume_is_scoped_to_original_track(change_track):
    buses, players = [], []
    media = RecordingMedia()
    try:
        for name, state in (("playing", "Playing"), ("paused", "Paused")):
            bus = await MessageBus().connect()
            buses.append(bus)
            player = Player(state)
            players.append(player)
            bus.export("/org/mpris/MediaPlayer2", player)
            await bus.request_name("org.mpris.MediaPlayer2.caelum_test_" + name)
        await media.pause()
        assert players[0].pauses == 1 and players[1].pauses == 0
        assert players[0].state == "Paused"
        if change_track:
            players[0].track = "/track/two"
        await media.resume()
        assert players[0].plays == (0 if change_track else 1)
        assert players[1].plays == 0
    finally:
        await media.resume()
        for bus in buses:
            bus.disconnect()
