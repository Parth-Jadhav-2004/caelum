# Application architecture

`caelum serve` owns the only session state machine. PortAudio capture runs in its callback thread, HTTP runs on asyncio, and the GTK HUD is a separate process with its own GLib loop. Press/release callbacks use Hyprland's Lua API, not X11 keyboard hooks.

## Modules

- `audio.py`: 16 kHz mono int16 capture, preallocated bounded PCM memory, sample snapshots, 20 ms RMS, attack/release envelope, speech hysteresis. Silence detection never removes samples.
- `providers.py`: pooled HTTP, bounded STT concurrency, Groq WAV multipart uploads, word timestamps, jittered retry inside a deadline, sanitized errors, conservative cleanup with bounded wait and raw fallback.
- `segmenter.py`: invisible overlapping sample-indexed chunk tasks. Only unique timestamp-aligned token runs are accepted at seams; otherwise a whole-recording repair is used. Genuine repeated words are not deduplicated merely because their text matches.
- `quality.py`: cleanup prompt, whitespace normalization, length/token similarity checks, literal number/URL preservation, and repeated-word preservation. Validation is heuristic, not proof of semantic equivalence.
- `orchestrator.py`: accepted-session identity, deduplicated hotkey tokens, cancellation, capture completion, retry memory/expiry, truthful HUD state transitions, final insertion, bounded numeric diagnostics.
- `linux.py`: subprocess execution without shell interpolation, original window identity, private runtime directory, clipboard, target-addressed down/up key dispatch, exact binding-handle removal, notifications, Omarchy lock-state query.
- `service.py`: UID-checked local Unix socket, single-instance lock, session lock/sleep monitors, compositor reload/output handling, helper supervision and cleanup.
- `hud.py`: GTK4 layer-shell overlay, empty input region, no keyboard interactivity, zero exclusive zone, pinned output, 17 real-energy bars, reduced motion, accessibility labels/announcements, terminal dwell/dismissal, unmapped idle state.
- `benchmark.py`: opt-in same-audio A/B replay with real-time chunk scheduling, transcript-free numeric reports and WER.
- `desktop.py`: native GTK4 overview/history/statistics/settings, monochrome themes, worker-thread I/O, explicit local input test, and UID-scoped service control. The dashboard never subscribes to interim transcription.
- `history.py`: opt-in SQLite final-text persistence after insertion dispatch, retention, literal search, deletion/export, and retained-data statistics. Connections are short-lived and local to each worker thread. Numeric aggregation does not load transcript contents.
- `launcher.py`: explicit app-launcher/autostart desktop entries referencing the existing private-environment launcher.
- `config.py`: typed defaults and validation, including desktop privacy preferences; atomic owner-only TOML writes.

The dashboard and daemon are separate processes. Socket commands add idle-only configuration reload, pause/resume, and orderly shutdown to existing recording controls. Hotkey reload removes only Caelum's bindings; installation failures restore the previous shortcut and leave the old runtime configuration intact. Disk settings may therefore be newer than the running service, which the dashboard reports when applying fails. History consent is re-read at write time rather than copied from the daemon's startup config. UI/database work cannot block capture or HTTP processing; pending persistence tasks are drained during orderly daemon shutdown.

## Important implementation choices

The helper starts with `GDK_BACKEND=wayland` and preloads `libgtk4-layer-shell` before GTK/libwayland load. Upstream documents the interposition requirement in [linking.md](https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md). Without this, importing PyGObject after GTK on this system reports layer-shell unavailable. The helper never falls back to an ordinary or XWayland window.

GTK's renderer is warmed before the helper reports ready, then its surface is hidden. The body is 232×48 logical pixels inside a 280×96 drawing surface; the 16 px lower gutter plus 8 px compositor margin gives 24 px body clearance above the usable bottom edge. Level events are limited to 30 Hz, carry only normalized history, and have a bounded pipe-drain deadline. A helper failure stops capture and shuts down the service.

Hyprland 0.56's `hyprctl dispatch` expects a Lua dispatcher expression. The adapter uses `hl.dsp.send_key_state`, with an explicit key-up in a `finally` block. This also avoids the sticky synthetic-key behavior documented in Omarchy's universal clipboard bindings. The production adapter never calls a focus dispatcher. Only the disposable integration-test fixture explicitly focuses its own window and restores the original target afterward.

The Omarchy shell's read-only `lock isLocked` IPC includes requested/pending locks before secure mapping. It is checked before recording and insertion, and every 200 ms during active work. Query failures fail closed. Login1 sleep/lock signals are monitored as well. Suspend/lock timing and compositor policy still require a manual end-to-end check on the deployed login session.

Retries retain PCM until success, cancel, or a finite expiry; starting a new session never silently deletes pending retry audio. Cleanup never owns insertion or application control. It receives untrusted dictation as data, and only its validated text can reach the fixed insertion adapter.

## Limits

The application targets the installed Omarchy shell and Lua-capable Hyprland, rather than all Linux compositors. It checks native 16 kHz capture support rather than implementing arbitrary hardware resampling. Missing configured microphones fail closed instead of recording an unintended device. A system-tray indicator, cross-platform shell, keyring-backed database encryption, automatic upgrades, and cloud sync are not included. Desktop entries currently require the source checkout's launcher. Chunking is deliberately conservative and may fall back frequently. No universal caret/visible-text observation API exists across Wayland applications; dispatch timings and visibility evidence are reported separately.
