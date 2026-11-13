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
def no_real_audio_sources(monkeypatch):
    monkeypatch.setattr(pulse, "sources", lambda: [])


@pytest.fixture
def inputs(monkeypatch):
    devices = [
        {"name": "alsa_input.builtin", "description": "Built-in Audio",
         "properties": {"device.form_factor": "internal"}},
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


def test_resolution_supports_legacy_names_and_disconnected_bluetooth_fallback(inputs):
    assert pulse.resolve("CMF Buds 2") == inputs[1]
    assert pulse.resolve("pulse:" + inputs[1]["name"]) == inputs[1]
    assert pulse.resolve(None) == {"name": None}
    assert pulse.resolve(0) is None
    assert pulse.resolve("hw:0") is None
    inputs.pop()
    assert pulse.resolve("pulse:bluez_input.2C:BE:EE:59:59:AC") == inputs[0]
    inputs.clear()
    with pytest.raises(RuntimeError, match="No microphones"):
        pulse.resolve(None)


def test_bluetooth_fallback_preserves_preference_and_uses_buds_when_reconnected(inputs, monkeypatch):
    selected = "pulse:" + inputs[1]["name"]
    bluetooth = inputs.pop()
    config = App(microphone=selected)
    stream = Mock()
    factory = Mock(return_value=stream)
    monkeypatch.setattr(pulse, "PulseStream", factory)
    capture = Capture(config)
    capture.start()
    factory.assert_called_with(inputs[0]["name"], capture.callback)
    capture.stop()
    assert config.microphone == selected
    inputs.append(bluetooth)
    capture.start()
    factory.assert_called_with(bluetooth["name"], capture.callback)
    capture.stop()


@pytest.mark.parametrize("selection", ["pulse:alsa_input.missing", "pulse:bluez_input.missing"])
def test_missing_inputs_do_not_fall_back_to_usb_or_another_bluetooth_mic(inputs, selection):
    inputs[0]["properties"] = {"device.bus": "usb"}
    with pytest.raises(RuntimeError, match="disconnected"):
        pulse.resolve(selection)


def test_missing_non_bluetooth_input_does_not_fall_back_to_builtin(inputs):
    with pytest.raises(RuntimeError, match="disconnected"):
        pulse.resolve("pulse:alsa_input.missing")


def test_bluetooth_fallback_accepts_internal_pci_input(inputs):
    inputs[0]["properties"] = {"device.bus": "pci"}
    assert pulse.resolve("pulse:bluez_input.missing") == inputs[0]


def test_connected_bluetooth_transport_failure_does_not_switch_microphones(inputs, monkeypatch):
    stream = pulse.PulseStream(inputs[1]["name"], Mock())
    stream.process = Mock()
    monkeypatch.setattr(pulse.select, "select", lambda *_: ([], [], []))
    factory = Mock()
    monkeypatch.setattr(pulse.subprocess, "Popen", factory)
    stream.read()
    factory.assert_not_called()
    assert "stopped sending audio" in stream.callback.call_args.args[3]


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


def test_stalled_stream_reports_transport_failure_instead_of_silence(monkeypatch, no_real_audio_sources):
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


def test_partial_pipe_reads_are_combined_into_complete_pcm_blocks(monkeypatch, no_real_audio_sources):
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


@pytest.mark.parametrize("failure", ["eof", "stall"])
def test_disconnect_during_recording_switches_to_builtin_without_capture_error(
    inputs, monkeypatch, failure,
):
    bluetooth = inputs.pop()
    previous = Mock(stdout=io.BytesIO(b"\x01\0" * 100))
    previous.poll.return_value = None
    builtin = Mock(stdout=io.BytesIO(b"\x02\0" * 320))
    factory = Mock(return_value=builtin)
    monkeypatch.setattr(pulse.subprocess, "Popen", factory)
    stream = pulse.PulseStream(bluetooth["name"], Mock())
    stream.process = previous
    polls = 0

    def readable(readers, *_):
        nonlocal polls
        polls += 1
        return ([], [], []) if failure == "stall" and polls == 2 else (readers, [], [])

    def received(*_):
        stream.stopping.set()

    stream.callback.side_effect = received
    monkeypatch.setattr(pulse.select, "select", readable)
    stream.read()
    assert stream.source == inputs[0]["name"]
    assert "--device=" + inputs[0]["name"] in factory.call_args.args[0]
    stream.callback.assert_called_once_with(b"\x02\0" * 320, 320, None, None)
    previous.terminate.assert_called_once()
    assert previous.stdout.closed
    stream.close()
    assert builtin.stdout.closed


def test_disconnect_is_detected_even_when_server_keeps_sending_audio(inputs, monkeypatch):
    bluetooth = inputs.pop()
    previous = Mock()
    previous.poll.return_value = None
    builtin = Mock(stdout=io.BytesIO(b"\x02\0" * 320))
    monkeypatch.setattr(pulse.subprocess, "Popen", Mock(return_value=builtin))
    monkeypatch.setattr(pulse.time, "monotonic", Mock(side_effect=[0, 2, 2]))
    monkeypatch.setattr(pulse.select, "select", lambda readers, *_: (readers, [], []))
    stream = pulse.PulseStream(bluetooth["name"], Mock())
    stream.process = previous
    stream.callback.side_effect = lambda *_: stream.stopping.set()
    stream.read()
    previous.stdout.read.assert_not_called()
    stream.callback.assert_called_once_with(b"\x02\0" * 320, 320, None, None)
    stream.close()


def test_stop_during_fallback_discovery_does_not_open_another_microphone(inputs, monkeypatch):
    bluetooth = inputs.pop()
    stream = pulse.PulseStream(bluetooth["name"], Mock())
    factory = Mock()
    monkeypatch.setattr(pulse.subprocess, "Popen", factory)

    def devices():
        stream.stopping.set()
        return inputs

    monkeypatch.setattr(pulse, "sources", devices)
    assert not stream.fallback()
    factory.assert_not_called()


def test_real_pipe_that_stalls_after_start_reports_an_error(monkeypatch, no_real_audio_sources):
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
