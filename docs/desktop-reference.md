# Caelum desktop reference

For downloads and first dictation, see the [project README](../README.md). Run source and packaging commands below from the repository root.

## Development

To try the native app on a clean checkout with a fresh profile, follow [Try dev on Linux](try-dev.md).

Requires Node 24+, the repository's pinned Rust toolchain, uv, Python 3.11–3.14, PortAudio, WebKitGTK 4.1,
a C/C++ toolchain, pkg-config, and libayatana-appindicator/libappindicator.

```sh
uv sync --locked --extra dev --extra local --python /usr/bin/python3
npm ci
npm run tauri dev
```

For the optional native Hyprland overlay, use the distro Python with its GI/Cairo
modules available (`uv venv --system-site-packages --python /usr/bin/python3
--allow-existing`) and install GTK4 and gtk4-layer-shell. The main window does
not import PyGObject. Tauri's Linux WebView uses GTK3/WebKitGTK internally.

The first run opens Speech → Microphone → Shortcut → Practice. Choose **On this
computer** for downloaded models or **Online** for an API provider. Downloads
continue during setup and while the window is hidden to the tray. The mic test
is local. Only Online practice requires upload consent; local practice never
falls back to an upload. Keys use Secret Service when available, otherwise
an owner-only file with an explicit unencrypted-storage disclosure.

```sh
npm run check                       # ESLint, React tests, strict TS, Vite build
uv run ruff check python tests scripts
uv run pytest -q
uv run python scripts/generate-contracts.py
cargo check --manifest-path src-tauri/Cargo.toml
npm run tauri build -- --no-bundle   # native executable, packaging step below
```

`npm run dev` serves only the frontend; IPC requires `tauri dev`. The standalone
web page is not a simulated transcription service.

## Architecture

- `src/features`: dashboard, retained-history statistics/calendar, searchable
  transcripts, settings/advanced providers, and consented onboarding.
- `src/components/ui`: shadcn components retrieved using the shadcn CLI.
- `src/lib`: typed IPC and generated Python configuration types.
- `src/hooks`, `src/stores`: native event subscription and Zustand navigation/status.
- `src-tauri`: single-instance window, tray, capability policy, command transport,
  bounded request timeouts, process supervision, and orderly shutdown.
- `python/caelum`: existing PortAudio/NumPy audio, HTTPX/asyncio providers,
  conservative cleanup/chunking, SQLite, TOML, key storage, MPRIS, D-Bus,
  Hyprland and portal shortcuts. `sidecar.py` adapts these services over JSON lines.

The existing UID-checked daemon socket remains compatible with `caelum control`.
Native shortcuts retain target-addressed paste, Escape cancellation, lock/suspend
safety, MPRIS pause/resume, and retryable audio held only in bounded memory.
Portable desktops retain portal shortcuts where available, Record/Finish, explicit
copy, and desktop notifications. Closing the main window keeps it alive only when
a tray watcher is available; quitting stops the service after confirmation.

Data paths and formats are preserved: `$XDG_CONFIG_HOME/caelum/config.toml`,
credentials/setup metadata alongside it, and
`$XDG_DATA_HOME/caelum/history.sqlite3`. Defaults fall back to standard XDG paths.
No SQL schema migration or credential copying is performed.

## Distribution packages

Build **inside the target distribution**, with its system Python and native build
libraries. The native package builder vendors the hashed `uv.lock` Python wheels
under `/opt/caelum/lib`; end users do not run pip or create a virtual environment.
System Python, audio libraries, WebKitGTK, and native helpers are declared package
dependencies. GTK4/GI/Cairo are needed only for the isolated native overlay.

```sh
python3 scripts/build_package.py ubuntu-24.04
python3 scripts/build_package.py ubuntu-26.04
python3 scripts/build_package.py debian-12
python3 scripts/build_package.py fedora-43
python3 scripts/build_package.py arch
```

Outputs go to `dist/`: `.deb`, `.rpm`, or `.pkg.tar.zst`. Install using `apt install
./…deb`, `dnf install ./…rpm`, or `pacman -U …pkg.tar.zst`. The Arch PKGBUILD
in `packaging/arch` invokes the same builder; it checks out the matching release Git tag. GitHub Actions builds, installs, and smoke-tests each target
package before publishing signed update metadata. Release signing still requires
the existing Ed25519 signing secret; no signing key is included in this repository.

Direct `tauri build` bundles are development artifacts: use the native package
builder for the complete vendored Python payload and distro dependency metadata.

## Platform limits and acceptance

Tauri cannot place ordinary windows reliably on Wayland or provide the original
click-through layer-shell contract. `python/caelum/hud.py` is intentionally retained
as a separate GTK4 layer-shell helper; it is the only GTK4 UI. It never becomes a
competing main window. GNOME and other compositors without layer-shell use portable
notifications rather than a falsely equivalent overlay. Native Hyprland integration
requires the existing Lua-capable compositor API. Other Linux desktops use manual paste.

Read [migration mapping](migration.md), [architecture](architecture.md),
[Linux prerequisites](linux.md), and [acceptance checks](acceptance.md).
Hardware recording, real provider uploads, desktop permissions, tray behavior,
suspend/lock, and installation on each distribution require host acceptance testing.
Do not interpret passing mocked tests as production certification.

## Appearance

Settings → General → Theme → **Color theme** selects T3 Code (the default), T3 Chat,
Grove, Ocean, Ember, Iris, or the original Caelum mint. **Appearance** separately
selects dark, light, or system mode. Preferences are saved in the existing TOML
file as `desktop.color_theme` and `desktop.theme`; old configuration files remain
valid. These palettes style the main window; the native layer-shell recording
HUD and system window decorations retain their separate styling.

T3 palettes are imported from a pinned, MIT-licensed upstream version; see
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). The
[T3 Code comparison and public-release report](t3code-comparison.md) records
source references, actual release assets, implementation changes, and remaining
qualification work. A [release note template](release-template.md) is included.

## Reliability and release workflow

Requests and responses use [shared runtime contracts](ipc.md), bounded
transport deadlines and explicit error states. Recording/transcription operations
are never automatically replayed after a transport failure.

Pull requests run checks. Candidate builds stay in GitHub Actions until a maintainer selects one for Testing. Stable promotion verifies the same package bytes and signs the update metadata in the release environment. [Release procedure](releasing.md)

Caelum is [MIT licensed](../LICENSE). Packages include third-party license texts,
metadata, and corresponding MPL-2.0 crate sources under
`/usr/share/licenses/caelum/third-party/`. Python 3.11–3.14 is currently supported;
3.15 removes an API used by the retained D-Bus dependency, so metadata prevents
installation on that interpreter until the dependency is updated. Development
uses `.python-version` (3.14); native packages use their target system Python.

## Vocabulary, offline transcription, and cleanup styles

Dictionary includes custom vocabulary (up to 4000 characters), shared by
Online and local recognition. Names and technical terms act as recognition hints.
The **Styles** page offers Off, Light, Thorough, Email, Casual, and Code for
online dictation, with examples. Enabled styles retain the
existing conservative validation and fall back to raw text on failure.

With **Light** or **Thorough** online cleanup, say a heading and at least two
items, or use clear cues such as “first … second …”. For example, “shopping
list first rice second onion third oil” pastes as:

```text
Shopping list:

1. Rice
2. Onion
3. Oil
```

Unordered items, such as a few issues you found, use `- ` bullets. Ordinary
sentences stay prose. This formatting needs no separate setting. With cleanup
off, online transcription does not infer lists. Local dictation uses built-in
rules for clearly enumerated English lists without a text model or a style setting. You can also say
“new line”, “new paragraph”, or “bullet point” as separate phrases. For
example, “Notes. New paragraph. Bullet point. Rice.” produces a blank line
after “Notes.” followed by `- Rice.`. Commands must stand alone in the
transcript (separated by punctuation or line breaks); “a new line of work”
stays literal.

### On this computer

Settings → Transcription offers **On this computer | Online**. The local
picker shows Parakeet, Small and quick, Most accurate (on ≥8 GB machines), and
Any language, with five alternatives under **Show all models**. Hardware and
language guide the recommendation; Hindi and other Indian languages are pointed
to Online for now. Downloads are resumable, verified against pinned SHA-256
values, and never start without your action.

Local dictations do not upload audio or refinement text. Fallback is **off by
default**. “Use Online instead” explicitly authorizes uploading a dictation only
if a local model is missing or cannot load. Unclear speech is never uploaded. “When you’re offline” can opt into a downloaded model
when Online fails with a connection, timeout, or quota error. The HUD and history
record the engine actually used. Update checks remain controlled separately.

Existing configs without an engine remain Online. The old `cloud` spelling
migrates to `online`. Retired executable/GGML-path options are ignored on upgrade;
choose a catalog model in Settings.

Python/source installations need the `local` extra. Native packages vendor it
by default; weights are **never bundled**.

```sh
uv sync --locked --extra dev --extra local --extra whisper
.venv/bin/caelum models list
.venv/bin/caelum models download parakeet-v3
.venv/bin/python scripts/download-local-fixtures.py /tmp/opencode/caelum-local-fixtures
.venv/bin/caelum benchmark /tmp/opencode/caelum-local-fixtures/manifest.json \
  --engine local --model parakeet-v3 --threads 4 --repeat 3 \
  --output /tmp/opencode/benchmark-results-parakeet-v3.json
```

`local` installs sherpa-onnx for Parakeet, Cohere, Canary and Moonshine. `whisper` is optional and
installs faster-whisper for `whisper-turbo`. With pip, use
`pip install 'caelum-dictation[local,whisper]'` from a version containing this preview.
Speech models are never included in the wheel or downloaded by runtime initialization.
The small MIT-licensed Silero voice detector is bundled for offline silence detection.
They live under `$XDG_DATA_HOME/caelum/models` (normally
`~/.local/share/caelum/models`), with pinned revisions, size/hash checks and receipts.
Interrupt a CLI download and repeat the command to resume. The desktop also has
Pause, Resume and Cancel, a single-download queue, Check files, and confirmed
removal. Use `caelum models verify <id>` for a full hash check or `caelum models
remove <id>` to reclaim space (switch away from it and stop benchmarks first).
`caelum models pin <id>` re-fetches a pinned source and prints file metadata for
review; it never installs files or edits the catalog automatically.

Parakeet vocabulary hints use local hotword biasing. Whisper receives the
vocabulary as an initial prompt. Canary, Cohere and Moonshine do not use these
hints. Silero skips silence and finds pauses before local decoding. Long recordings
are split at pauses, with maximum windows of 35 seconds for Cohere, 30 seconds
for Whisper and 60 seconds for Parakeet. Vocabulary echoes and subtitle boilerplate
are filtered. For known English speech, offline cleanup also removes “um” and “uh”. All languages support
Dictionary replacements without uploading text.

Settings → Transcription offers Auto, GPU and CPU execution and an idle unload
period (five minutes by default; Never keeps the model resident). The base install
includes CPU inference. For Parakeet and other sherpa models, see
[optional NVIDIA setup and platform verification](nvidia.md). Auto checks
the selected backend; GPU requires it to activate CUDA. Settings reports the
loaded device. x86-64 processors without AVX2 are directed to Online before native
runtimes are imported.

Model switches load the candidate before saving the new selection. A failure keeps
the previous selection and engine working. Explicit Online fallback runs only if
a local model is missing or cannot load; unclear speech and decode failures do
not upload audio. History records the engine, model, and selected or detected
language (Auto when an engine cannot report detection).

New downloads record verified file sizes and modified times. Startup and loading
use these quick checks; Check files still performs full SHA-256 verification.
Old receipts receive a one-time verification to populate the cache.
Local inference is serialized; cancellation discards its result, though an
in-progress native decode must finish before the worker can unload.

### Optional Whisper component

For Python installations:

```sh
pip install 'caelum-dictation[local,whisper]'
```

For native packages, install into a user-owned, ABI-specific component folder
with the **same Python interpreter** that runs Caelum (no system pip changes):

```sh
component_dir="${XDG_DATA_HOME:-$HOME/.local/share}/caelum/components/$(python3 -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')"
uv pip install --python /usr/bin/python3 --target "$component_dir" 'faster-whisper>=1.2,<2'
```

Restart Caelum, then download Any language. Component folders are appended after
packaged dependencies; `.pth` files are not executed. Remove/reinstall the folder
for a new Python minor version. Whisper uses CTranslate2's CUDA support, not the
sherpa component. In Auto, a failed CUDA decode retries on CPU.

The experimental `build_package.py appimage` target is separate from the candidate workflow’s Ubuntu-based `scripts/build-appimage.sh`. The experimental target requires
linuxdeploy, its GTK plugin, and appimagetool. It targets **system Python 3.14**;
GTK4/GI and desktop helpers are host prerequisites for the optional native HUD.
It is not yet part of signed automated promotion. Clean-VM qualification and
package-size comparisons remain mandatory before release.

See [local model measurements](local-models-benchmark.md) and the
[release qualification checklist](local-models-release-checklist.md).
