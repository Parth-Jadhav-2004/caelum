"""Offline engines. Native loading, decoding and destruction share one worker."""

import asyncio
import ctypes
import os
import re
import shutil
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .audio import RATE
from .cuda_runtime import SherpaCuda
from .models import get_model, installed, models_dir
from .providers import ProviderError, Transcript
from .sherpa_stt import ADAPTERS, hotword_phrases


def auto_threads():
    try:
        cores = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cores = os.cpu_count() or 1
    return min(4, max(1, cores - 1))


def repetition_guard(text, duration, tokens=()):
    """Catch decoder loops without rejecting ordinary short dictations.

    Expected conversational speech is three words/second. Permit four times
    that, and a minimum one-second duration for very short microphone clips.
    """
    words = re.findall(r"\w+", text.casefold())
    if len(words) > 4 * 3 * max(1, duration):
        return True
    for sequence in (words, list(tokens)):
        grams = zip(*(sequence[i:] for i in range(4)), strict=False)
        if any(count > 4 for count in Counter(grams).values()):
            return True
    return False


def whisper_setup_error():
    windows = os.name == "nt"
    return ProviderError(
        "Whisper needs CUDA-capable CTranslate2 with int8_float16 and CUDA 12 cuBLAS "
        f"on {'Windows (DLLs on PATH)' if windows else 'Linux (libraries on the loader path)'}. "
        "See docs/nvidia.md or choose Auto or CPU.", "local_setup")


def whisper_blas():
    # The pinned CTranslate2 wheel loads cuBLAS lazily. Probe before loading weights.
    if os.name == "nt":
        dll = shutil.which("cublas64_12.dll")
        if not dll:
            raise OSError("Missing cuBLAS")
        ctypes.CDLL(dll)
    else:
        ctypes.CDLL("libcublas.so.12")


class FasterWhisper:
    def __init__(self, model, path, threads, language="", vocabulary="", prefer_cuda=True, device="auto"):
        try:
            from faster_whisper import WhisperModel
        except (ImportError, OSError):
            if device == "gpu":
                raise whisper_setup_error() from None
            raise

        self.path, self.threads = str(path), threads
        # A local directory and local_files_only prevent implicit HF downloads.
        self.device = "cpu"
        self.allow_cpu_fallback = device != "gpu"
        if prefer_cuda and device != "cpu":
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count() and (
                    "int8_float16" in ctranslate2.get_supported_compute_types("cuda")
                ):
                    whisper_blas()
                    self.model = WhisperModel(str(path), device="cuda", compute_type="int8_float16",
                                              cpu_threads=threads, local_files_only=True)
                    self.device = "cuda"
            except (ImportError, RuntimeError, OSError):
                if device == "gpu":
                    raise whisper_setup_error() from None
        if self.device == "cpu" and device == "gpu":
            raise whisper_setup_error()
        if self.device == "cpu":
            self.model = WhisperModel(str(path), device="cpu", compute_type="int8",
                                      cpu_threads=threads, num_workers=1, local_files_only=True)
        self.language = language or (None if model["auto_language"] else "en")
        self.vocabulary = vocabulary or None

    def transcribe(self, samples, retry=False):
        try:
            return self._decode(samples, retry)
        except (RuntimeError, OSError):
            if self.device != "cuda":
                raise
            if not self.allow_cpu_fallback:
                raise ProviderError("Whisper CUDA decode failed. Check cuBLAS and free GPU memory, "
                                    "or choose Auto or CPU.", "local_decode") from None
            # CTranslate2 can construct a CUDA model even when cuBLAS/cuDNN
            # are missing; capability enumeration alone is insufficient.
            from faster_whisper import WhisperModel

            self.model = None
            self.model = WhisperModel(self.path, device="cpu", compute_type="int8",
                                      cpu_threads=self.threads, num_workers=1, local_files_only=True)
            self.device = "cpu"
            return self._decode(samples, retry)

    def _decode(self, samples, retry=False):
        segments, info = self.model.transcribe(
            samples, language=self.language, initial_prompt=self.vocabulary,
            # The runtime retries high-compression / low-confidence outputs
            # using temperature fallback. Never use sherpa for Whisper.
            temperature=(0.4, 0.6, 0.8, 1.0) if retry else (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            condition_on_previous_text=not retry, no_repeat_ngram_size=4 if retry else 0,
        )
        self.detected_language = getattr(info, "language", "")
        segments = list(segments)  # Actual decode happens while consuming the iterator.
        if segments and all(segment.no_speech_prob > 0.85 for segment in segments):
            return "", [], []
        return " ".join(segment.text.strip() for segment in segments).strip(), [], []


def runtime_adapter(model, path, threads, language, vocabulary, prefer_cuda=True, device="auto",
                    profile_dir=None):
    args = model, path, threads, language, vocabulary
    if model["runtime"] == "faster-whisper":
        return FasterWhisper(*args, prefer_cuda, device)
    if device == "gpu" or prefer_cuda and device == "auto":
        try:
            return SherpaCuda(*args, profile_dir=profile_dir)
        except ProviderError:
            if device == "gpu":
                raise
    return ADAPTERS[model["runtime"]](*args)


class LocalEngine:
    def __init__(self, *, root=None, threads=0, language="", vocabulary="",
                 silence_dbfs=-60, adapter_factory=None, prefer_cuda=True, device="auto",
                 speech_detector=None, cuda_profile_dir=None):
        if type(threads) is not int or not 0 <= threads <= 256:
            raise ValueError("Local thread count must be between 0 and 256")
        self.root = Path(root) if root is not None else models_dir()
        self.threads = threads or auto_threads()
        self.language = language
        self.vocabulary = vocabulary
        self.silence_dbfs = silence_dbfs
        self.adapter_factory = adapter_factory
        self.prefer_cuda = prefer_cuda
        self.device = device
        self.cuda_profile_dir = cuda_profile_dir
        self._speech_detector = speech_detector
        self._provided_detector = speech_detector is not None
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="caelum-local")
        self.lock = asyncio.Lock()
        self.state = "idle"
        self.model_id = None
        self.message = ""
        self.decode_ms = 0.0
        self.load_seconds = 0.0
        self._adapter = None
        self._closed = False

    async def _run(self, function, *args):
        if self._closed:
            raise ProviderError("Local engine is closed", "local_setup")
        # Shielding prevents cancellation of the asyncio wrapper from cancelling
        # a queued model swap/unload. The single executor still serializes native
        # work after a caller cancels an in-flight decode.
        result = asyncio.get_running_loop().run_in_executor(self.worker, function, *args)
        try:
            return await asyncio.shield(result)
        except asyncio.CancelledError:
            # Drain exceptions without leaking native exception text into logs.
            result.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            raise

    async def load(self, model_id):
        get_model(model_id)
        async with self.lock:
            self.state, self.message = "loading", "Getting ready…"
            return await self._run(self._load, model_id)

    def _load(self, model_id):
        began = time.monotonic()
        try:
            if not installed(model_id, self.root, full=True):
                if installed(model_id, self.root):
                    raise ProviderError(
                        "Speech model files are damaged. Choose Check files in the model menu, "
                        "then Download again.", "local_setup"
                    )
                raise ProviderError("Speech model not downloaded", "missing_model")
            model = get_model(model_id)
            if self.language and "*" not in model["languages"] and self.language not in model["languages"]:
                raise ProviderError("This model doesn't support the chosen language. Choose another model or Online.",
                                    "local_setup")
            language = self.language
            if self.adapter_factory is None:
                from .hardware import detect, local_support

                hardware = detect(directory=self.root)
                if not language and not model["auto_language"]:
                    language = hardware.language if hardware.language in model["languages"] else "en"
                if reason := local_support(hardware):
                    raise ProviderError(reason, "local_setup")
                if hardware.mem_total_mb < model["min_mem_total_mb"]:
                    raise ProviderError("This speech model needs 8 GB memory.", "local_setup")
                if 0 < hardware.mem_available_mb < model["min_ram_available_mb"]:
                    raise ProviderError("Not enough memory for this speech model. Close apps and try again.",
                                        "local_setup")
            args = (model, self.root / model_id, self.threads, language, self.vocabulary)
            if self._speech_detector is None:
                from .vad import Silero

                self._speech_detector = Silero()
            new = (self.adapter_factory(*args) if self.adapter_factory
                   else runtime_adapter(*args, prefer_cuda=self.prefer_cuda, device=self.device,
                                        profile_dir=self.cuda_profile_dir))
            if isinstance(self._adapter, SherpaCuda):
                self._adapter.close()
            self._adapter = new
            self.model_id = model_id
            self.load_seconds = time.monotonic() - began
            self.state, self.message = "ready", ""
        except ProviderError as error:
            self.state = "ready" if self._adapter is not None else "error"
            self.message = str(error)
            raise
        except ImportError:
            self.state, self.message = ("ready" if self._adapter else "error"), "Needs an extra component."
            raise ProviderError(self.message, "local_setup") from None
        except Exception:
            self.state, self.message = ("ready" if self._adapter else "error"), "Speech model needs attention. Check files in Settings."
            raise ProviderError(self.message, "local_setup") from None

    async def transcribe(self, pcm, start=0, end=None):
        if len(pcm) % 2:
            raise ValueError("Audio must be 16-bit PCM")
        async with self.lock:
            return await self._run(self._transcribe, pcm, start, end)

    def _transcribe(self, pcm, start, end):
        if self._adapter is None:
            raise ProviderError("Speech model not downloaded", "missing_model")
        end = end if end is not None else start + len(pcm) // 2
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        rms = float(np.sqrt(np.mean(samples * samples))) if len(samples) else 0
        if 20 * np.log10(max(rms, 1e-9)) <= self.silence_dbfs:
            self.decode_ms = 0.0
            return Transcript("", [], start, end)
        began = time.monotonic()
        try:
            from .vad import pause_chunks

            regions = self._speech_detector(samples)
            runtime = get_model(self.model_id)["runtime"]
            limit = 35 if runtime == "sherpa-cohere" else 30 if runtime == "faster-whisper" else 60
            texts, all_words, languages = [], [], set()
            for begin, stop in pause_chunks(regions, limit):
                chunk = samples[begin:stop]
                text, words, tokens = self._adapter.transcribe(chunk)
                text = text.strip()
                if repetition_guard(text, len(chunk) / RATE, tokens) and isinstance(self._adapter, FasterWhisper):
                    text, words, tokens = self._adapter.transcribe(chunk, retry=True)
                if repetition_guard(text, len(chunk) / RATE, tokens):
                    raise ProviderError("Couldn't make sense of that. Try again.", "local_decode")
                detected = getattr(self._adapter, "detected_language", "")
                if detected:
                    languages.add(detected)
                text = filter_output(text, self.vocabulary)
                if text:
                    texts.append(text)
                    all_words.extend({**word, "start": word["start"] + (start + begin) / RATE,
                                      "end": word["end"] + (start + begin) / RATE}
                                     for word in words)
            language = self.language or (next(iter(languages)) if len(languages) == 1 else
                                         "mixed" if languages else "auto")
            return Transcript(" ".join(texts), all_words, start, end, language)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("Couldn't make sense of that. Try again.", "local_decode") from None
        finally:
            self.decode_ms = (time.monotonic() - began) * 1000

    @property
    def active_device(self):
        return getattr(self._adapter, "device", "cpu") if self._adapter is not None else None

    def _unload(self):
        if isinstance(self._adapter, SherpaCuda):
            self._adapter.close()
        self._adapter = None
        if not self._provided_detector:
            self._speech_detector = None
        self.model_id = None
        self.state, self.message = "idle", ""

    async def unload(self):
        async with self.lock:
            await self._run(self._unload)

    async def aclose(self):
        if not self._closed:
            await self.unload()
            self._closed = True
            self.worker.shutdown(wait=False, cancel_futures=True)



def filter_output(text, vocabulary):
    """Reject recognizer boilerplate and verbatim prompt dumps conservatively."""
    if not any(unicodedata.category(char)[0] in ("L", "N") for char in text):
        return ""
    def canonical(value):
        return " ".join(re.findall(r"\w+", value.casefold()))
    normalized = canonical(text)
    phrases = [canonical(value) for value in hotword_phrases(vocabulary)]
    # A single name can be a legitimate dictation. A whole vocabulary list is not.
    if len(phrases) >= 2 and normalized == " ".join(phrases):
        return ""
    if normalized in {"subtitles by the amara org community", "subtitles by amara org"} or (
        text.strip().casefold() in {"[music]", "(music)", "[applause]", "(applause)"}
    ):
        return ""
    # Whisper sometimes prepends its prompt before the actual spoken sentence.
    prompt = " ".join(phrases)
    if len(phrases) >= 2 and normalized.startswith(prompt + " "):
        pattern = r"[\W_]*".join(re.escape(word) for word in prompt.split())
        text = re.sub(r"^\s*" + pattern + r"[\W_]*", "", text, count=1, flags=re.I)
    return text.strip()
