import io
import json
import os
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from caelum import pulse
from caelum.audio import Capture
from caelum.config import App
from caelum.desktop import microphone_selection, microphones


@pytest.fixture
def inputs(monkeypatch):
    devices = [
        {"name": "alsa_input.builtin", "description": "Built-in Audio", "properties": {}},
        {"name": "bluez_input.2C:BE:EE:59:59:AC", "description": "CMF Buds 2",
         "properties": {"device.api": "bluez5"}},
    ]
    monkeypatch.setattr(pulse, "sources", lambda: devices)
    return devices


def test_discovery_filters_monitors_and_queries_fresh_each_time(monkeypatch):
    monkeypatch.setattr(pulse.shutil, "which", lambda name: "/usr/bin/" + name)
    devices = [
        {"name": "bluez_input.test", "description": "CMF Buds 2"},
        {"name": "bluez_output.test.monitor", "description": "Playback"},
        {"name": "another-monitor", "properties": {"device.class": "monitor"}},
    ]
    run = Mock(return_value=SimpleNamespace(stdout=json.dumps(devices)))
    monkeypatch.setattr(pulse.subprocess, "run", run)
    assert pulse.sources() == devices[:1]
    run.return_value.stdout = "[]"
    assert pulse.sources() == []
    assert run.call_count == 2
    assert run.call_args.kwargs["timeout"] == 2


@pytest.mark.parametrize("failure", [OSError(), subprocess.TimeoutExpired("pactl", 2)])
def test_unavailable_server_allows_alsa_fallback(monkeypatch, failure):
    monkeypatch.setattr(pulse.shutil, "which", lambda name: name)
    monkeypatch.setattr(pulse.subprocess, "run", Mock(side_effect=failure))
    assert pulse.sources() is None
    assert pulse.resolve("hw:0") is None
    with pytest.raises(RuntimeError, match="Audio server unavailable"):
        pulse.resolve("pulse:bluez_input.test")


def test_missing_tools_do_not_start_server_query(monkeypatch):
    monkeypatch.setattr(pulse.shutil, "which", lambda name: None)
    query = Mock()
    monkeypatch.setattr(pulse.subprocess, "run", query)
    assert pulse.sources() is None
    query.assert_not_called()


def test_ui_uses_real_sources_and_stable_names(inputs):
    devices = microphones()
    assert devices == [(device["description"], "pulse:" + device["name"]) for device in inputs]
    assert microphone_selection("CMF Buds 2", devices) == devices[1][1]
    assert microphone_selection(None, devices) is None
    assert microphone_selection(devices[1][1], devices) == devices[1][1]
    assert microphone_selection("Missing mic", devices) == "Missing mic"


def test_duplicate_names_are_distinguished_and_legacy_ambiguity_is_rejected(inputs):
    inputs.append({"name": "bluez_input.other", "description": "CMF Buds 2"})
    devices = microphones()
    assert devices[1][0] != devices[2][0]
    assert pulse.resolve(devices[2][1]) == inputs[2]
    with pytest.raises(RuntimeError, match="Multiple microphones"):
        pulse.resolve("CMF Buds 2")


def test_resolution_supports_legacy_names_without_switching_missing_inputs(inputs):
    assert pulse.resolve("CMF Buds 2") == inputs[1]
    assert pulse.resolve("pulse:" + inputs[1]["name"]) == inputs[1]
    assert pulse.resolve(None) == {"name": None}
    assert pulse.resolve(0) is None
    assert pulse.resolve("hw:0") is None
    inputs.pop()
    with pytest.raises(RuntimeError, match="disconnected"):
        pulse.resolve("pulse:bluez_input.2C:BE:EE:59:59:AC")
    inputs.clear()
    with pytest.raises(RuntimeError, match="No microphones"):
        pulse.resolve(None)


def test_capture_uses_server_conversion_for_48khz_bluetooth_input(inputs, monkeypatch):
    stream = Mock()
    factory = Mock(return_value=stream)
    monkeypatch.setattr(pulse, "PulseStream", factory)
    capture = Capture(App(microphone="CMF Buds 2"))
    capture.start()
    factory.assert_called_once_with(inputs[1]["name"], capture.callback)
    stream.start.assert_called_once()
    capture.stop()
    stream.stop.assert_called_once()
    stream.close.assert_called_once()


def test_portaudio_remains_available_without_audio_server(monkeypatch):
    import sounddevice

    monkeypatch.setattr(pulse, "sources", lambda: None)
    factory = Mock()
    monkeypatch.setattr(sounddevice, "RawInputStream", factory)
    capture = Capture(App(microphone="hw:0"))
    capture.start()
    assert factory.call_args.kwargs["device"] == "hw:0"
    assert factory.call_args.kwargs["samplerate"] == 16000
    capture.stop()


def test_failed_stream_start_is_closed(inputs, monkeypatch):
    stream = Mock()
    stream.start.side_effect = RuntimeError("not connected")
    monkeypatch.setattr(pulse, "PulseStream", Mock(return_value=stream))
    capture = Capture(App(microphone="CMF Buds 2"))
    with pytest.raises(RuntimeError, match="not connected"):
        capture.start()
    stream.close.assert_called_once()


def test_pulse_stream_routes_exact_source_and_cleans_up_reader(monkeypatch):
    monkeypatch.setattr(pulse.select, "select", lambda readers, *_: (readers, [], []))
    stopped = threading.Event()
    reads = []

    def read(count):
        assert count == 640
        if not reads:
            reads.append(True)
            return b"\x01\0" * 320
        assert stopped.wait(2)
        return b""

    process = Mock()
    process.stdout.read.side_effect = read
    process.poll.return_value = None
    process.terminate.side_effect = stopped.set
    factory = Mock(return_value=process)
    monkeypatch.setattr(pulse.subprocess, "Popen", factory)
    callback = Mock()
    stream = pulse.PulseStream("bluez_input.test", callback)
    stream.start()
    stream.close()
    command = factory.call_args.args[0]
    assert "--device=bluez_input.test" in command
    assert "--format=s16le" in command
    assert "--rate=16000" in command
    assert "--channels=1" in command
    assert "--property=media.role=Communication" in command
    callback.assert_called_once_with(b"\x01\0" * 320, 320, None, None)
    assert not stream.thread.is_alive()
    process.stdout.close.assert_called_once()


def test_pulse_startup_failure_terminates_process(monkeypatch):
    monkeypatch.setattr(pulse.select, "select", lambda readers, *_: (readers, [], []))
    process = Mock(stdout=io.BytesIO())
    process.poll.return_value = 1
    monkeypatch.setattr(pulse.subprocess, "Popen", Mock(return_value=process))
    stream = pulse.PulseStream(None, Mock())
    with pytest.raises(RuntimeError, match="did not start"):
        stream.start()
    assert process.stdout.closed
    assert not stream.thread.is_alive()


def test_pulse_shutdown_kills_unresponsive_process():
    process = Mock()
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("parec", 2), 0]
    stream = pulse.PulseStream(None, Mock())
    stream.process = process
    stream.close()
    process.terminate.assert_called_once()
    process.kill.assert_called_once()
    process.stdout.close.assert_called_once()


def test_stalled_stream_reports_transport_failure_instead_of_silence(monkeypatch):
    stream = pulse.PulseStream("bluez_input.test", Mock())
    stream.process = Mock()
    stream.process.stdout.read.return_value = b"\0" * 640
    readiness = Mock(side_effect=[([stream.process.stdout], [], []), ([], [], [])])
    monkeypatch.setattr(pulse.select, "select", readiness)
    stream.read()
    assert stream.started
    assert stream.ready.is_set()
    assert stream.callback.call_args.args[:3] == (b"", 0, None)
    assert "stopped sending audio" in stream.callback.call_args.args[3]
    assert readiness.call_args.args[3] == 2


def test_partial_pipe_reads_are_combined_into_complete_pcm_blocks(monkeypatch):
    stream = pulse.PulseStream("bluez_input.test", Mock())
    stream.process = Mock()
    stream.process.stdout.read.side_effect = [b"\x01\0" * 100, b"\x02\0" * 220, b""]
    monkeypatch.setattr(pulse.select, "select", lambda readers, *_: (readers, [], []))
    stream.read()
    stream.callback.assert_any_call(b"\x01\0" * 100 + b"\x02\0" * 220, 320, None, None)
    assert [call.args[0] for call in stream.process.stdout.read.call_args_list] == [640, 440, 640]


def test_stop_during_poll_does_not_report_a_capture_error(monkeypatch):
    stream = pulse.PulseStream(None, Mock())
    stream.process = Mock()

    def stopped(*_):
        stream.stopping.set()
        return [], [], []

    monkeypatch.setattr(pulse.select, "select", stopped)
    stream.read()
    stream.callback.assert_not_called()


def test_real_pipe_that_stalls_after_start_reports_an_error(monkeypatch):
    reader, writer = os.pipe()
    process = Mock(stdout=os.fdopen(reader, "rb", buffering=0))
    process.poll.return_value = 0
    monkeypatch.setattr(pulse.subprocess, "Popen", Mock(return_value=process))
    capture = Capture(App())
    stream = pulse.PulseStream("bluez_input.test", capture.callback)
    try:
        os.write(writer, b"\x01\0" * 320)
        stream.start()
        stream.thread.join(timeout=3)
        assert not stream.thread.is_alive()
        assert "stopped sending audio" in capture.error
        assert capture.size == 640
    finally:
        stream.close()
        os.close(writer)
        capture.discard()
