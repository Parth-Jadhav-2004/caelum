"""Named PipeWire/PulseAudio inputs with server-side PCM conversion."""

import json
import select
import shutil
import subprocess
import threading
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

    def start(self):
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
        self.thread = threading.Thread(target=self.read, name="caelum-audio", daemon=True)
        self.thread.start()
        if not self.ready.wait(4) or not self.started:
            self.close()
            raise RuntimeError("Microphone did not start; reconnect it and check the headset profile")

    def read(self):
        pending = bytearray()
        try:
            while not self.stopping.is_set():
                readable, _, _ = select.select([self.process.stdout], [], [], 2)
                if not readable:
                    if not self.stopping.is_set():
                        self.callback(
                            b"", 0, None,
                            "Microphone stopped sending audio. Disconnect and reconnect "
                            "the headset, then test again.",
                        )
                    break
                data = self.process.stdout.read(640 - len(pending))
                if not data:
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

    def stop(self):
        self.stopping.set()
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.thread is not None:
            self.thread.join(timeout=2)

    def close(self):
        self.stop()
        if self.process is not None:
            self.process.stdout.close()
