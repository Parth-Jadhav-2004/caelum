import io
import wave

import numpy as np

from caelum.audio import BLOCK, RATE, Capture, wav_bytes
from caelum.config import App


def test_pcm_wav_is_lossless():
    pcm = np.arange(1000, dtype=np.int16).tobytes()
    with wave.open(io.BytesIO(wav_bytes(pcm)), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, RATE)
        assert wav.readframes(1000) == pcm


def test_capture_bounds_and_quiet_audio_not_gated():
    capture = Capture(App(max_recording_seconds=1))
    quiet = np.full(BLOCK, 40, dtype=np.int16).tobytes()
    for _ in range(60):
        capture.callback(quiet, BLOCK, None, None)
    assert capture.full
    assert capture.size == RATE * 2
    assert capture.snapshot() == quiet * 50
    assert capture.speech_ms > 0
    assert len(capture.history) == 17


def test_hysteresis_settles_and_preserves_silence():
    capture = Capture(App())
    voice = np.full(BLOCK, 2000, dtype=np.int16).tobytes()
    silence = b"\0" * BLOCK * 2
    for _ in range(5):
        capture.callback(voice, BLOCK, None, None)
    assert capture.speaking
    level = capture.level
    capture.callback(silence, BLOCK, None, None)
    assert capture.speaking
    for _ in range(60):
        capture.callback(silence, BLOCK, None, None)
    assert not capture.speaking
    assert capture.level < level / 100
    assert capture.snapshot().endswith(silence * 61)
