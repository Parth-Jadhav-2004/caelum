# Third-party notices

## Inter Variable — SIL Open Font License 1.1 (OFL-1.1)

Inter is designed by Rasmus Andersson and the Inter Project Authors
(https://github.com/rsms/inter). The font is bundled through
`@fontsource-variable/inter`. Copyright 2016 The Inter Project Authors.

The complete SIL Open Font License 1.1 is distributed in
`public/licenses/Inter-OFL-1.1.txt`, copied to `licenses/Inter-OFL-1.1.txt`
in the built frontend, and included with native application resources.

The website uses [`inter-latin-wght-normal.woff2`](website/fonts/inter-latin-wght-normal.woff2)
from `@fontsource-variable/inter` 5.3.0 for headings and body text. The OFL
permits embedding and redistribution with the copyright notice and license;
both are published alongside the font in [`website/fonts/OFL.txt`](website/fonts/OFL.txt).

## Optional local speech runtimes and models

Native packages include sherpa-onnx by default. Python extras and the optional
Whisper component use these runtimes:

- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx): Apache-2.0.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime): MIT.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): MIT.
- [CTranslate2](https://github.com/OpenNMT/CTranslate2): MIT.

Speech model weights are not bundled. The catalog records the source, revision,
SHA-256, licence and attribution for every downloadable model:

- Parakeet TDT 0.6B v3 and Parakeet TDT-CTC 110M by NVIDIA,
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  The quantized ONNX exports are by the sherpa-onnx project; Caelum does not
  modify those files. NVIDIA does not endorse Caelum.
- Cohere Transcribe by Cohere, Apache 2.0.
- Whisper by OpenAI, MIT; the catalog uses deepdml's CTranslate2 conversion.
- Parakeet TDT 0.6B v2 and Canary 180M Flash by NVIDIA, CC BY 4.0.
- Distil-Whisper by the Hugging Face team, MIT, based on Whisper by OpenAI;
  Whisper Large v3 uses Systran's CTranslate2 conversion.
- Moonshine Base by Useful Sensors, MIT.

The opt-in fixture downloader retrieves public test recordings, not models,
from pinned sherpa-onnx Hugging Face repositories. The two LibriSpeech samples
and their references are distributed in the upstream
[`test_wavs` directory](https://huggingface.co/csukuangfj/sherpa-onnx-zipformer-en-2023-06-26/tree/11a70a47ec5fd969c17b8d0818681d222a147781/test_wavs).
LibriSpeech audio derives from public-domain LibriVox readings. The third sample
is the pinned Parakeet v2 repository's `test_wavs/0.wav`; that repository declares
CC BY 4.0. Recordings are downloaded only by an explicit developer command,
outside the source tree, and are not included in packages.


## Silero voice activity detector — MIT

`python/caelum/data/silero_vad.onnx` is the Silero detector distributed by
[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx).
It is bundled so silence detection never needs a runtime download. Snapshot
retrieved November 17, 2026; SHA-256:
`9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`.
The upstream [Silero license](https://github.com/snakers4/silero-vad/blob/master/LICENSE)
is included verbatim in `python/caelum/data/Silero-LICENSE.txt` and the Python wheel.

## Optional NVIDIA runtime

`caelum install-nvidia` downloads upstream sherpa-onnx, NumPy and NVIDIA CUDA
user-space wheels into a separate environment. The base app does not redistribute
those GPU binaries. Their upstream licenses and notices accompany the installed
wheels; exact versions and wheel digests are in `python/caelum/data/nvidia-cu12.txt`.
