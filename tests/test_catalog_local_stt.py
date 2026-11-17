import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from caelum import local_stt
from caelum.audio import RATE, read_wav, wav_bytes
from caelum.benchmark import local_benchmark
from caelum.config import Config
from caelum.local_stt import LocalEngine, repetition_guard
from caelum.models import catalog, models_dir
from caelum.providers import ProviderError

PCM = np.full(RATE, 2000, dtype="<i2").tobytes()


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(local_stt, "installed", lambda *_: True)
    threads = []

    class Adapter:
        def __init__(self, model, path, count, language, vocabulary):
            threads.append(threading.get_ident())

        def transcribe(self, samples):
            threads.append(threading.get_ident())
            assert samples.dtype == np.float32
            assert samples[0] == 2000 / 32768
            return "Hello world", [{"word": "Hello", "start": 0.1, "end": 0.5}], []

    return LocalEngine(adapter_factory=Adapter), threads


async def test_engine_interface_and_dedicated_worker(fake_engine):
    engine, threads = fake_engine
    try:
        assert engine.state == "idle"
        await engine.load("parakeet-v3")
        assert engine.state == "ready"
        assert engine.model_id == "parakeet-v3"
        transcript = await engine.transcribe(PCM, start=RATE)
        assert transcript.text == "Hello world"
        assert transcript.words == [{"word": "Hello", "start": 1.1, "end": 1.5}]
        assert (transcript.start, transcript.end) == (RATE, RATE * 2)
        assert engine.decode_ms > 0
        assert len(set(threads)) == 1
        assert threads[0] != threading.get_ident()
        await engine.unload()
        assert engine.state == "idle"
        with pytest.raises(ProviderError, match="not downloaded"):
            await engine.transcribe(PCM)
    finally:
        await engine.aclose()


async def test_loading_never_blocks_event_loop(fake_engine):
    engine, _ = fake_engine
    entered = threading.Event()
    release = threading.Event()

    def factory(*_):
        entered.set()
        assert release.wait(timeout=3)
        return SimpleNamespace(transcribe=lambda _: ("Hello", [], []))

    engine.adapter_factory = factory
    task = asyncio.create_task(engine.load("parakeet-v3"))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert engine.state == "loading"
        release.set()
        await task
        assert engine.state == "ready"
    finally:
        release.set()
        await engine.aclose()


async def test_decode_serialized_even_when_caller_cancels(fake_engine):
    engine, _ = fake_engine
    await engine.load("parakeet-v3")
    entered = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0

    def decode(_):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        entered.set()
        assert release.wait(timeout=3)
        active -= 1
        return "Hello", [], []

    engine._adapter.transcribe = decode
    first = asyncio.create_task(engine.transcribe(PCM))
    second = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(engine.transcribe(PCM))
        release.set()
        assert (await second).text == "Hello"
        assert maximum == 1
    finally:
        release.set()
        await engine.aclose()


async def test_silence_and_punctuation_are_dropped(fake_engine):
    engine, _ = fake_engine
    try:
        await engine.load("parakeet-v3")
        decode = Mock(return_value=("… !!!", [], []))
        engine._adapter.transcribe = decode
        assert (await engine.transcribe(b"\0\0" * RATE)).text == ""
        assert (await engine.transcribe(b"")).text == ""
        decode.assert_not_called()
        assert (await engine.transcribe(PCM)).text == ""
    finally:
        await engine.aclose()


async def test_errors_do_not_expose_native_or_dictation_text(fake_engine):
    engine, _ = fake_engine
    try:
        await engine.load("parakeet-v3")
        engine._adapter.transcribe = Mock(side_effect=RuntimeError("private transcript"))
        with pytest.raises(ProviderError) as error:
            await engine.transcribe(PCM)
        assert error.value.kind == "local_decode"
        assert "private" not in str(error.value)
        engine.adapter_factory = Mock(side_effect=RuntimeError("private model path"))
        with pytest.raises(ProviderError):
            await engine.load("parakeet-110m")
        assert engine.state == "error"
        assert engine.model_id == "parakeet-v3"  # Failed switch did not destroy the old model.
        assert "private" not in engine.message
    finally:
        await engine.aclose()


async def test_missing_receipt_prevents_loading(monkeypatch, tmp_path):
    factory = Mock()
    engine = LocalEngine(root=tmp_path, adapter_factory=factory)
    try:
        with pytest.raises(ProviderError) as error:
            await engine.load("parakeet-v3")
        assert error.value.kind == "missing_model"
        factory.assert_not_called()
    finally:
        await engine.aclose()


def test_repetition_guard_words_tokens_and_duration():
    assert repetition_guard("one two three four " * 5, 10)
    assert not repetition_guard("one two three four " * 4, 10)
    assert repetition_guard("ordinary text", 10, ["a", "b", "c", "d"] * 5)
    assert repetition_guard(" ".join(f"w{i}" for i in range(100)), 1)
    assert not repetition_guard("Yes yes yes, I really meant it.", 2)
    assert not repetition_guard("Turn left, then turn right.", 3)


def test_sherpa_word_boundaries():
    result = SimpleNamespace(tokens=["▁Hello", ",", "▁wor", "ld", "."],
                             timestamps=[0.1, 0.3, 0.5, 0.6, 0.8])
    assert local_stt._sherpa_words(result, 1.0) == [
        {"word": "Hello,", "start": 0.1, "end": 0.5},
        {"word": "world.", "start": 0.5, "end": 1.0},
    ]
    assert local_stt._sherpa_words(SimpleNamespace(tokens=["x"], timestamps=[]), 1) == []


def test_cuda_decode_failure_retries_on_cpu_without_downloads(tmp_path, monkeypatch):
    calls = []
    class Model:
        def __init__(self, path, **options):
            assert options["local_files_only"] is True
            self.device = options["device"]
            calls.append(options)

        def transcribe(self, *_args, **_kwargs):
            if self.device == "cuda":
                raise RuntimeError("Missing CUDA library")
            return [SimpleNamespace(text="Hello", no_speech_prob=0)], None

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(
        get_cuda_device_count=lambda: 1,
        get_supported_compute_types=lambda _: {"int8_float16"},
    ))
    model = local_stt.FasterWhisper({"auto_language": True}, tmp_path, 2)
    assert model.transcribe(np.ones(16000, dtype=np.float32))[0] == "Hello"
    assert [call["device"] for call in calls] == ["cuda", "cpu"]
    assert model.device == "cpu"


def test_hotwords_do_not_accept_native_control_syntax():
    assert local_stt.hotword_phrases("Acme :100, a/b\nAcme :100") == ["Acme 100", "a b"]


async def test_local_benchmark_never_constructs_http_client(tmp_path, monkeypatch, fake_engine):
    engine, _ = fake_engine
    monkeypatch.setattr(local_stt, "LocalEngine", lambda **_: engine)
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: pytest.fail("HTTP client constructed"))
    (tmp_path / "clip.wav").write_bytes(wav_bytes(PCM))
    (tmp_path / "reference.txt").write_text("Hello world")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"id": "fake", "audio": "clip.wav", "reference": "reference.txt"}
    ]))
    config = Config()
    config.cleanup.model = "must-not-upload-for-refinement"
    output = tmp_path / "numeric.json"
    report = await local_benchmark(config, manifest, 2, output, "parakeet-v3")
    assert report["summary"]["mean_raw_wer"] == 0
    assert report["summary"]["http_calls"] == report["summary"]["uploaded_audio_bytes"] == 0
    assert report["summary"]["realtime_factor"] > 0
    assert report["summary"]["peak_rss_mb"] > 0
    assert len(report["runs"]) == 2
    assert "Hello" not in output.read_text()
    assert engine._closed


@pytest.mark.skipif(os.environ.get("CAELUM_TEST_MODELS") != "1",
                    reason="Opt-in: requires installed models and three public/consented WAVs")
@pytest.mark.parametrize("model_id", [model["id"] for model in catalog()["models"]])
async def test_real_model_three_clips(model_id):
    # Explicit paths bypass the unit suite's isolated XDG directories. Tests do
    # not download anything, use the microphone, save text, or upload audio.
    root = os.environ.get("CAELUM_TEST_MODELS_DIR")
    manifest = os.environ.get("CAELUM_MODEL_FIXTURES")
    if not root or not manifest:
        pytest.fail("Set CAELUM_TEST_MODELS_DIR and CAELUM_MODEL_FIXTURES")
    manifest = Path(manifest)
    fixtures = json.loads(manifest.read_text())
    assert len(fixtures) >= 3
    engine = LocalEngine(root=root or models_dir(), language="en")
    try:
        await engine.load(model_id)
        for fixture in fixtures[:3]:
            pcm = read_wav(manifest.parent / fixture["audio"])
            result = await engine.transcribe(pcm)
            assert result.text
            if fixture.get("id") == "librispeech-0":
                assert "light" in result.text.casefold()
            if fixture.get("id") == "librispeech-0":
                assert "light" in result.text.casefold()
            assert not repetition_guard(result.text, len(pcm) / (RATE * 2))
            if fixture.get("id") == "librispeech-0":
                assert "light" in result.text.casefold()
    finally:
        await engine.aclose()
