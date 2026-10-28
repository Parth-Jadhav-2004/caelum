"""Bounded PCM capture. The PortAudio callback never calls UI or networking."""

import io
import math
import threading
import wave
from collections import deque

import numpy as np

RATE = 16000
BLOCK = 320  # 20 ms


def wav_bytes(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)
    return out.getvalue()


def read_wav(path):
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, RATE):
            raise ValueError("Fixture must be 16 kHz mono 16-bit PCM WAV")
        return wav.readframes(wav.getnframes())


class Capture:
    def __init__(self, config):
        self.config = config
        self.capacity = RATE * config.max_recording_seconds * 2
        self.buffer = bytearray(self.capacity)
        self.size = 0
        self.level = 0.0
        self.history = deque([0.0] * 17, maxlen=17)
        self.speaking = False
        self.speech_ms = 0
        self.above = self.below = 0
        self.error = None
        self.full = False
        self.stream = None
        self.lock = threading.Lock()

    def callback(self, indata, frames, time_info, status):
        if status:
            self.error = "Audio capture interrupted"
        raw = bytes(indata)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
        rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0
        db = 20 * math.log10(max(rms, 1e-9))
        energy = min(1.0, max(0.0, (db + 55) / 43))
        dt = frames / RATE
        self.level += (energy - self.level) * (
            1 - math.exp(-dt / (0.04 if energy > self.level else 0.18))
        )
        self.history.append(self.level)
        active = db > self.config.silence_dbfs
        self.speech_ms += int(dt * 1000) if active else 0
        self.above = self.above + dt if active else 0
        self.below = self.below + dt if not active else 0
        if self.above >= 0.08:
            self.speaking = True
        if self.below >= 0.25:
            self.speaking = False
        with self.lock:
            count = min(len(raw), self.capacity - self.size)
            self.buffer[self.size : self.size + count] = raw[:count]
            self.size += count
            self.full = self.size >= self.capacity

    def start(self):
        import sounddevice as sd

        self.stream = sd.RawInputStream(
            samplerate=RATE,
            channels=1,
            dtype="int16",
            blocksize=BLOCK,
            device=self.config.microphone,
            callback=self.callback,
        )
        try:
            self.stream.start()
        except BaseException:
            self.stream.close()
            raise

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def snapshot(self, start=0, end=None):
        with self.lock:
            return bytes(
                self.buffer[start * 2 : min(self.size, end * 2 if end is not None else self.size)]
            )

    def discard(self):
        self.buffer = bytearray()
        self.size = 0
