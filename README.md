# Caelum

Private dictation for **Linux desktops**, with native Hyprland integration and a
portable recording workflow for GNOME, KDE, and X11. **Caelum 0.2 is a cross-distro
preview.** Download the package matching your OS from
[GitHub Releases](https://github.com/Parth-Jadhav-2004/caelum/releases) and read the
[Linux compatibility and installation guide](docs/linux.md).

On Hyprland, hold **Super+Alt+V**, speak, and release to paste once into the original
application. On other desktops, use **Record / Finish recording** (or an available
portal shortcut), then **Copy text** and paste into your chosen app. Caelum uploads
recordings to your configured transcription provider and optionally cleans text
with an LLM. Completed dictations are stored locally; audio is not saved.

The portable backend uses notifications and logind lock feedback. The native
Hyprland backend additionally offers a click-through recording pill and addressed
paste. Portal availability varies by desktop/version; package availability does
not imply every desktop combination has been hardware-qualified.

## Desktop application · Phase 2

```bash
./scripts/run.sh app
# Or, when credentials already exist in the launch environment:
.venv/bin/caelum app
```

The native GTK4 application uses a **pure-black theme**, charcoal surfaces, and Adwaita Sans, without gradients or hover highlights. The app name stays at the upper left above a sidebar toggle; collapse it to keep compact icon navigation. Opening the window does not start microphone capture or provider requests. Use **Start dictation service**, then the configured hold-to-talk shortcut. Closing the window leaves dictation running; **Stop service** stops it and discards pending audio. **Pause** cancels pending work and ignores the shortcut until resumed.

- **Overview:** live service state, shortcut, today's saved words, retained recording minutes, recent dictations.
- **History:** automatically saved completed transcripts, literal search (up to 200 matches), copy, delete-one, confirmed delete-all, sensitive-text JSONL export.
- **Statistics:** today / last seven days / calendar month / retained words, seven-day chart, recording-time WPM, mean release-to-dispatch latency.
- **Settings:** shortcut recorder, microphone selection, explicit three-second local input meter test, language, provider/model settings, history retention, and grouped recording, provider, and storage controls. Settings are validated and saved atomically. Idle services reload without restarting; active sessions or shortcut collisions leave the previous runtime settings intact and show an application warning.
- **Desktop integration:** Settings can add Caelum to the app launcher or enable/disable start-at-login. These entries use this checkout's credential-loading launcher. Keep the checkout at its installed path. Nothing is installed or enabled automatically.

History uses `$XDG_DATA_HOME/caelum/history.sqlite3` (normally `~/.local/share/caelum/history.sqlite3`), owner-only file permissions, and a private application directory. The database is created when the first dictation completes. Only final transcripts are stored: no audio, raw transcript, source application, or credentials. History is always enabled; use **Delete all** to erase saved entries. Older `history_enabled = false` preferences are ignored and removed on the next settings save. Retention runs on read/write, not while Caelum is entirely closed. Statistics recalculate from retained entries. See [privacy details](docs/privacy.md), including disk-encryption and export limitations.

Statistics use retained history, so deletion and retention recalculate totals. Word counts use whitespace-separated words; WPM uses recording duration. Latency measures release to dispatch rather than observed on-screen insertion.

Modifier-only shortcuts such as `CTRL + SUPER` are supported: press in either order, hold both to dictate, and release either to finish. Left/right variants work. Such a chord also begins recording when used as the prefix of a longer desktop shortcut; choose a three-key shortcut if that overlap is undesirable.

This application is Linux-only. The portable desktop backend is a preview; see the compatibility guide. A system-tray icon, cross-platform ports, encrypted database/keyring integration, and automatic upgrades are not implemented.

## Source installation on this Omarchy machine

The required native packages were already installed during development. For another Arch/Omarchy machine, install `python`, `python-gobject`, `python-cairo`, `gtk4`, `gtk4-layer-shell`, `portaudio`, `wl-clipboard`, `libnotify`, and `uv` using the distro package manager. The native integration requires Hyprland's **Lua API**; Omarchy lock feedback is used when available, otherwise logind is used; this implementation was checked on **Hyprland 0.56.2**.

```bash
./scripts/setup.sh
.venv/bin/caelum init
```

`init` creates `~/.config/caelum/config.toml` and refuses to overwrite it. Edit that file for microphone, language, hotkey, model, reduced motion, or high contrast. See [config.example.toml](config.example.toml).

Provide `GROQ_API_KEY` and `OPENAI_API_KEY` in the environment launching Caelum. Do not put secrets in the TOML config or commit them. `.env.example` documents the variable names; `.env` is deliberately **not automatically loaded**.

```bash
.venv/bin/caelum models stt
.venv/bin/caelum models cleanup
.venv/bin/caelum doctor
.venv/bin/caelum serve
```

If credentials are saved in `~/.config/caelum/environment` (mode 600), the convenience launcher loads them before starting Caelum:

```bash
./scripts/run.sh doctor
./scripts/run.sh          # starts dictation
```

For OpenRouter, set cleanup `base_url="https://openrouter.ai/api/v1"`, `key_env="OPENROUTER_API_KEY"`, and `model="openai/gpt-6-luna"`. The launcher and example systemd unit use the same private environment file. Keep that file outside the repository.

For Meta directly, use cleanup `base_url="https://api.meta.ai/v1"`, `key_env="MODEL_API_KEY"`, `model="muse-spark-1.3-contributor"`, `reasoning_effort="minimal"`, and `timeout_seconds=3.0`. Meta does not support disabling reasoning for Muse Spark. [Contributor mode permits Meta to use submitted content for model training](https://dev.meta.ai/docs/models), including cleanup transcripts. The currently configured local model can be checked in `~/.config/caelum/config.toml`.

The default cleanup model is `gpt-6-luna`, with `reasoning_effort="none"`. Its identifier and Chat Completions support were verified in the [official OpenAI documentation](https://developers.openai.com/api/docs/models/gpt-6-luna) on October 28, 2026. Startup checks the configured cleanup model against the account's `/models` listing. Account access and live performance have **not** been verified without credentials. Set `[cleanup] model=""` to explicitly use raw STT only; the pill then says “Done · unrefined”. A failed or slow cleanup request also falls back to the raw transcript.

The service registers compositor bindings at runtime and removes its own binding handles on clean exit. **No Hyprland config files are edited.** It refuses shortcut collisions, re-registers after compositor config reload, consumes the recording chord, handles modifier release ordering, and enables Escape cancellation only during an active session. Stop with Ctrl+C. A hard kill may leave runtime shortcuts until `hyprctl reload` or the next Caelum startup; no microphone continues after process death.

## Use and recover

- Hold **Super+Alt+V** to capture; release to finalize and paste once.
- **Escape** cancels capture, requests, and pending retry audio. Idle Escape behaves normally.
- Accidental presses under 200 ms and confirmed silence insert nothing.
- Switching applications while speaking copies the final text and asks you to paste manually. Caelum does not move focus to paste.
- Network failures retain audio **in memory** for up to 60 seconds. Use notification Retry/Cancel actions or the commands below. A pending retry blocks new sessions. Notification action support depends on the notification daemon; CLI recovery is always available.

```bash
.venv/bin/caelum control retry
.venv/bin/caelum control cancel
.venv/bin/caelum control status
.venv/bin/caelum devices
.venv/bin/caelum hud-demo
```

`status` returns only state and recent numeric diagnostics. `hud-demo` replays all states with a still waveform, without recording, uploading, or inserting text. Audio capture is bounded to 120 seconds by default (configurable to 600 seconds). Unsupported 16 kHz devices fail with microphone guidance rather than silently changing format.

The insertion adapter checks the original window address and process ID and uses target-addressed Lua key dispatch. Terminals tagged by Omarchy use Shift+Insert; other apps use Ctrl+V. App-specific paste behavior can differ. A compositor dispatch acknowledgment does not prove visible insertion in every application: diagnostics explicitly record that visibility is unobserved. A disposable GTK entry integration test verifies actual visible paste on this machine; browser/editor/chat/office checks remain manual.

## Test and benchmark

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
# Native desktop smoke test opens a short-lived window with isolated empty storage.
GDK_BACKEND=wayland CAELUM_DESKTOP_TESTS=1 .venv/bin/pytest tests/test_desktop.py -q
# Native tests briefly record/cancel, show a disposable text field, and restore focus.
# They send no audio/text to cloud providers.
CAELUM_NATIVE_TESTS=1 .venv/bin/pytest tests/test_native.py -q -s
```

The default path sends **one full recording after release**. Experimental `strategy="chunked"` starts overlapping uploads in the background, bounded to two concurrent calls. Sample offsets and word timestamps align overlap; missing, conflicting, or ambiguous seams cause whole-audio repair. It deliberately favors preserving words over winning a latency benchmark. No provisional cleanup is enabled.

[Benchmark instructions](docs/benchmarks.md) explain the opt-in corpus runner, WER, p50/p90/p95, and the remaining release gates. Corpus benchmarking uploads only the audio files you explicitly provide. No synthetic or mocked API timing is presented as real provider performance.

For start-on-login, adapt [the optional systemd user unit](packaging/caelum.service.example). Replace the path, provide credentials in a user-owned mode-600 environment file, and import `WAYLAND_DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`, `XDG_CURRENT_DESKTOP`, and `OMARCHY_PATH` into the user service environment. Nothing is enabled automatically.

See [architecture](docs/architecture.md), [privacy](docs/privacy.md), and [manual acceptance checks](docs/acceptance.md).
