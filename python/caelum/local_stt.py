"""Offline engines. Native loading, decoding and destruction share one worker."""

import asyncio
import os
import re
import shutil
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .audio import RATE, wav_bytes
from .models import get_model, installed, models_dir
from .providers import ProviderError, Transcript


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


def _sherpa_words(result, duration):
    tokens = list(result.tokens)
    timestamps = list(result.timestamps)
    if not tokens or len(tokens) != len(timestamps):
        return []
    # SentencePiece word boundaries are used by the Parakeet exports.
    words = []
    for token, timestamp in zip(tokens, timestamps, strict=True):
        if token.startswith(("▁", " ")) or not words:
            words.append({"word": token.lstrip("▁ "), "start": min(duration, max(0, timestamp))})
        else:
            words[-1]["word"] += token
    words = [word for word in words if word["word"]]
    for index, word in enumerate(words):
        word["end"] = words[index + 1]["start"] if index + 1 < len(words) else duration
    return words


class SherpaTransducer:
    def __init__(self, model, path, threads, language="", vocabulary=""):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        options = dict(
            encoder=files["encoder"], decoder=files["decoder"], joiner=files["joiner"],
            tokens=files["tokens"], model_type="nemo_transducer", num_threads=threads,
            sample_rate=RATE, provider="cpu",
        )
        pieces = [line.rsplit(" ", 1)[0] for line in Path(files["tokens"]).read_text().splitlines()]
        characters = {piece for piece in pieces if len(piece) == 1}
        phrases = [phrase for phrase in hotword_phrases(vocabulary)
                   if all(char.isspace() or char in characters for char in phrase)]
        if not phrases:
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(**options)
            return
        # The catalog contains tokens, not the original SentencePiece scores.
        # A uniform-cost vocabulary finds a valid minimum-piece segmentation
        # for biasing only; it does not change the model or its token IDs.
        vocab = "\n".join(
            line.rsplit(" ", 1)[0] + "\t-1"
            for line in Path(files["tokens"]).read_text().splitlines()
            if line.rsplit(" ", 1)[0]
        )
        descriptors = []
        try:
            for content in (vocab, "\n".join(phrases)):
                descriptor = os.memfd_create("caelum-hotwords", flags=0)
                descriptors.append(descriptor)
                with os.fdopen(os.dup(descriptor), "wb") as stream:
                    stream.write(content.encode("utf-8"))
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                **options, hotwords_file=f"/proc/self/fd/{descriptors[1]}",
                bpe_vocab=f"/proc/self/fd/{descriptors[0]}", modeling_unit="bpe",
                decoding_method="modified_beam_search",
            )
        finally:
            for descriptor in descriptors:
                os.close(descriptor)

    def transcribe(self, samples):
        stream = self.recognizer.create_stream()
        stream.accept_waveform(RATE, samples)
        self.recognizer.decode_stream(stream)
        result = stream.result
        return result.text, _sherpa_words(result, len(samples) / RATE), list(result.tokens)


def hotword_phrases(vocabulary):
    # Never allow sherpa's score/threshold syntax or slashes to be injected.
    phrases = []
    for part in re.split(r"[,\n]", vocabulary[:4000]):
        phrase = " ".join(re.sub(r"[^\w\s]", " ", part, flags=re.UNICODE).split())[:128]
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases[:128]


class SherpaCohere:

    def __init__(self, model, path, threads, language="", vocabulary=""):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_cohere_transcribe(
            encoder=files["encoder"], decoder=files["decoder"], tokens=files["tokens"],
            num_threads=threads, language=language if language in model["languages"] else "en",
            use_punct=True, use_itn=True, provider="cpu",
        )

    def transcribe(self, samples):
        stream = self.recognizer.create_stream()
        stream.accept_waveform(RATE, samples)
        self.recognizer.decode_stream(stream)
        return stream.result.text, [], []


class SherpaCanary(SherpaCohere):
    def __init__(self, model, path, threads, language="", vocabulary=""):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        language = language if language in model["languages"] else "en"
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_canary(
            encoder=files["encoder"], decoder=files["decoder"], tokens=files["tokens"],
            src_lang=language, tgt_lang=language, num_threads=threads, provider="cpu",
        )


class SherpaMoonshine(SherpaCohere):
    def __init__(self, model, path, threads, language="", vocabulary=""):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_moonshine(
            preprocessor=files["preprocessor"], encoder=files["encoder"],
            uncached_decoder=files["uncached_decoder"], cached_decoder=files["cached_decoder"],
            tokens=files["tokens"], num_threads=threads, provider="cpu",
        )


class FasterWhisper:
    def __init__(self, model, path, threads, language="", vocabulary="", prefer_cuda=True):
        from faster_whisper import WhisperModel

        self.path, self.threads = str(path), threads
        # A local directory and local_files_only prevent implicit HF downloads.
        self.device = "cpu"
        if prefer_cuda:
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count() and (
                    "int8_float16" in ctranslate2.get_supported_compute_types("cuda")
                ):
                    self.model = WhisperModel(str(path), device="cuda", compute_type="int8_float16",
                                              cpu_threads=threads, local_files_only=True)
                    self.device = "cuda"
            except (RuntimeError, OSError):
                pass
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
            # CTranslate2 can construct a CUDA model even when cuBLAS/cuDNN
            # are missing; capability enumeration alone is insufficient.
            from faster_whisper import WhisperModel

            self.model = None
            self.model = WhisperModel(self.path, device="cpu", compute_type="int8",
                                      cpu_threads=self.threads, num_workers=1, local_files_only=True)
            self.device = "cpu"
            return self._decode(samples, retry)

    def _decode(self, samples, retry=False):
        segments, _ = self.model.transcribe(
            samples, language=self.language, initial_prompt=self.vocabulary,
            # The runtime retries high-compression / low-confidence outputs
            # using temperature fallback. Never use sherpa for Whisper.
            temperature=(0.4, 0.6, 0.8, 1.0) if retry else (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            condition_on_previous_text=not retry, no_repeat_ngram_size=4 if retry else 0,
        )
        segments = list(segments)  # Actual decode happens while consuming the iterator.
        if segments and all(segment.no_speech_prob > 0.85 for segment in segments):
            return "", [], []
        return " ".join(segment.text.strip() for segment in segments).strip(), [], []


def runtime_adapter(model, path, threads, language, vocabulary, prefer_cuda=True):
    adapters = {
        "sherpa-transducer": SherpaTransducer,
        "sherpa-cohere": SherpaCohere,
        "sherpa-canary": SherpaCanary,
        "sherpa-moonshine": SherpaMoonshine,
        "faster-whisper": FasterWhisper,
    }
    adapter = adapters[model["runtime"]]
    if adapter is FasterWhisper:
        return adapter(model, path, threads, language, vocabulary, prefer_cuda)
    return adapter(model, path, threads, language, vocabulary)


class LocalEngine:
    def __init__(self, *, root=None, threads=0, language="", vocabulary="",
                 silence_dbfs=-60, adapter_factory=None, prefer_cuda=True):
        if type(threads) is not int or not 0 <= threads <= 256:
            raise ValueError("Local thread count must be between 0 and 256")
        self.root = Path(root) if root is not None else models_dir()
        self.threads = threads or auto_threads()
        self.language = language
        self.vocabulary = vocabulary
        self.silence_dbfs = silence_dbfs
        self.adapter_factory = adapter_factory
        self.prefer_cuda = prefer_cuda
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
            if not installed(model_id, self.root):
                raise ProviderError("Speech model not downloaded", "missing_model")
            model = get_model(model_id)
            if self.adapter_factory is None:
                from .hardware import detect

                hardware = detect(directory=self.root)
                if hardware.mem_total_mb < model["min_mem_total_mb"]:
                    raise ProviderError("This speech model needs 8 GB memory.", "local_setup")
                if 0 < hardware.mem_available_mb < model["min_ram_available_mb"]:
                    raise ProviderError("Not enough memory for this speech model. Close apps and try again.",
                                        "local_setup")
            args = (model, self.root / model_id, self.threads, self.language, self.vocabulary)
            new = (self.adapter_factory(*args) if self.adapter_factory
                   else runtime_adapter(*args, prefer_cuda=self.prefer_cuda))
            self._adapter = new
            self.model_id = model_id
            self.load_seconds = time.monotonic() - began
            self.state, self.message = "ready", ""
        except ProviderError as error:
            self.state = "error"
            self.message = str(error)
            raise
        except ImportError:
            self.state, self.message = "error", "Needs an extra component."
            raise ProviderError(self.message, "local_setup") from None
        except Exception:
            self.state, self.message = "error", "Speech model needs attention. Check files in Settings."
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
            text, words, tokens = self._adapter.transcribe(samples)
            text = text.strip()
            if repetition_guard(text, len(samples) / RATE, tokens) and isinstance(self._adapter, FasterWhisper):
                text, words, tokens = self._adapter.transcribe(samples, retry=True)
            if repetition_guard(text, len(samples) / RATE, tokens):
                raise ProviderError("Couldn't make sense of that. Try again.", "local_decode")
            if not any(unicodedata.category(char)[0] in ("L", "N") for char in text):
                text, words = "", []
            words = [
                {**word, "start": word["start"] + start / RATE,
                 "end": word["end"] + start / RATE}
                for word in words
            ]
            return Transcript(text, words, start, end)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("Couldn't make sense of that. Try again.", "local_decode") from None
        finally:
            self.decode_ms = (time.monotonic() - began) * 1000

    def _unload(self):
        self._adapter = None
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


def check_local(config):
    binary = shutil.which(config.local_binary)
    if not binary:
        raise ProviderError("Install whisper.cpp and set its whisper-cli executable in Settings", "local_setup")
    if not config.local_model_path or not Path(config.local_model_path).is_file():
        raise ProviderError("Choose an existing whisper.cpp GGML model file in Settings", "local_setup")
    return binary


async def transcribe(config, pcm):
    binary = check_local(config)
    fd = os.memfd_create("caelum-audio", flags=0)
    process = None
    try:
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(wav_bytes(pcm))
        os.lseek(fd, 0, os.SEEK_SET)
        args = [binary, "-m", config.local_model_path, "-f", f"/proc/self/fd/{fd}",
                "-nt", "-np", "-l", config.language or "auto"]
        if config.vocabulary:
            args.extend(["--prompt", config.vocabulary])
        process = await asyncio.create_subprocess_exec(
            *args, pass_fds=(fd,), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), config.local_timeout_seconds)
        except TimeoutError:
            raise ProviderError("Local transcription timed out; choose a smaller model or increase its timeout", "timeout") from None
        if process.returncode:
            raise ProviderError("Local transcription failed; check the executable and model file", "local_setup")
        return stdout.decode("utf-8").strip()
    except (OSError, UnicodeError):
        raise ProviderError("Local transcription unavailable; check whisper.cpp installation", "local_setup") from None
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        os.close(fd)
