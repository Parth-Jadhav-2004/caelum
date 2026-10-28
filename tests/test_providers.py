import asyncio
import json

import httpx
import pytest

from caelum.config import Config
from caelum.providers import ProviderError, Providers
from caelum.quality import validate_cleanup


@pytest.mark.parametrize(
    "raw,result,expected",
    [
        ("hello world", "Hello, world.", True),
        ("hello world", "", False),
        ("call 5551234 tomorrow", "Call 5551235 tomorrow.", False),
        ("use https://example.com/a", "Use https://example.com/b", False),
        ("hello", "Hello and welcome to my newsletter", False),
        ("नमस्ते world", "नमस्ते, world.", True),
        ("very very good", "Very good.", False),
    ],
)
def test_cleanup_validation(raw, result, expected):
    text, valid = validate_cleanup(raw, result)
    assert valid is expected
    if not expected:
        assert text == raw


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-not-a-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-secret")
    cfg = Config()
    cfg.cleanup.model = "test-model"
    return cfg


async def test_stt_file_upload_offsets_and_no_streaming(config):
    def respond(request):
        assert request.url.path.endswith("/audio/transcriptions")
        assert b'filename="dictation.wav"' in request.content
        assert b"RIFF" in request.content
        return httpx.Response(
            200, json={"text": "hello", "words": [{"word": "hello", "start": 0.1, "end": 0.5}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client)
        result = await provider.stt(b"\0" * 32000, start=16000)
        assert result.words[0]["start"] == 1.1
        assert result.end == 32000
        assert provider.metrics["http_calls"] == 1
        assert "hello" not in json.dumps(provider.metrics)


async def test_rate_limit_bounded_retry(config, monkeypatch):
    calls = 0

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr("caelum.providers.asyncio.sleep", no_sleep)

    def respond(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={"text": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client)
        assert (await provider.stt(b"\0" * 1000)).text == "ok"
        assert calls == 3
        assert provider.metrics["retries"] == 2


async def test_error_is_sanitized(config):
    def respond(request):
        return httpx.Response(500, text="secret-provider-body audio transcript")

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client)
        with pytest.raises(ProviderError) as error:
            await provider.stt(b"\0" * 100)
        assert "secret-provider-body" not in str(error.value)


async def test_cleanup_timeout_falls_back(config):
    config.cleanup.timeout_seconds = 0.2

    async def respond(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client)
        states = []
        text, refined = await provider.cleanup("actual words", lambda: states.append("refining"))
        assert text == "actual words" and not refined
        assert states == ["refining"]
        assert provider.metrics["cleanup_ms"] < 400


async def test_cleanup_unconfigured_does_not_claim_refinement(config):
    config.cleanup.model = ""
    async with httpx.AsyncClient() as client:
        provider = Providers(config, client)
        states = []
        assert await provider.cleanup("hello", lambda: states.append("refining")) == (
            "hello",
            False,
        )
        assert states == []
