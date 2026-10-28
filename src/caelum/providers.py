import asyncio
import inspect
import os
import random
import time
from dataclasses import dataclass

import httpx

from .audio import RATE, wav_bytes
from .quality import PROMPT, normalize, validate_cleanup


class ProviderError(RuntimeError):
    """Sanitized error: never contains response bodies, headers, or dictation."""


@dataclass
class Transcript:
    text: str
    words: list
    start: int = 0
    end: int = 0


class Providers:
    def __init__(self, config, client=None):
        self.config = config
        self.client = client or httpx.AsyncClient(
            limits=httpx.Limits(max_connections=5), follow_redirects=False
        )
        self.semaphore = asyncio.Semaphore(config.stt.concurrency)
        self.reset_metrics()

    def reset_metrics(self):
        self.metrics = {
            "http_calls": 0,
            "retries": 0,
            "uploaded_audio_bytes": 0,
            "chunks": [],
            "cleanup_refined": False,
        }

    def headers(self, provider):
        key = os.environ.get(provider.key_env)
        if not key:
            raise ProviderError(f"Missing credential: {provider.key_env}")
        return {"Authorization": f"Bearer {key}"}

    async def models(self, provider):
        try:
            response = await self.client.get(
                provider.base_url.rstrip("/") + "/models",
                headers=self.headers(provider),
                timeout=10,
            )
            response.raise_for_status()
            return sorted(item["id"] for item in response.json()["data"])
        except (httpx.HTTPError, KeyError, ValueError):
            raise ProviderError("Could not verify provider model list") from None

    async def stt(self, pcm, start=0, end=None):
        cfg = self.config.stt
        end = end if end is not None else start + len(pcm) // 2
        data = {
            "model": cfg.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
        }
        if cfg.language:
            data["language"] = cfg.language
        if cfg.vocabulary:
            data["prompt"] = cfg.vocabulary
        payload = wav_bytes(pcm)
        async with self.semaphore:
            began = time.monotonic()
            try:
                async with asyncio.timeout(cfg.timeout_seconds):
                    for attempt in range(3):
                        self.metrics["http_calls"] += 1
                        self.metrics["uploaded_audio_bytes"] += len(payload)
                        response = await self.client.post(
                            cfg.base_url.rstrip("/") + "/audio/transcriptions",
                            headers=self.headers(cfg),
                            data=data,
                            files={"file": ("dictation.wav", payload, "audio/wav")},
                            timeout=cfg.timeout_seconds,
                        )
                        if response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                            break
                        self.metrics["retries"] += 1
                        await asyncio.sleep(0.15 * 2**attempt + random.uniform(0, 0.15))
                    if response.status_code in (401, 403):
                        raise ProviderError("STT credential rejected")
                    response.raise_for_status()
                    body = response.json()
                    text = normalize(body["text"])
                    words = [
                        {
                            "word": w["word"],
                            "start": float(w["start"]) + start / RATE,
                            "end": float(w["end"]) + start / RATE,
                        }
                        for w in body.get("words", [])
                    ]
                    # Whisper's segment confidence can identify noise hallucinations.
                    segments = body.get("segments", [])
                    if segments and all(s.get("no_speech_prob", 0) > 0.85 for s in segments):
                        text, words = "", []
                    self.metrics["chunks"].append(
                        {
                            "start_sample": start,
                            "end_sample": end,
                            "response_ms": (time.monotonic() - began) * 1000,
                            "request_started_monotonic": began,
                        }
                    )
                    return Transcript(text, words, start, end)
            except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError):
                raise ProviderError("Transcription unavailable; retry or cancel") from None

    async def cleanup(self, raw, on_refining=lambda: None):
        cfg = self.config.cleanup
        if not cfg.model:
            return raw, False
        began = time.monotonic()
        try:
            headers = self.headers(cfg)
            indication = on_refining()
            if inspect.isawaitable(indication):
                await indication
            self.metrics["http_calls"] += 1
            async with asyncio.timeout(cfg.timeout_seconds):
                response = await self.client.post(
                    cfg.base_url.rstrip("/") + "/chat/completions",
                    headers=headers,
                    json={
                        "model": cfg.model,
                        "store": False,
                        "max_completion_tokens": max(256, min(8192, len(raw) * 2)),
                        **(
                            {"reasoning_effort": cfg.reasoning_effort}
                            if cfg.reasoning_effort
                            else {}
                        ),
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": raw},
                        ],
                    },
                    timeout=cfg.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
                result, refined = validate_cleanup(raw, body["choices"][0]["message"]["content"])
                self.metrics["cleanup_refined"] = refined
                if isinstance(body.get("usage"), dict):
                    self.metrics["token_usage"] = {
                        k: v
                        for k, v in body["usage"].items()
                        if k in ("prompt_tokens", "completion_tokens", "total_tokens")
                        and isinstance(v, int)
                    }
                return result, refined
        except (httpx.HTTPError, TimeoutError, ProviderError, KeyError, TypeError, ValueError):
            return raw, False
        finally:
            self.metrics["cleanup_ms"] = (time.monotonic() - began) * 1000
