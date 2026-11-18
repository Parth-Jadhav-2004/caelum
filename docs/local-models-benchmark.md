# Local speech models: P0 laptop benchmark

Measured on **17 November 2026**, on this laptop: Intel Core i5-13450HX,
x86_64, 16 logical CPUs, approximately 15.2 GiB RAM, AVX2. CPU inference,
four runtime threads, Python 3.14.8, sherpa-onnx 2.0.1, faster-whisper 1.2.1,
CTranslate2 4.9.0, NumPy 2.5.4.

## Result

**P0's latency gate passes on the available 7.435-second fixture:** Parakeet v3
averaged **0.399 seconds** after release across three decodes (0.472, 0.423,
0.301 seconds), against the brief's ≤1.0-second threshold.

No reason emerged here to revisit the proposed Parakeet v3 default. This is a
small spike, not validation across machines, accents, languages or workloads.
The P0 spike did not change dictation defaults. The subsequent P1–P6
implementation exposes the catalog engine through Speech setup and Settings;
existing users remain Online unless they choose otherwise.

Across the complete three-clip corpus (nine decodes per model):

- **Parakeet v3:** load 1.58 s; 20.00× realtime; mean wait 0.513 s;
  observed p95 0.831 s; process peak RSS 1,467 MiB.
- **Parakeet 110M:** load 0.64 s; 52.07× realtime; mean wait 0.198 s;
  observed p95 0.335 s; process peak RSS 464 MiB.
- **Cohere Transcribe:** load 4.12 s; 7.71× realtime; mean wait 1.331 s;
  observed p95 1.998 s; process peak RSS 3,664 MiB.
- **Whisper turbo:** load 2.31 s; 1.43× realtime; mean wait 7.198 s;
  observed p95 7.490 s; process peak RSS 1,998 MiB.

All 36 benchmark decodes returned non-empty text, with no failures or repetition
guard triggers. The separate opt-in integration check also passed all four
models on the three WAVs. The local benchmark constructs no HTTP client and
never invokes online cleanup; unit tests enforce this even with online cleanup
configured. Model downloads are a separate, explicitly networked operation.

Numeric results and all per-fixture wait observations are retained in
[`local-models-benchmark.json`](local-models-benchmark.json). Full runtime reports
were written to `/tmp/opencode/caelum-local-benchmarks/<id>.json` during this run;
those local temporary files are not release artifacts.

## Method and limitations

- Three unmodified upstream public WAVs: `parakeet-sample` (7.435 s),
  `librispeech-0` (6.625 s), `librispeech-1` (16.715 s). The
  7–8-second gate therefore uses **one unique recording, repeated three times**.
  A broader 20-clip, 7–8-second corpus remains desirable before release.
- `scripts/download-local-fixtures.py` pins every sample to an exact revision,
  byte count and SHA-256. It retrieves recordings only, not any additional model.
  Source attribution is in `THIRD_PARTY_NOTICES.md`.
- Each model ran in its **own process**, loaded once, followed by three passes
  through the same manifest. The first decode is included, not discarded.
  Downloaded files were already in the OS page cache; these are not cold-boot
  disk-load measurements.
- Wait is complete-clip release to text ready. It includes worker dispatch and
  guards, but excludes capture, cleanup, insertion, UI and application rendering.
  Throughput is total audio duration / total decode time.
- Peak RSS is Linux `ru_maxrss / 1024` in **MiB**, including Python, imports,
  model load and decoding. The JSON key `peak_rss_mb` is retained for the CLI
  contract; do not interpret it as model-only steady-state memory.
- The desktop was running other applications. CPU frequency and contention were
  not controlled. Nine observations do not establish a production p95.
- Language was unset: Parakeet/Whisper auto-detect; Cohere receives `en`.
  Whisper used CPU int8 and default vocabulary hints. No CUDA measurement.
- Only two samples have independent upstream reference text. The CLI computes
  WER on those when supplied; this small corpus cannot rank model accuracy.

## Reproduce

```sh
uv sync --locked --extra dev --extra local --extra whisper
.venv/bin/python scripts/download-local-fixtures.py /tmp/opencode/caelum-local-fixtures
.venv/bin/caelum models download parakeet-v3
.venv/bin/caelum benchmark /tmp/opencode/caelum-local-fixtures/manifest.json \
  --engine local --model parakeet-v3 --threads 4 --repeat 3 \
  --output /tmp/opencode/benchmark-results-parakeet-v3.json
```

Repeat the last two commands separately for `parakeet-110m`,
`cohere-transcribe`, and `whisper-turbo`. Use a clean/default config file with
`--config /path/to/defaults.toml` before `benchmark` to exclude personal
language/vocabulary overrides. The file may be absent to use defaults.

Opt-in runtime smoke checks (no automatic downloads, microphone or uploads):

```sh
CAELUM_TEST_MODELS=1 \
CAELUM_TEST_MODELS_DIR="$HOME/.local/share/caelum/models" \
CAELUM_MODEL_FIXTURES=/tmp/opencode/caelum-local-fixtures/manifest.json \
.venv/bin/pytest tests/test_catalog_local_stt.py::test_real_model_three_clips -q
```

Set the model directory explicitly when using a custom `XDG_DATA_HOME`. Ordinary
tests continue to use isolated XDG paths and fake runtime adapters.

## Implementation follow-up

The initial P0 spike provided:

- The four pinned primary catalog entries, local/Whisper dependency extras,
  resumable foreground CLI downloads, source fallback, SHA-256 checks,
  safe allowlisted archive extraction, atomic installs and receipts.
- A dedicated single-worker `LocalEngine` with serialized native loads/decodes,
  model swap safety, silence/punctuation/repetition guards and token timestamps.
  Cohere and faster-whisper CPU adapters are included early because P0 requires
  their laptop measurements.
- CLI list/download/verify/remove and offline numeric benchmarking.
- Fake-runtime/thread/cancellation/privacy tests and opt-in real-model tests.

The follow-up implements P1–P6 code: config migration, private provider routing,
explicit fallback, background service loading, HUD states, actual-engine history,
hardware recommendation, queued downloads/IPC, Settings, Speech setup and Home,
all five runner-ups, Parakeet hotwords, decode stats, optional CUDA with CPU
recovery, default runtime vendoring, attribution and package budget checks.

All nine catalog models downloaded and passed the three-WAV runtime smoke
checks in separate processes. A native 110M smoke check also exercised the real
HUD and provider path with an HTTP client that must not be called.

Vocabulary follow-up used the default `Caelum, Omarchy, Hyprland` hints and
modified beam search, with uniform-cost segmentation derived from the shipped
tokens (the catalog does not contain original SentencePiece scores). On one
additional three-clip pass, Parakeet v3 was 16.04× realtime / 0.640 s mean wait,
and 110M was 42.32× / 0.243 s. Mean WER on the two referenced clips was unchanged:
0.03819 and 0.01042 respectively. These are regression observations, **not proof
that hints improve accuracy**; the small public corpus contains none of those
technical names.

The laptop exposes CUDA but lacks `libcublas.so.12`. Real runtime tests caught
this after successful model construction; Whisper now retries locally on CPU.
Working-CUDA performance and distribution qualification remain unverified.
See the [release checklist](local-models-release-checklist.md); passing this
spike is not a claim that deb/rpm/AppImage installation has been certified.
