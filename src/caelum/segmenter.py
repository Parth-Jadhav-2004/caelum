"""Sample-indexed hidden uploads. Ambiguous seams fall back to whole audio."""

import asyncio
import re

from .audio import RATE


def merge(chunks):
    chunks = sorted(chunks, key=lambda c: c.start)
    if not chunks:
        return ""
    if len(chunks) == 1:
        return chunks[0].text
    # Align exact token runs in the physical overlap, not arbitrary suffixes.
    # No timestamp support, disagreement, or repeated ambiguous anchors => repair whole audio.
    words = list(chunks[0].words)
    if not words:
        return None

    def token(w):
        return re.sub(r"[^\w]", "", w["word"].casefold())

    for chunk in chunks[1:]:
        if not chunk.words:
            return None
        candidates = []
        for i, old in enumerate(words):
            for j, new in enumerate(chunk.words):
                if (
                    token(old)
                    and token(old) == token(new)
                    and abs(old["start"] - new["start"]) < 0.35
                ):
                    n = 0
                    while i + n < len(words) and j + n < len(chunk.words):
                        a, b = words[i + n], chunk.words[j + n]
                        if token(a) != token(b) or abs(a["start"] - b["start"]) >= 0.35:
                            break
                        n += 1
                    if n >= 2 and i + n == len(words) and j == 0:
                        candidates.append((i, j, n))
        if len(candidates) != 1:
            return None
        i, j, n = candidates[0]
        words.extend(chunk.words[j + n :])
    return " ".join(w["word"].strip() for w in words).strip()


class Chunker:
    def __init__(self, provider, config):
        self.provider = provider
        self.step = int(config.chunk_seconds * RATE)
        self.overlap = int(config.overlap_seconds * RATE)
        self.next_end = self.step
        self.last_end = 0
        self.tasks = []

    def feed(self, pcm_source, samples):
        while samples >= self.next_end:
            start = max(0, self.last_end - self.overlap)
            end = self.next_end
            task = asyncio.create_task(self.provider.stt(pcm_source(start, end), start, end))
            # Retrieve failures immediately to avoid unhandled-task logs with provider internals.
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            self.tasks.append(task)
            self.last_end = end
            self.next_end += self.step

    async def finish(self, pcm):
        samples = len(pcm) // 2
        if not self.tasks:
            return (await self.provider.stt(pcm)).text
        # A very short tail is deliberately repaired using whole audio.
        if 0 < samples - self.last_end < RATE // 2:
            self.cancel()
            return (await self.provider.stt(pcm)).text
        if samples > self.last_end:
            start = max(0, self.last_end - self.overlap)
            self.tasks.append(
                asyncio.create_task(self.provider.stt(pcm[start * 2 :], start, samples))
            )
        try:
            chunks = await asyncio.gather(*self.tasks)
            result = merge(chunks)
            if result is not None:
                return result
        except Exception:
            self.cancel()
        return (await self.provider.stt(pcm)).text

    def cancel(self):
        for task in self.tasks:
            task.cancel()
