# Caelum

A Linux-first voice dictation application: Tauri 2, React, TypeScript, shadcn/ui,
Tailwind CSS, Lucide, Motion, Zustand, and TanStack Query around the existing
Python capture and transcription engine. Dark first, with light/system appearance.

Audio is sent to the configured transcription provider (Groq by default). Optional
cleanup sends text to its configured provider. Final transcripts can be stored in
local SQLite; microphone recordings are never stored. Local history is not encrypted.
Clipboard managers and exports retain independent copies.

## Development

Requires Node 24+, Rust stable, uv, Python 3.11+, PortAudio, WebKitGTK 4.1,
a C/C++ toolchain, pkg-config, and libayatana-appindicator/libappindicator.

```sh
uv sync --locked --extra dev --python /usr/bin/python3
npm ci
npm run tauri dev
```

For the optional native Hyprland overlay, use the distro Python with its GI/Cairo
modules available (`uv venv --system-site-packages --python /usr/bin/python3
--allow-existing`) and install GTK4 and gtk4-layer-shell. The main window does
not import PyGObject. Tauri's Linux WebView uses GTK3/WebKitGTK internally.

The first run opens Provider → Microphone → Shortcut → Practice. Provider checks
validate model access without uploading audio. The mic test is local. Practice
requires explicit upload consent. Keys use Secret Service when available, otherwise
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
requires the existing Lua-capable compositor API. Other desktops use manual paste.

Read [migration mapping](docs/migration.md), [architecture](docs/architecture.md),
[Linux prerequisites](docs/linux.md), and [acceptance checks](docs/acceptance.md).
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
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The
[T3 Code comparison and public-release report](docs/t3code-comparison.md) records
source references, actual release assets, implementation changes, and remaining
qualification work. A [release note template](docs/release-template.md) is included.

## Reliability and release workflow

Requests and responses use [shared runtime contracts](docs/ipc.md), bounded
transport deadlines and explicit error states. Recording/transcription operations
are never automatically replayed after a transport failure.

Pull requests run fast checks. Native distro packages are built through the
manual candidate workflow, tested after installation, then promoted without
rebuilding. See [releasing.md](docs/releasing.md) for candidate verification,
resumable publication, immutable tags/assets, signing and recovery procedures.
