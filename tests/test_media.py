"""MPRIS behavior without touching the user's real media players."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from caelum.media import PATH, PLAYER, RecordingMedia
from dbus_next import MessageType, Variant


class Bus:
    def __init__(self):
        self.players = {
            ":1.10": {"PlaybackStatus": "Playing", "CanPause": True, "CanPlay": True},
            ":1.11": {"PlaybackStatus": "Paused", "CanPause": True, "CanPlay": True},
            ":1.12": {"PlaybackStatus": "Stopped", "CanPause": True, "CanPlay": True},
            ":1.13": {"PlaybackStatus": "Playing", "CanPause": False, "CanPlay": True},
        }
        self.owners = {f"org.mpris.MediaPlayer2.test{i}": owner
                       for i, owner in enumerate(self.players)}
        self.calls = []
        self.disconnect = Mock()
        self.fail = None

    async def connect(self):
        return self

    async def call(self, message):
        self.calls.append(message)
        if message.member == self.fail:
            raise TimeoutError("Player stopped responding")
        if message.member == "ListNames":
            body = [[*self.owners, "org.example.unrelated"]]
        elif message.member == "GetNameOwner":
            body = [self.owners[message.body[0]]]
        elif message.member == "GetAll":
            assert message.path == PATH
            assert message.body == [PLAYER]
            properties = self.players[message.destination]
            body = [{key: Variant("s" if isinstance(value, str) else "b", value)
                     for key, value in properties.items()}]
        else:
            assert message.path == PATH
            assert message.interface == PLAYER
            properties = self.players[message.destination]
            properties["PlaybackStatus"] = "Paused" if message.member == "Pause" else "Playing"
            body = []
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=body)

    def controls(self):
        return [(call.destination, call.member) for call in self.calls
                if call.interface == PLAYER]


@pytest.fixture
def bus(monkeypatch):
    bus = Bus()
    monkeypatch.setattr("caelum.media.MessageBus", lambda: bus)
    return bus


async def test_only_playing_pausable_players_resume_once(bus):
    media = RecordingMedia()
    await media.pause()
    assert bus.controls() == [(":1.10", "Pause")]
    await media.resume()
    await media.resume()
    assert bus.controls() == [(":1.10", "Pause"), (":1.10", "Play")]
    bus.disconnect.assert_called_once()
    assert not media.paused
    assert media.bus is None


@pytest.mark.parametrize("state", ["Stopped", "Playing"])
async def test_user_changed_playback_is_left_alone(bus, state):
    media = RecordingMedia()
    await media.pause()
    bus.players[":1.10"]["PlaybackStatus"] = state
    await media.resume()
    assert bus.controls() == [(":1.10", "Pause")]


async def test_replacement_player_is_not_resumed(bus):
    media = RecordingMedia()
    await media.pause()
    del bus.players[":1.10"]
    bus.owners["org.mpris.MediaPlayer2.test0"] = ":1.99"
    bus.players[":1.99"] = {"PlaybackStatus": "Paused", "CanPlay": True}
    await media.resume()
    assert bus.controls() == [(":1.10", "Pause")]
    bus.disconnect.assert_called_once()


async def test_duplicate_names_pause_once(bus):
    bus.owners["org.mpris.MediaPlayer2.alias"] = ":1.10"
    media = RecordingMedia()
    await media.pause()
    await media.resume()
    assert bus.controls() == [(":1.10", "Pause"), (":1.10", "Play")]


@pytest.mark.parametrize("failure", ["ListNames", "GetAll", "Pause", "Play"])
async def test_player_failures_are_best_effort_and_disconnect(bus, failure):
    bus.fail = failure
    media = RecordingMedia()
    await media.pause()
    await media.resume()
    bus.disconnect.assert_called_once()
    assert media.bus is None


async def test_missing_session_bus_is_ignored(monkeypatch):
    monkeypatch.setattr("caelum.media.MessageBus", Mock(side_effect=OSError("No bus")))
    media = RecordingMedia()
    await media.pause()
    await media.resume()


async def test_unresponsive_bus_has_bounded_wait(bus, monkeypatch):
    async def unresponsive():
        await asyncio.Future()

    monkeypatch.setattr(bus, "connect", unresponsive)
    async with asyncio.timeout(1):
        await RecordingMedia().pause()
    bus.disconnect.assert_called_once()


async def test_changed_track_stays_paused(bus, monkeypatch):
    media = RecordingMedia()
    await media.pause()
    properties = media.properties

    async def changed(owner):
        result = await properties(owner)
        result["Metadata"] = {"mpris:trackid": Variant("o", "/new/track")}
        return result

    monkeypatch.setattr(media, "properties", changed)
    await media.resume()
    assert bus.controls() == [(":1.10", "Pause")]
