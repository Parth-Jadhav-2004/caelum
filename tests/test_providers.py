import asyncio
import json
from unittest.mock import AsyncMock, Mock

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


@pytest.mark.parametrize(
    "status,body,kind",
    [
        (401, {}, "invalid_key"),
        (403, {}, "permission"),
        (402, {}, "quota"),
        (429, {}, "rate_limit"),
        (429, {"error": {"code": "insufficient_quota"}}, "quota"),
        (503, {}, "unavailable"),
        (404, {}, "model"),
    ],
)
async def test_provider_failure_categories(config, monkeypatch, status, body, kind):
    monkeypatch.setattr("caelum.providers.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    ) as client:
        provider = Providers(config, client)
        with pytest.raises(ProviderError) as error:
            await provider.stt(b"\0" * 100)
        assert error.value.kind == kind
        with pytest.raises(ProviderError) as error:
            await provider.models(config.stt)
        assert error.value.kind == kind


async def test_retry_after_is_honored(config, monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("caelum.providers.asyncio.sleep", sleep)
    responses = iter([
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200, json={"text": "ok"}),
    ])
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: next(responses))
    ) as client:
        assert (await Providers(config, client).stt(b"\0" * 100)).text == "ok"
    sleep.assert_awaited_once_with(2.0)


@pytest.mark.parametrize("failure,kind", [
    (httpx.ConnectError, "offline"),
    (httpx.ReadTimeout, "timeout"),
])
async def test_transport_failure_categories(config, failure, kind):
    def respond(request):
        raise failure("sensitive details", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client)
        with pytest.raises(ProviderError) as error:
            await provider.stt(b"\0" * 100)
        assert error.value.kind == kind
        assert "sensitive" not in str(error.value)
        assert await provider.cleanup("hello") == ("hello", False)
        assert provider.metrics["cleanup_error"] == kind


@pytest.mark.parametrize("host,token_field,store", [
    ("api.groq.com/openai", "max_tokens", False),
    ("api.openai.com", "max_completion_tokens", True),
    ("custom.example", "max_tokens", False),
])
async def test_cleanup_request_fields(config, host, token_field, store):
    config.cleanup.base_url = f"https://{host}/v1"
    config.cleanup.reasoning_effort = ""
    def respond(request):
        body = json.loads(request.content)
        assert token_field in body
        assert ("store" in body) is store
        assert "reasoning_effort" not in body
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello."}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await Providers(config, client).cleanup("hello") == ("Hello.", True)


async def test_missing_cleanup_key_falls_back_without_request(config, monkeypatch):
    monkeypatch.delenv(config.cleanup.key_env)
    respond = Mock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        provider = Providers(config, client)
        assert await provider.cleanup("hello") == ("hello", False)
        assert provider.metrics["cleanup_error"] == "missing_key"
        respond.assert_not_called()


@pytest.mark.parametrize("effort,expected", [("none", None), ("low", "low"), ("max", None)])
async def test_groq_refinement_reasoning_fields(config, effort, expected):
    config.cleanup.model = "openai/gpt-oss-20b"
    config.cleanup.reasoning_effort = effort

    def respond(request):
        body = json.loads(request.content)
        assert body.get("reasoning_effort") == expected
        assert "store" not in body and "max_completion_tokens" not in body
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hello."}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await Providers(config, client).cleanup("hello") == ("Hello.", True)


async def test_retry_after_longer_than_deadline_does_not_retry_early(config):
    config.stt.timeout_seconds = 0.02
    respond = Mock(return_value=httpx.Response(429, headers={"Retry-After": "60"}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ProviderError) as error:
            await Providers(config, client).stt(b"\0" * 100)
        assert error.value.kind == "timeout"
    assert respond.call_count == 1
