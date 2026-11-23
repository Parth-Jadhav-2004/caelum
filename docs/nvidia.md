# NVIDIA inference for packaged Caelum

The default installation runs local speech models on CPU. An NVIDIA adapter in
the model picker is a hardware hint. It does not mean either speech backend can
use it. `nvidia-smi`'s CUDA version describes driver compatibility, not the
libraries loaded by the app.

## Parakeet, Canary, Moonshine and Cohere (sherpa-onnx)

Use x64 Linux (glibc 2.28+) or Windows x64, an AVX2 CPU and a CUDA 12.8/cuDNN 9
compatible NVIDIA GPU with enough free VRAM for the model. The tested card is
an RTX 3050 Laptop 6 GB; this is not a minimum-VRAM measurement. For this
CUDA 12.8 Update 1 stack use an NVIDIA driver **570.124.06+ on Linux** or
**572.61+ on Windows** ([NVIDIA release notes](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html)).
Windows also needs the Microsoft Visual C++ x64 runtime. See qualification below.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and
   make it available on PATH. Allow several GB for the component and installer
   cache (the installed Linux environment alone is ~3.2 GiB).
2. **Native Linux package:** run `caelum install-nvidia` as your normal user.
   **AppImage:** use the `usr/bin/caelum install-nvidia` launcher inside an
   extracted AppImage (`./caelum-…AppImage --appimage-extract`).
   **Windows:** in PowerShell, from the Caelum installation directory run
   `& ".\engine\python.exe" -I -m caelum.cli install-nvidia`.
3. In **Settings → Transcription**, select a downloaded model and choose **GPU**
   (requires CUDA), **Auto** (can use CPU) or **CPU**. If the model is already
   loaded, reselect the device or restart Caelum. Read the active device beneath
   **Run local models on** while the local engine is ready.

The installer uses a private Python 3.12 environment, the pinned
[upstream CUDA wheel](https://k2-fsa.github.io/sherpa/onnx/python/install.html)
and hash-checked NVIDIA user-space libraries. No system CUDA toolkit is required
for sherpa. The worker checks visible devices and executes a small local provider
probe before opening speech weights. It then checks ORT node placement **for
the selected recognizer**. Mixed CPU/CUDA graphs are normal, particularly with
quantized weights. Audio stays in local pipes; the Silero speech gate uses CPU.

If the driver is visible but GPU activation fails, check driver compatibility and
free VRAM; unset a restrictive `CUDA_VISIBLE_DEVICES` before starting Caelum.
For an incomplete or damaged runtime, quit Caelum, remove **only** the
`components/nvidia-cu12` directory and repeat step 2. On Linux it lives under
`${XDG_DATA_HOME:-$HOME/.local/share}/caelum`; on Windows under
`%LOCALAPPDATA%\Caelum`. Removing it also returns to a CPU-only sherpa installation.
Do not remove the `models` directory: downloading weights cannot repair CUDA.

## Whisper (faster-whisper / CTranslate2)

Whisper does **not** load the sherpa worker or share its DLL search path.
Windows bundles faster-whisper; native Linux uses the [optional Whisper
component](../README.md#optional-whisper-component). For the pinned CTranslate2
4.9.0 x64 wheels, provide a CUDA 12 compatible driver and CUDA 12 cuBLAS in
the **engine's** loader path (Linux: system library path or `LD_LIBRARY_PATH`;
Windows: CUDA `bin` on PATH before launch). Other CTranslate2 builds may require
their matching cuDNN too. The backend must report a CUDA device and support
`int8_float16`. Explicit GPU does not retry on CPU. Auto may retry locally, in
which case Settings reports CPU.

## Reproduce package qualification

Use a disposable profile, a copy of the catalog model with its receipt, and the
public `librispeech-0.wav` fetched by `scripts/download-local-fixtures.py`.
From the matching source checkout, run with **the packaged engine**, not the
development virtual environment:

```sh
# Linux: extracted native package (stage); use the package target's Python ABI
PYTHONPATH="$PWD/stage/opt/caelum/lib" /usr/bin/python3 -S scripts/smoke_nvidia.py \
  /path/to/copied/models /path/to/librispeech-0.wav
```

```powershell
# Windows: $install is the installed NSIS app directory
& "$install\engine\python.exe" -I scripts/smoke_nvidia.py C:\qa\models C:\qa\librispeech-0.wav
```

The check runs weight verification, CPU VAD, actual transcription and output
filtering; it requires a known word and reports only counts. Its temporary ORT
profiles cover the speech model, **excluding** the CUDA preflight. It requires
CUDA compute events rather than memory copies. Repeat with `--model <id>` or
`--device cpu`. On a CPU-only machine or with a required native library missing,
`--device gpu` must report recovery; `--device auto` should still transcribe.

### Qualification record (2026-11-23)

- **Linux:** Extracted Arch x86-64 package, Omarchy/Hyprland, kernel 7.2.15,
  system Python 3.14.8, RTX 3050 Laptop (6 GB), driver 615.78.08.
  Both explicit GPU and Auto transcribed 18 words with Parakeet v3 revision
  `ed5d745623472f97cfc2e6c2916ee248798fc5a8`. The speech sessions recorded
  **5,039 CUDA node executions**, including 72 MatMul, 24 Softmax and 96
  LayerNormalization operations. This does not imply all operations ran on GPU.
  The same package's desktop `practice` IPC returned 18 words including the
  reference keyword with explicit GPU selected: the WAV was streamed live into
  a private PulseAudio pipe-source, with upload, clipboard and history disabled.
  Tested source `2b7979db587f5e6d8b0f899776bdd3dd04c5e8b5`;
  Arch package SHA-256 `19027d7680cb2b844984a7987b0ea59de89e12976e7d9f48503bc0db1bb5a731`.
- **Other Linux models:** Parakeet v2, 110M, Canary 180M, Moonshine Base and
  Cohere Transcribe each returned 18 words including the reference word;
  their profiles recorded 5,063 / 4,117 / 24,358 / 35,548 / 37,350 CUDA node
  events respectively. Whisper Turbo with the optional faster-whisper 1.2.1 +
  CTranslate2 4.9.0 component also returned 18 words; `nvidia-smi pmon`
  measured 34–92% SM utilization attributed to its PID during repeated decodes.
  Distil-Whisper and full Whisper large-v3 were not qualified.
- **Linux recovery:** With no optional runtime, with `/dev/nvidia*` hidden in
  a private device namespace, and with the worker's `libcurand.so.10` masked
  while the real GPU remained visible, GPU returned a setup error. Auto decoded
  the reference on CPU (18 words, zero CUDA speech events) in all three cases.
  The no-device case emulated a CPU-only host; it was not a second physical machine.
  Separately, with no cuBLAS on the loader path, Whisper Turbo rejected explicit
  GPU and decoded the reference on CPU in Auto.
- **Windows CPU and recovery:** The [NSIS installer check at `3d01efc`](https://github.com/Parth-Jadhav-2004/caelum/actions/runs/45144183909)
  passed on the hosted Windows x64 CPU runner. Packaged Parakeet v3 transcribed
  the same 18 words on CPU. Explicit GPU reported a setup error with the add-on
  absent, with it installed but no accessible GPU, and with `cudart64_12.dll`
  removed from the loader path. Auto returned 18 words on CPU in the latter two cases.
- **Windows GPU:** Not verified for any model. A Windows x64 NVIDIA machine is
  still needed to run the packaged speech-profile check above.
