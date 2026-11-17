# Local models: release qualification

P1–P6 implementation is present. This document separates implemented checks
from release evidence; do not mark the release qualified solely from unit tests.

## Implemented and exercised on the development laptop

- Online remains the migration default, with `cloud` compatibility. Retired
  executable/GGML-path options are ignored without executing them.
- Local routing and cleanup privacy, explicit one-shot fallback, background
  loads, single native worker, HUD loading/missing/fallback states and
  actual-engine history.
- Pinned files and archives, Range resume, source fallback, bounded downloads,
  safe allowlisted extraction, receipts, repair, process locking, queue,
  pause/cancel, restart recovery and developer pinning.
- Hardware/language table, memory/disk/component gates, Settings cards,
  keyboard selection, progress accessibility, download announcements,
  Speech onboarding, download-through-setup and Home recovery states.
- All nine catalog models: successful download, hash verification, load and
  non-empty/repetition-guarded transcription of three public WAVs, plus a
  substring check on a referenced sample. Each model check ran in a fresh process.
- Native HUD + 110M provider-path smoke on this Hyprland login, with no
  microphone capture, text insertion, history or HTTP requests.
- Parakeet hotword WER regression check, persisted decode stats, CPU int8
  Whisper, and automatic CPU recovery when CUDA lacks cuBLAS.
- Native builder exports the locked `local` extra. The installed sherpa package
  measured 38,625,332 bytes here, below the enforced 50,000,000-byte budget.
  This is a runtime-footprint check, not a compressed release-asset comparison.
- About attribution, third-party notices and optional-component documentation.

## Required before a public release

- Build deb and rpm inside every supported distribution. Install into clean VMs
  with their declared system dependencies. Download 110M, disconnect networking,
  dictate and verify visible delivery, settings/history migration and uninstall.
- Build the experimental AppImage using linuxdeploy + GTK plugin and
  appimagetool; test its system-Python-3.14 and GTK4/GI prerequisites explicitly.
  It is a separate manual target, not in signed promotion yet. Do not market it
  as independent of all host libraries/interpreters.
- Compare compressed native artifacts with the same baseline build:
  growth must be ≤50 MB and no speech weights or recordings may appear in any
  package. The small Silero voice detector is bundled with its MIT license.
- Exercise downloads through real suspend/reboot, disk exhaustion, damaged
  files, proxies/HF mirrors, and a hidden tray window.
- Check real working CUDA libraries/GPU inference. The laptop only established
  CPU recovery from unavailable cuBLAS, not GPU performance.
- Verify longer dictations, additional languages and accented/noisy speech,
  including chunk seams, quiet voices, cancellation while native decoding,
  and fallback delivery. Keep the brief's Indian-language recommendation Online.
- Do a real keyboard/screen-reader/responsive visual pass on Settings and setup.
  The in-app browser was disconnected during this session; component and axe
  tests are not a substitute for that manual visual check.

No clean-VM installs, public release publication or signed promotion were
performed as part of this implementation.

## Local transcription fixes — November 17, 2026

Rebased onto main `8890b43` while preserving the redesigned desktop layout.
The model picker uses existing Settings rows, shared controls and typography.

Silero is bundled and runs before local decoding. The duration ceilings are
35 seconds for Cohere, 30 for Whisper and 60 for Parakeet. Chunking prefers an
earlier complete-utterance pause instead of filling a sequence decoder to its
ceiling. A 70.86-second public sample assembled from four LibriSpeech utterances
was checked with all three engines on CPU: all four closing words were retained.
Cohere and Whisper used four roughly 17-second chunks; Parakeet used two roughly
35-second chunks. The regression suite also checks uninterrupted speech bounds
and original recording offsets. This is a targeted regression, not a general
accuracy claim for long or noisy dictation.

All nine installed models passed the three-public-WAV smoke test with the new
Silero path. The combined-process run hit the memory guard for Cohere after two
other models; Cohere then passed in a fresh process. No guard was bypassed.
Working GPU inference, clean-VM installation and live screen-reader/desktop
interaction remain release checks.
