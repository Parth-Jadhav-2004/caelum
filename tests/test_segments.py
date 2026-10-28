from caelum.audio import RATE
from caelum.config import STT
from caelum.providers import Transcript
from caelum.segmenter import Chunker, merge


def word(text, start):
    return {"word": text, "start": start, "end": start + 0.2}


def test_timestamp_overlap_preserves_spoken_repetition():
    chunks = [
        Transcript(
            "it is very very good",
            [word("it", 0), word("is", 1), word("very", 5.5), word("very", 5.9), word("good", 6.4)],
            0,
            7 * RATE,
        ),
        Transcript(
            "very good indeed",
            [word("very", 5.9), word("good", 6.4), word("indeed", 7.1)],
            5 * RATE,
            8 * RATE,
        ),
    ]
    assert merge(chunks) == "it is very very good indeed"
    assert merge(list(reversed(chunks))) == "it is very very good indeed"


def test_conflicting_or_missing_timestamps_requires_repair():
    chunks = [
        Transcript("one two", [word("one", 0), word("two", 1)], 0, 2 * RATE),
        Transcript("three four", [word("three", 1), word("four", 2)], RATE, 3 * RATE),
    ]
    assert merge(chunks) is None
    assert merge([Transcript("one two", [], 0, 2 * RATE), chunks[1]]) is None


async def test_segment_offsets_and_short_tail_repair():
    calls = []

    class Provider:
        async def stt(self, pcm, start=0, end=None):
            calls.append((start, end, len(pcm) // 2))
            return Transcript("complete phrase", [], start, end or len(pcm) // 2)

    provider = Provider()
    chunker = Chunker(provider, STT())
    pcm = b"\0" * int(7.2 * RATE) * 2
    chunker.feed(lambda a, b: pcm[a * 2 : b * 2], len(pcm) // 2)
    result = await chunker.finish(pcm)
    assert result == "complete phrase"
    assert calls[-1] == (0, None, len(pcm) // 2)


async def test_chunk_failure_falls_back_whole():
    class Provider:
        async def stt(self, pcm, start=0, end=None):
            if end is not None:
                raise RuntimeError("unavailable")
            return Transcript("whole recording", [])

    chunker = Chunker(Provider(), STT())
    pcm = b"\0" * 9 * RATE * 2
    chunker.feed(lambda a, b: pcm[a * 2 : b * 2], len(pcm) // 2)
    assert await chunker.finish(pcm) == "whole recording"
