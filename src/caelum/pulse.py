"""Named PipeWire/PulseAudio inputs with server-side PCM conversion."""

import json
import select
import shutil
import subprocess
import threading
import time
from collections import Counter


def sources():
    if not shutil.which("pactl") or not shutil.which("parec"):
        return None
    try:
        result = subprocess.run(
            ["pactl", "--format=json", "list", "sources"],
            capture_output=True, text=True, check=True, timeout=2,
        )
        devices = json.loads(result.stdout)
        return [device for device in devices if
                not device["name"].endswith(".monitor")
                and device.get("properties", {}).get("device.class") != "monitor"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def microphones():
    devices = sources()
    if devices is None:
        return None
    counts = Counter(device["description"] for device in devices)
    return [
        (device["description"] if counts[device["description"]] == 1
         else f'{device["description"]} · {device["name"]}', "pulse:" + device["name"])
        for device in devices
    ]


def disconnected_bluetooth_fallback(selection, devices):
    if not selection or not selection.startswith("bluez_input.") or devices is None:
        return None
    if any(device["name"] == selection for device in devices):
        return None
    for device in devices:
        properties = device.get("properties", {})
        if device["name"].startswith("alsa_input.") and (
            properties.get("device.form_factor") == "internal"
            or properties.get("device.bus") in ("pci", "platform")
        ):
            return device
    return None


def resolve(selection):
    if isinstance(selection, int):
        return None
    devices = sources()
    named = isinstance(selection, str) and selection.startswith("pulse:")
    if devices is None:
        if named:
            raise RuntimeError("Audio server unavailable; reconnect the microphone and retry")
        return None
    if selection is None:
        if not devices:
            raise RuntimeError("No microphones detected; connect an input device and retry")
        return {"name": None}
    name = selection.removeprefix("pulse:")
    matches = [device for device in devices if device["name"] == name]
    if not matches and not named:
        matches = [device for device in devices if device["description"] == selection]
    if len(matches) > 1:
        raise RuntimeError("Multiple microphones have this name; select one again in Settings")
    if matches:
        return matches[0]
    if named:
        fallback = disconnected_bluetooth_fallback(name, devices)
        if fallback is not None:
            return fallback
        raise RuntimeError("Selected microphone disconnected; reconnect it or choose another input")
    return None


class PulseStream:
    def __init__(self, source, callback):
        self.source = source
        self.callback = callback
        self.process = None
        self.thread = None
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.started = False
        self.process_lock = threading.Lock()

    def open_process(self):
        command = [
            "parec", "--raw", "--format=s16le", "--rate=16000", "--channels=1",
            "--latency-msec=20", "--client-name=Caelum", "--stream-name=Dictation",
            "--property=media.role=Communication",
        ]
        if self.source is not None:
            command.append("--device=" + self.source)
        self.process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0,
        )

    def start(self):
        self.open_process()
        self.thread = threading.Thread(target=self.read, name="caelum-audio", daemon=True)
        self.thread.start()
        if not self.ready.wait(4) or not self.started:
            self.close()
            raise RuntimeError("Microphone did not start; reconnect it and check the headset profile")

    def fallback(self):
        if self.stopping.is_set() or not self.source or not self.source.startswith("bluez_input."):
            return False
        device = disconnected_bluetooth_fallback(self.source, sources())
        if device is None:
            return False
        with self.process_lock:
            if self.stopping.is_set():
                return False
            self.terminate_process()
            self.process.stdout.close()
            self.source = device["name"]
            self.open_process()
        return True

    def read(self):
        pending = bytearray()
        next_check = time.monotonic() + 1
        try:
            while not self.stopping.is_set():
                if time.monotonic() >= next_check:
                    if self.fallback():
                        pending.clear()
                    next_check = time.monotonic() + 1
                readable, _, _ = select.select([self.process.stdout], [], [], 2)
                if not readable:
                    if self.fallback():
                        pending.clear()
                        continue
                    if not self.stopping.is_set():
                        self.callback(
                            b"", 0, None,
                            "Microphone stopped sending audio. Disconnect and reconnect "
                            "the headset, then test again.",
                        )
                    break
                data = self.process.stdout.read(640 - len(pending))
                if not data:
                    if self.fallback():
                        pending.clear()
                        continue
                    if not self.stopping.is_set():
                        self.callback(b"", 0, None, "Microphone disconnected or capture interrupted")
                    break
                pending.extend(data)
                if len(pending) < 640:
                    continue
                self.callback(bytes(pending), 320, None, None)
                pending.clear()
                self.started = True
                self.ready.set()
        except (OSError, ValueError):
            if not self.stopping.is_set():
                self.callback(b"", 0, None, True)
        finally:
            self.ready.set()

    def terminate_process(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def stop(self):
        self.stopping.set()
        with self.process_lock:
            self.terminate_process()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def close(self):
        self.stop()
        if self.process is not None:
            self.process.stdout.close()
