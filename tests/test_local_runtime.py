"""Privacy and lifetime regressions for local inference. No model downloads."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest
from caelum.audio import RATE
from caelum.config import Config, load, save, validate
from caelum.hardware import Hardware, local_support
from caelum.local_stt import LocalEngine, filter_output
from caelum.providers import ProviderError, Providers, Transcript, offline_cleanup
from caelum.service import reload_settings
from caelum.vad import Silero, pause_chunks


@pytest.mark.parametrize("model_id,limit", [("cohere-transcribe", 35), ("whisper-turbo", 30),
                                          ("parakeet-v3", 60)])
async def test_long_recordings_are_bounded_at_pauses_and_keep_offsets(monkeypatch, model_id, limit):
    monkeypatch.setattr("caelum.local_stt.installed", lambda *_: True)
    lengths = []
    def decode(samples):
        lengths.append(len(samples))
        return "Spoken words", [{"word": "Spoken", "start": 0, "end": 0.2}], []
    first_end = int((limit - 2) * RATE)
    second_begin = int((limit - 1) * RATE)
    total = (limit * 2 + 5) * RATE
    def detector(_):
        return [(0, first_end), (second_begin, total)]
    engine = LocalEngine(adapter_factory=lambda *_: SimpleNamespace(transcribe=decode),
                         speech_detector=detector)
    try:
        await engine.load(model_id)
        result = await engine.transcribe(np.full(total, 2000, dtype="<i2").tobytes(), RATE)
        assert lengths[0] == first_end
        assert max(lengths) <= limit * RATE
        assert sum(lengths) == first_end + total - second_begin
        assert result.words[1]["start"] == 1 + second_begin / RATE
        assert (result.start, result.end) == (RATE, RATE + total)
        assert result.text.count("Spoken words") == len(lengths)
    finally:
        await engine.aclose()


def test_continuous_speech_is_bounded_without_sample_loss():
    chunks = list(pause_chunks([(100, 91 * RATE)], 30))
    assert chunks[0][0] == 100
    assert chunks[-1][1] == 91 * RATE
    assert all(end - begin <= 30 * RATE for begin, end in chunks)
    assert all(left[1] == right[0] for left, right in zip(chunks, chunks[1:], strict=False))


async def test_vad_skips_nonspeech_before_decoder_even_above_energy_threshold(monkeypatch):
    monkeypatch.setattr("caelum.local_stt.installed", lambda *_: True)
    decoder = Mock()
    engine = LocalEngine(adapter_factory=lambda *_: SimpleNamespace(transcribe=decoder),
                         speech_detector=lambda _: [])
    try:
        await engine.load("parakeet-v3")
        assert not (await engine.transcribe(np.full(RATE, 2000, dtype="<i2").tobytes())).text
        decoder.assert_not_called()
    finally:
        await engine.aclose()


def test_bundled_silero_rejects_silence_and_resets_between_recordings():
    pytest.importorskip("sherpa_onnx")
    detector = Silero()
    assert detector(np.zeros(RATE, dtype=np.float32)) == []
    assert detector(np.zeros(51, dtype=np.float32)) == []


@pytest.mark.parametrize("kind", ["local_decode", "timeout", "local_load_timeout"])
async def test_unclear_speech_or_pending_load_never_uploads(kind):
    config = Config()
    config.stt.engine, config.stt.local_model, config.stt.fallback = "local", "parakeet-v3", "online"
    provider = Providers(config, client=AsyncMock())
    provider._local_stt = AsyncMock(side_effect=ProviderError("Try again", kind))
    provider._online_stt = AsyncMock()
    try:
        with pytest.raises(ProviderError):
            await provider.stt(b"audio")
        provider._online_stt.assert_not_called()
        provider.client.post.assert_not_called()
    finally:
        await provider.aclose()


def test_offline_cleanup_and_dictionary_are_bounded_and_non_cascading():
    assert offline_cleanup("Um, hello uh world new line sea lum.", {"sea lum": "Caelum"}) == "hello world\nCaelum."
    assert offline_cleanup("human UHF umbrella", {}) == "human UHF umbrella"
    assert offline_cleanup("Acme Acme Labs", {"Acme Labs": "Studio", "Acme": "Acme Labs"}) == "Acme Labs Studio"
    assert offline_cleanup("a+b", {"a+b": "$1"}) == "$1"
    assert offline_cleanup("İstanbul is lovely.", {"istanbul": "Istanbul"}) == "Istanbul is lovely."
    config = Config()
    config.cleanup.replacements = {"sea lum": "Caelum"}
    validate(config)
    config.cleanup.replacements = {"": "bad"}
    with pytest.raises(ValueError, match="Dictionary"):
        validate(config)


def test_prompt_echo_and_subtitle_filters_keep_ordinary_vocabulary():
    assert filter_output("Caelum, Omarchy, Hyprland.", "Caelum, Omarchy, Hyprland") == ""
    assert filter_output("Caelum", "Caelum, Omarchy, Hyprland") == "Caelum"
    assert filter_output("Caelum, Omarchy, Hyprland. Send this message.", "Caelum, Omarchy, Hyprland") == "Send this message."
    assert filter_output("Subtitles by the Amara.org community", "") == ""
    assert filter_output("Turn left, then turn right.", "") == "Turn left, then turn right."


async def test_failed_switch_keeps_runtime_config_and_saved_selection(tmp_path):
    previous = Config()
    previous.stt.engine, previous.stt.local_model = "local", "parakeet-v3"
    path = tmp_path / "config.toml"
    save(previous, path)
    provider = Providers(previous, client=AsyncMock())
    active = SimpleNamespace(aclose=AsyncMock(), transcribe=AsyncMock(return_value=Transcript("Still works", [])))
    provider.local_engine, provider.local_state = active, "ready"
    provider.local_signature = provider.signature(previous)
    provider.prepare_local = AsyncMock(side_effect=ProviderError("Not enough memory", "local_setup"))
    core = SimpleNamespace(config=previous, control_lock=asyncio.Lock(), capture=None, pcm=None, work=None)
    bindings = SimpleNamespace(hotkey=previous.app.hotkey, remove=AsyncMock(), install=AsyncMock())
    updated = deepcopy(previous)
    updated.stt.local_model = "cohere-transcribe"
    try:
        with pytest.raises(ProviderError, match="memory"):
            await reload_settings(core, bindings, provider, path, updated, True)
        assert provider.local_engine is active
        assert provider.config is core.config is previous
        assert load(path).stt.local_model == "parakeet-v3"
        assert (await active.transcribe(b"audio")).text == "Still works"
        active.aclose.assert_not_called()
    finally:
        await provider.aclose()


async def test_successful_switch_commits_only_after_candidate_load(tmp_path):
    previous = Config()
    path = tmp_path / "config.toml"
    save(previous, path)
    provider = Providers(previous, client=AsyncMock())
    provider.local_signature = provider.signature(previous)
    candidate = AsyncMock()
    entered, finish = asyncio.Event(), asyncio.Event()
    async def stage(_):
        entered.set()
        await finish.wait()
        return candidate
    provider.prepare_local = stage
    core = SimpleNamespace(config=previous, control_lock=asyncio.Lock(), capture=None, pcm=None, work=None)
    bindings = SimpleNamespace(hotkey=previous.app.hotkey, remove=AsyncMock(), install=AsyncMock())
    updated = deepcopy(previous)
    updated.stt.engine, updated.stt.local_model = "local", "parakeet-v3"
    task = asyncio.create_task(reload_settings(core, bindings, provider, path, updated, True))
    try:
        await entered.wait()
        assert load(path).stt.engine == "online"
        assert provider.local_engine is None
        finish.set()
        await task
        assert load(path).stt.local_model == "parakeet-v3"
        assert provider.local_engine is candidate
        assert provider.config is core.config is updated
    finally:
        finish.set()
        await task
        await provider.aclose()


async def test_idle_unload_and_next_dictation_reload(monkeypatch):
    config = Config()
    config.stt.engine, config.stt.local_model = "local", "parakeet-v3"
    config.stt.local_idle_seconds = 0.01
    provider = Providers(config, client=AsyncMock())
    engine = SimpleNamespace(unload=AsyncMock(), aclose=AsyncMock())
    provider.local_engine, provider.local_state = engine, "ready"
    provider.local_signature = provider.signature(config)
    try:
        provider.arm_idle()
        await asyncio.sleep(0.03)
        engine.unload.assert_awaited_once()
        assert provider.local_state == "unloaded"
        new = SimpleNamespace(transcribe=AsyncMock(return_value=Transcript("Hello", [], language="en")),
                              decode_ms=1, aclose=AsyncMock())
        provider.prepare_local = AsyncMock(return_value=new)
        assert (await provider.stt(b"audio")).text == "Hello"
        assert provider.local_engine is new
        assert provider.metrics["language"] == "en"
    finally:
        await provider.aclose()


def test_old_processors_are_rejected_before_native_imports():
    assert local_support(Hardware(arch="x86_64", avx2=False))
    assert local_support(Hardware(arch="aarch64")) is None
    assert local_support(Hardware(arch="x86_64", avx2=True)) is None


def test_pauses_do_not_feed_distant_silence_to_decoder():
    assert list(pause_chunks([(0, RATE), (500 * RATE, 501 * RATE)], 35)) == [
        (0, RATE), (500 * RATE, 501 * RATE),
    ]


def test_real_spoken_closing_phrase_is_not_blanket_filtered():
    assert filter_output("Thank you for watching.", "") == "Thank you for watching."


def test_utterance_pauses_are_used_before_sequence_decoder_ceiling():
    # Packing two repeated 17-second utterances into a 35-second Cohere window
    # can produce only one sentence. Prefer the earlier complete-utterance pause.
    regions = [(0, 17 * RATE), (18 * RATE, 35 * RATE)]
    assert list(pause_chunks(regions, 35)) == regions
