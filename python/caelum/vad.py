"""Offline Silero speech detection and pause-aware bounded decoding windows."""

from pathlib import Path

import numpy as np

from .audio import RATE


class Silero:
    """Created and called on the local engine's native worker. No downloads."""

    def __init__(self):
        import sherpa_onnx

        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(Path(__file__).with_name("data") / "silero_vad.onnx")
        config.silero_vad.threshold = 0.5
        config.silero_vad.min_silence_duration = 0.3
        config.silero_vad.min_speech_duration = 0.1
        config.silero_vad.max_speech_duration = 60
        config.sample_rate = RATE
        config.num_threads = 1
        config.provider = "cpu"
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=90)
        self.window = config.silero_vad.window_size

    def __call__(self, samples):
        self.vad.reset()
        regions = []

        def drain():
            while not self.vad.empty():
                segment = self.vad.front
                # Preserve consonants just before/after a detected speech span.
                begin = max(0, segment.start - int(0.15 * RATE))
                end = min(len(samples), segment.start + len(segment.samples) + int(0.15 * RATE))
                if end > begin:
                    if regions and begin <= regions[-1][1]:
                        regions[-1] = (regions[-1][0], max(end, regions[-1][1]))
                    else:
                        regions.append((begin, end))
                self.vad.pop()

        for offset in range(0, len(samples), self.window):
            window = samples[offset:offset + self.window]
            if len(window) < self.window:
                window = np.pad(window, (0, self.window - len(window)))
            self.vad.accept_waveform(window)
            drain()
        self.vad.flush()
        drain()
        return regions


def pause_chunks(regions, limit_seconds):
    """Pack speech spans into bounded windows, splitting at detected pauses.

    Offsets stay in original recording coordinates. Distant silence never enters
    the decoder. Continuous speech is hard-bounded without skipping any samples.
    """
    limit = int(limit_seconds * RATE)
    if not regions:
        return
    begin, end = regions[0]
    for following, stop in regions[1:]:
        # Use the first natural pause after roughly half a window. Filling a
        # sequence decoder to its ceiling can still encourage early EOS or
        # collapse repeated utterances, even below the hard duration bound.
        if stop - begin <= limit and end - begin < limit * 0.45:
            end = stop
            continue
        while end - begin > limit:
            yield begin, begin + limit
            begin += limit
        if end > begin:
            yield begin, end
        begin, end = following, stop
    while end - begin > limit:
        yield begin, begin + limit
        begin += limit
    if end > begin:
        yield begin, end
