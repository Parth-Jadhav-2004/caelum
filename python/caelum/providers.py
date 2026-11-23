import asyncio
import inspect
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

from .audio import RATE, wav_bytes
from .credentials import get as credential
from .quality import cleanup_prompt, normalize, validate_cleanup


def contributor_scope(provider):
    """Consent is tied to the exact endpoint and model, including custom aliases."""
    return provider.base_url.rstrip("/") + "|" + provider.model


def needs_contributor_consent(provider):
    return "contributor" in (provider.model + " " + provider.base_url).casefold()


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
    language: str = ""


class Providers:
    def __init__(self, config, client=None, credential_resolver=None):
        self.config = config
        self.credential_resolver = credential_resolver or credential
        self.client = client or httpx.AsyncClient(
            limits=httpx.Limits(max_connections=5), follow_redirects=False
        )
        self.semaphore = asyncio.Semaphore(config.stt.concurrency)
        self.local_engine = None
        self.local_task = None
        self.local_signature = None
        self.local_state = "missing"
        self.local_message = ""
        self.on_loading = None
        self.on_processing = None
        self.idle_handle = None
        self.idle_task = None
        self.local_activity = 0
        self._closing = False
        self.reset_metrics()

    @staticmethod
    def signature(config):
        cfg = config.stt
        wanted = cfg.engine == "local" or cfg.fallback == "local"
        return (cfg.local_model if wanted else "", cfg.local_threads,
                cfg.language.split("_")[0].split("-")[0].lower(), cfg.vocabulary,
                config.app.silence_dbfs, cfg.local_device)

    async def prepare_local(self, config):
        """Load a candidate without altering the active engine or configuration."""
        signature = self.signature(config)
        if not signature[0]:
            return None
        from .local_stt import LocalEngine

        candidate = LocalEngine(threads=signature[1], language=signature[2],
                                vocabulary=signature[3], silence_dbfs=signature[4],
                                device=signature[5])
        try:
            await candidate.load(signature[0])
            return candidate
        except BaseException:
            await candidate.aclose()
            raise

    async def commit_local(self, config, candidate):
        previous = self.local_engine
        self.local_engine = candidate
        self.local_signature = self.signature(config)
        self.local_state, self.local_message = ("ready" if candidate else "missing"), ""
        if previous and previous is not candidate:
            await previous.aclose()
        self.arm_idle(config)

    def configure_local(self, force=False):
        """Schedule startup loading; model changes use prepare/commit before saving."""
        if self._closing:
            return
        signature = self.signature(self.config)
        if signature == self.local_signature and not force:
            return
        self.local_signature = signature
        previous = self.local_task
        self.local_state = "loading" if signature[0] else "missing"
        config = self.config

        async def refresh():
            if previous:
                await asyncio.gather(asyncio.shield(previous), return_exceptions=True)
            if signature != self.local_signature:
                return
            try:
                candidate = await self.prepare_local(config)
                if signature != self.local_signature:
                    if candidate:
                        await candidate.aclose()
                    return
                await self.commit_local(config, candidate)
            except ProviderError as error:
                if signature == self.local_signature:
                    self.local_state = "missing" if error.kind == "missing_model" else "error"
                    self.local_message = str(error)
        self.local_task = asyncio.create_task(refresh())

    def cancel_idle(self):
        self.local_activity += 1
        if self.idle_handle:
            self.idle_handle.cancel()
            self.idle_handle = None

    def arm_idle(self, config=None):
        self.cancel_idle()
        seconds = (config or self.config).stt.local_idle_seconds
        if self._closing or not seconds or not self.local_engine or self.local_state != "ready":
            return
        revision = self.local_activity
        engine = self.local_engine

        async def release():
            # Work may have started after the timer fired but before this task ran.
            if revision != self.local_activity or self.local_engine is not engine:
                return
            await engine.unload()
            # Activity can cancel the timer, but cannot undo a completed unload.
            if self.local_engine is engine:
                self.local_state = "unloaded"

        def expire():
            self.idle_handle = None
            self.idle_task = asyncio.create_task(release())
        self.idle_handle = asyncio.get_running_loop().call_later(seconds, expire)

    def engine_status(self):
        cfg = self.config.stt
        if cfg.engine != "local":
            return {"kind": "online", "model": None, "state": "ready", "message": ""}
        message = self.local_message
        if self.local_state == "ready" and self.local_engine:
            device = getattr(self.local_engine, "active_device", None)
            if device in ("cpu", "cuda"):
                message = "Using NVIDIA CUDA" if device == "cuda" else "Using CPU"
        return {"kind": "local", "model": cfg.local_model or None,
                "state": self.local_state, "message": message}

    async def aclose(self):
        self._closing = True
        self.cancel_idle()
        if self.idle_task:
            await asyncio.gather(self.idle_task, return_exceptions=True)
        if self.local_task:
            await asyncio.gather(self.local_task, return_exceptions=True)
        if self.local_engine:
            await self.local_engine.aclose()
        await self.client.aclose()

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
            key = await asyncio.to_thread(self.credential_resolver, provider.key_env)
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
        if provider is self.config.stt and provider.engine == "local":
            if provider.local_model:
                import importlib.util

                from .models import EXTRA_MODULES, get_model, installed

                if not installed(provider.local_model):
                    raise ProviderError("Speech model not downloaded", "missing_model")
                model = get_model(provider.local_model)
                extra = model["requires_extra"] or "local"
                if importlib.util.find_spec(EXTRA_MODULES[extra]) is None:
                    raise ProviderError("Needs an extra component.", "local_setup")
                return [provider.local_model]
            raise ProviderError("Speech model not downloaded", "missing_model")
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
        kind = "local" if cfg.engine == "local" else "online"
        try:
            result = await (self._local_stt(pcm, start, end) if kind == "local"
                            else self._online_stt(pcm, start, end))
        except ProviderError as error:
            if kind == "local" and cfg.fallback == "online" and error.kind in {
                "missing_model", "local_setup",
            }:
                if self.on_processing:
                    await self.on_processing()
                result = await self._online_stt(pcm, start, end)
                kind = "online"
            elif kind == "online" and cfg.fallback == "local" and error.kind in {
                "offline", "timeout", "quota",
            }:
                result = await self._local_stt(pcm, start, end)
                kind = "local"
            else:
                raise
            self.metrics["fallback"] = kind
        self.metrics["engine"] = kind
        self.metrics["model"] = cfg.local_model if kind == "local" else cfg.model
        self.metrics["language"] = result.language or cfg.language or "auto"
        return result

    async def _local_stt(self, pcm, start=0, end=None):
        cfg = self.config.stt
        end = end if end is not None else start + len(pcm) // 2
        self.cancel_idle()
        if self.idle_task:
            await asyncio.gather(self.idle_task, return_exceptions=True)
            self.idle_task = None
        self.configure_local(force=self.local_state in ("unloaded", "missing", "error"))
        loading = self.local_state == "loading"
        if loading and self.on_loading:
            await self.on_loading()
        if self.local_task:
            try:
                await asyncio.wait_for(asyncio.shield(self.local_task), 20)
            except TimeoutError:
                raise ProviderError("Speech model is still getting ready. Try again.",
                                    "local_load_timeout") from None
        if self.local_state != "ready" or not self.local_engine:
            raise ProviderError(self.local_message or "Speech model not downloaded",
                                "missing_model" if self.local_state == "missing" else "local_setup")
        if loading and self.on_processing:
            await self.on_processing()
        self.cancel_idle()  # Startup loading can have armed a timer while we waited.
        try:
            result = await self.local_engine.transcribe(pcm, start, end)
        finally:
            self.arm_idle()
        self.metrics["decode_ms"] = self.local_engine.decode_ms
        from .models import record_stats

        try:
            if result.text:
                await asyncio.to_thread(record_stats, cfg.local_model, self.local_engine.decode_ms)
        except OSError:
            pass  # A stats write failure must not lose a successful dictation.
        return result

    async def _online_stt(self, pcm, start=0, end=None):
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
                    return Transcript(text, words, start, end, body.get("language", ""))
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
        if self.metrics.get("engine", self.config.stt.engine) == "local":
            language = self.metrics.get("language") or self.config.stt.language
            return offline_cleanup(raw, cfg.replacements, language), False
        if not cfg.model:
            return raw, False
        if needs_contributor_consent(cfg) and cfg.contributor_consent != contributor_scope(cfg):
            self.metrics["cleanup_error"] = "consent_required"
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
                            {"role": "system", "content": cleanup_prompt(cfg.style)},
                            {"role": "user", "content": raw},
                        ],
                    },
                    timeout=cfg.timeout_seconds,
                )
                if response.is_error:
                    raise response_error(response)
                body = response.json()
                result, refined = validate_cleanup(
                    raw, body["choices"][0]["message"]["content"],
                    preserve_whitespace=cfg.style == "code",
                )
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


def offline_cleanup(text, replacements, language=""):
    """Deterministic local cleanup. Dictionary replacements run once, without cascades."""
    if language.lower().replace("_", "-").split("-")[0] == "en":
        text = re.sub(r"(?<!\w)(?:um+|uh+)(?!\w)[,.!?;:]?\s*", "", text, flags=re.I)
        text = re.sub(r"[ \t]*\bnew line\b[,.]?[ \t]*", "\n", text, flags=re.I)
    if replacements:
        keys = sorted(replacements, key=len, reverse=True)
        pattern = r"(?<!\w)(?:" + "|".join(f"({re.escape(key)})" for key in keys) + r")(?!\w)"
        # The capture index identifies the dictionary entry even when re.I
        # equates characters whose casefolds differ (for example İ and i).
        text = re.sub(pattern, lambda m: replacements[keys[m.lastindex - 1]], text, flags=re.I)
    return re.sub(r"[ \t]+([,.!?;:])", r"\1", re.sub(r"[ \t]{2,}", " ", text)).strip()
