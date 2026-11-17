# Local models: release qualification

P1–P6 implementation is present. This document separates implemented checks
from release evidence; do not mark the release qualified solely from unit tests.

## Implemented and exercised on the development laptop

- Online remains the migration default, with `cloud` compatibility and retained
  whisper.cpp/GGML configurations.
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
  growth must be ≤50 MB and no weight/audio files may appear in any package.
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
