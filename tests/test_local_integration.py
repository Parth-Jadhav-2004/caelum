import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from caelum.config import Config, load, save, validate
from caelum.hardware import Hardware, detect
from caelum.models import recommend
from caelum.onboarding import privacy
from caelum.providers import ProviderError, Providers, Transcript


def local_config():
    config = Config()
    config.stt.engine = "local"
    config.stt.local_model = "parakeet-v3"
    return config


def test_legacy_defaults_and_cloud_alias(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[stt]\nmodel = "existing-online-model"\n')
    assert load(path).stt.engine == "online"
    assert load(path).stt.fallback == "none"
    path.write_text('[stt]\nengine = "cloud"\n')
    assert load(path).stt.engine == "online"


def test_local_validation_is_private_but_online_fallback_validates_urls(tmp_path):
    config = local_config()
    config.stt.base_url = "not a URL"
    config.cleanup.base_url = "not a URL"
    assert validate(config)
    config.stt.fallback = "online"
    with pytest.raises(ValueError, match="HTTPS"):
        validate(config)
    config.stt.fallback = "local"
    with pytest.raises(ValueError, match="Fallback"):
        validate(config)


@pytest.mark.parametrize("field,value", [
    ("engine", "unknown"), ("local_model", "not-a-model"),
    ("local_threads", -1), ("local_threads", True), ("fallback", "silent"),
])
def test_invalid_local_settings(field, value):
    config = local_config()
    setattr(config.stt, field, value)
    with pytest.raises((ValueError, RuntimeError)):
        validate(config)


async def test_local_dictation_and_cleanup_never_call_http_or_credentials():
    config = local_config()
    config.cleanup.model = "online-refinement-is-configured"
    client = AsyncMock()
    provider = Providers(config, client=client,
                         credential_resolver=lambda _: pytest.fail("Credential accessed"))
    provider._local_stt = AsyncMock(return_value=Transcript("Private words", []))
    result = await provider.stt(b"pcm")
    assert await provider.cleanup(result.text) == ("Private words", False)
    assert provider.metrics["engine"] == "local"
    assert provider.metrics["http_calls"] == provider.metrics["uploaded_audio_bytes"] == 0
    client.get.assert_not_called()
    client.post.assert_not_called()
    await provider.aclose()


@pytest.mark.parametrize("fallback,expected", [("none", False), ("online", True)])
async def test_local_failure_uploads_only_when_explicitly_enabled(fallback, expected):
    config = local_config()
    config.stt.fallback = fallback
    provider = Providers(config, client=AsyncMock())
    provider._local_stt = AsyncMock(side_effect=ProviderError("Speech model not downloaded", "missing_model"))
    provider._online_stt = AsyncMock(return_value=Transcript("Online result", []))
    try:
        if expected:
            assert (await provider.stt(b"pcm")).text == "Online result"
            assert provider.metrics["fallback"] == provider.metrics["engine"] == "online"
            assert provider.metrics["model"] == config.stt.model
            provider._online_stt.assert_awaited_once()
        else:
            with pytest.raises(ProviderError):
                await provider.stt(b"pcm")
            provider._online_stt.assert_not_called()
    finally:
        await provider.aclose()


@pytest.mark.parametrize("kind,expected", [
    ("offline", True), ("timeout", True), ("quota", True),
    ("invalid_key", False), ("rate_limit", False), ("permission", False),
])
async def test_online_fallback_is_once_and_only_for_allowed_failures(kind, expected):
    config = Config()
    config.stt.fallback, config.stt.local_model = "local", "parakeet-110m"
    config.cleanup.model = "never-refine-local-fallback"
    provider = Providers(config, client=AsyncMock())
    provider._online_stt = AsyncMock(side_effect=ProviderError("safe", kind))
    provider._local_stt = AsyncMock(return_value=Transcript("Local result", []))
    try:
        if expected:
            result = await provider.stt(b"pcm")
            assert await provider.cleanup(result.text) == ("Local result", False)
            assert provider.metrics["fallback"] == provider.metrics["engine"] == "local"
            provider._local_stt.assert_awaited_once()
        else:
            with pytest.raises(ProviderError):
                await provider.stt(b"pcm")
            provider._local_stt.assert_not_called()
        provider._online_stt.assert_awaited_once()
    finally:
        await provider.aclose()


async def test_background_load_returns_immediately_and_can_retry_missing_model(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    engine = AsyncMock()
    engine.decode_ms = 12

    async def load_model(_):
        entered.set()
        await release.wait()

    engine.load.side_effect = load_model
    monkeypatch.setattr("caelum.local_stt.LocalEngine", lambda **_: engine)
    provider = Providers(local_config(), client=AsyncMock())
    try:
        provider.configure_local()
        assert provider.engine_status()["state"] == "loading"
        await entered.wait()
        assert not provider.local_task.done()
        release.set()
        await provider.local_task
        assert provider.engine_status()["state"] == "ready"
        engine.load.side_effect = ProviderError("Speech model not downloaded", "missing_model")
        provider.configure_local(force=True)
        await provider.local_task
        assert provider.engine_status()["state"] == "missing"
        engine.load.side_effect = None
        provider.configure_local(force=True)
        await provider.local_task
        assert provider.engine_status()["state"] == "ready"
    finally:
        await provider.aclose()


def test_privacy_tracks_engine_and_explicit_fallback():
    config = local_config()
    assert privacy(config).startswith("Audio stays on this computer. Caelum downloads")
    config.stt.fallback = "online"
    assert "that dictation is sent to your online provider" in privacy(config)
    assert "History is not encrypted" in privacy(config)


@pytest.mark.parametrize("total,available,cores,language,expected", [
    (16384, 8000, 8, "en", "parakeet-v3"),
    (16384, 8000, 8, "de", "parakeet-v3"),
    (8192, 4000, 4, "en", "parakeet-v3"),
    (4096, 2000, 2, "en", "parakeet-110m"),
    (16384, 8000, 8, "hi", None),
    (16384, 8000, 8, "mr", None),
    (16384, 8000, 8, "ja", "cohere-transcribe"),
    (6144, 4000, 4, "ja", "whisper-turbo"),
    (16384, 8000, 8, "sw", "whisper-turbo"),
    (4096, 1900, 2, "de", None),
    (4096, 2100, 2, "de", "parakeet-v3"),
])
def test_recommendation_table(total, available, cores, language, expected):
    hardware = Hardware(mem_total_mb=total, mem_available_mb=available, cores=cores,
                        language=language, arch="x86_64", avx2=True)
    result = recommend(hardware)
    assert result["id"] == expected
    if expected == "whisper-turbo":
        assert "slower on this computer" in result["reason_text"]


def test_no_avx2_and_locale_detection(monkeypatch):
    hardware = Hardware(mem_total_mb=16384, mem_available_mb=8000, cores=8,
                        language="en", arch="x86_64")
    assert recommend(hardware)["id"] is None
    assert recommend(replace(hardware, arch="aarch64"))["id"] == "parakeet-v3"
    monkeypatch.setenv("LC_ALL", "hi_IN.UTF-8")
    assert detect(Config()).language == "hi"
    config = Config()
    config.stt.language = "de"
    assert detect(config).language == "de"


async def test_local_history_records_actual_engine_and_has_no_online_charge(tmp_path):
    from caelum.history import History

    config = Config()
    path = tmp_path / "config.toml"
    save(config, path)
    history = History(path)
    history.record("local-fallback", "Local words", {
        "capture_ms": 1000, "engine": "local", "model": "parakeet-110m",
    }, config, False, False)
    row = history.read()[0]
    assert row["engine"] == "local"
    assert row["stt_model"] == "parakeet-110m"
    assert row["estimated_stt_usd"] == 0
