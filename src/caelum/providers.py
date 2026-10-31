import asyncio
import inspect
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

from .audio import RATE, wav_bytes
from .credentials import get as credential
from .quality import PROMPT, normalize, validate_cleanup


class ProviderError(RuntimeError):
    """Sanitized error: never contains response bodies, headers, or dictation."""

    def __init__(self, message, kind="unavailable"):
        super().__init__(message)
        self.kind = kind


def response_error(response):
    status = response.status_code
    kind, message = {
        401: ("invalid_key", "Invalid provider key; update the key"),
        403: ("permission", "Provider access denied; check key permissions"),
        402: ("quota", "Provider quota exhausted; check usage or billing"),
        429: ("rate_limit", "Provider rate limit reached; retry later"),
        404: ("model", "Provider model or endpoint unavailable; check settings"),
    }.get(status, ("unavailable", "Provider unavailable; retry or cancel"))
    # Inspect only known machine codes; never expose provider response text.
    if status in (403, 429):
        try:
            code = response.json().get("error", {}).get("code")
            if code in ("insufficient_quota", "quota_exceeded", "billing_hard_limit_reached"):
                kind, message = "quota", "Provider quota exhausted; check usage or billing"
        except (ValueError, AttributeError, TypeError):
            pass
    return ProviderError(message, kind)


def retry_delay(response, attempt):
    value = response.headers.get("Retry-After", "")
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 0
    return max(0.15 * 2**attempt + random.uniform(0, 0.15), delay)


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

    async def headers(self, provider):
        try:
            key = await asyncio.to_thread(credential, provider.key_env)
        except (RuntimeError, OSError):
            raise ProviderError(
                "Saved credential unavailable; open setup to repair key storage", "credential_store"
            ) from None
        if not key:
            raise ProviderError(
                f"Missing credential: {provider.key_env}; add the key", "missing_key"
            )
        return {"Authorization": f"Bearer {key}"}

    async def models(self, provider):
        try:
            response = await self.client.get(
                provider.base_url.rstrip("/") + "/models",
                headers=await self.headers(provider),
                timeout=10,
            )
            if response.is_error:
                raise response_error(response)
            return sorted(item["id"] for item in response.json()["data"])
        except httpx.TimeoutException:
            raise ProviderError("Provider timed out; retry later", "timeout") from None
        except httpx.ConnectError:
            raise ProviderError("Provider unreachable; check your connection", "offline") from None
        except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
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
                            headers=await self.headers(cfg),
                            data=data,
                            files={"file": ("dictation.wav", payload, "audio/wav")},
                            timeout=cfg.timeout_seconds,
                        )
                        if response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                            break
                        if response_error(response).kind == "quota":
                            break
                        self.metrics["retries"] += 1
                        await asyncio.sleep(retry_delay(response, attempt))
                    if response.is_error:
                        raise response_error(response)
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
            except (httpx.TimeoutException, TimeoutError):
                raise ProviderError("Transcription timed out; retry or cancel", "timeout") from None
            except httpx.ConnectError:
                raise ProviderError(
                    "Provider unreachable; check your connection and retry", "offline"
                ) from None
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
                raise ProviderError("Transcription unavailable; retry or cancel") from None

    async def cleanup(self, raw, on_refining=lambda: None):
        cfg = self.config.cleanup
        if not cfg.model:
            return raw, False
        began = time.monotonic()
        try:
            async with asyncio.timeout(cfg.timeout_seconds):
                headers = await self.headers(cfg)
                indication = on_refining()
                if inspect.isawaitable(indication):
                    await indication
                self.metrics["http_calls"] += 1
                response = await self.client.post(
                    cfg.base_url.rstrip("/") + "/chat/completions",
                    headers=headers,
                    json={
                        "model": cfg.model,
                        **(
                            {"store": False}
                            if urlparse(cfg.base_url).hostname == "api.openai.com"
                            else {}
                        ),
                        (
                            "max_completion_tokens"
                            if urlparse(cfg.base_url).hostname == "api.openai.com"
                            else "max_tokens"
                        ): max(256, min(8192, len(raw) * 2)),
                        **(
                            {"reasoning_effort": cfg.reasoning_effort}
                            if cfg.reasoning_effort
                            and (
                                urlparse(cfg.base_url).hostname != "api.groq.com"
                                or (
                                    cfg.model in ("openai/gpt-oss-20b", "openai/gpt-oss-120b")
                                    and cfg.reasoning_effort in ("low", "medium", "high")
                                )
                            )
                            else {}
                        ),
                        "messages": [
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": raw},
                        ],
                    },
                    timeout=cfg.timeout_seconds,
                )
                if response.is_error:
                    raise response_error(response)
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
        except ProviderError as error:
            self.metrics["cleanup_error"] = error.kind
            return raw, False
        except (httpx.TimeoutException, TimeoutError):
            self.metrics["cleanup_error"] = "timeout"
            return raw, False
        except httpx.ConnectError:
            self.metrics["cleanup_error"] = "offline"
            return raw, False
        except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError, AttributeError):
            self.metrics["cleanup_error"] = "unavailable"
            return raw, False
        finally:
            self.metrics["cleanup_ms"] = (time.monotonic() - began) * 1000
