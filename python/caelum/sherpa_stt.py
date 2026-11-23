"""Shared offline recognizers for packaged CPU and optional CUDA runtimes."""

import os
import re
from pathlib import Path

from .audio import RATE


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
    def __init__(self, model, path, threads, language="", vocabulary="", device="cpu"):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        options = dict(
            encoder=files["encoder"], decoder=files["decoder"], joiner=files["joiner"],
            tokens=files["tokens"], model_type="nemo_transducer", num_threads=threads,
            sample_rate=RATE, provider=device,
        )
        pieces = [line.rsplit(" ", 1)[0] for line in Path(files["tokens"]).read_text(encoding="utf-8").splitlines()]
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
            for line in Path(files["tokens"]).read_text(encoding="utf-8").splitlines()
            if line.rsplit(" ", 1)[0]
        )
        descriptors = []
        if os.name == "nt":
            import tempfile

            with tempfile.TemporaryDirectory(prefix="caelum-vocabulary-") as tmp:
                vocabulary_path, words = Path(tmp) / "vocab", Path(tmp) / "words"
                vocabulary_path.write_text(vocab, encoding="utf-8")
                words.write_text("\n".join(phrases), encoding="utf-8")
                self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                    **options, hotwords_file=str(words), bpe_vocab=str(vocabulary_path),
                    modeling_unit="bpe", decoding_method="modified_beam_search",
                )
            return
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
        self.detected_language = getattr(result, "lang", "")
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

    def __init__(self, model, path, threads, language="", vocabulary="", device="cpu"):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        self.language = language if language in model["languages"] else "en"
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_cohere_transcribe(
            encoder=files["encoder"], decoder=files["decoder"], tokens=files["tokens"],
            num_threads=threads, language=self.language,
            use_punct=True, use_itn=True, provider=device,
        )

    def transcribe(self, samples):
        stream = self.recognizer.create_stream()
        stream.accept_waveform(RATE, samples)
        self.recognizer.decode_stream(stream)
        self.detected_language = getattr(stream.result, "lang", "") or getattr(self, "language", "en")
        return stream.result.text, [], []


class SherpaCanary(SherpaCohere):
    def __init__(self, model, path, threads, language="", vocabulary="", device="cpu"):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        language = language if language in model["languages"] else "en"
        self.language = language
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_canary(
            encoder=files["encoder"], decoder=files["decoder"], tokens=files["tokens"],
            src_lang=language, tgt_lang=language, num_threads=threads, provider=device,
        )


class SherpaMoonshine(SherpaCohere):
    def __init__(self, model, path, threads, language="", vocabulary="", device="cpu"):
        import sherpa_onnx

        files = {item["role"]: str(path / item["path"]) for item in model["files"]}
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_moonshine(
            preprocessor=files["preprocessor"], encoder=files["encoder"],
            uncached_decoder=files["uncached_decoder"], cached_decoder=files["cached_decoder"],
            tokens=files["tokens"], num_threads=threads, provider=device,
        )


ADAPTERS = {
    "sherpa-transducer": SherpaTransducer,
    "sherpa-cohere": SherpaCohere,
    "sherpa-canary": SherpaCanary,
    "sherpa-moonshine": SherpaMoonshine,
}
