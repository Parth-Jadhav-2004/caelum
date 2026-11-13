# Application architecture

The React WebView is the only main application UI. Tauri owns the native window,
single-instance activation, tray, native export dialog and the Python sidecar.
Frontend code has no filesystem, shell or unrestricted process permissions.

React commands use `src/lib/ipc.ts`; Python configuration types are generated
from dataclasses. The Rust `backend` command forwards versioned, ID-correlated
JSON-lines requests through private stdin/stdout. Python sends responses and
allowlisted status/microphone events. Requests have a bounded deadline; child exit
rejects outstanding calls and exposes a restart message. stdout contains protocol
only; no credential values or transcripts are logged. Secrets entered in setup
are validated against the configured model before storage and cleared from the UI.

The sidecar accesses unchanged services in `python/caelum`. Its supervised daemon
retains the UID-checked Unix control socket, single-instance file lock, capture
state machine, provider pooling, retry expiry, and history persistence. Settings
writes use the existing atomic mode-600 TOML writer. Reloads remain idle-only and
report saved-but-not-applied failures; they never silently discard active audio.
The daemon monitors its sidecar parent so a sidecar crash cannot leave recording
running indefinitely. EOF/SIGTERM cancels samples and shuts down the owned service.
Standalone `caelum serve` remains independent of desktop ownership.

Capture remains sounddevice/PortAudio or PipeWire/PulseAudio through the existing
stable source selection and Bluetooth fallback. Audio stays in memory, with
bounded recording duration and retries. HTTPX performs transcription/cleanup;
cleanup cannot control insertion. History stores final text and numeric metadata
using the existing schema. Lifetime word totals survive deletion and expiration.

Hyprland shortcuts, original-target paste, MPRIS, lock/suspend monitoring and
compositor reload recovery remain in Python. Portable mode retains optional XDG
GlobalShortcuts portal registration, manual recording/copy, and notifications.
`hud.py` alone imports GTK4/GI and provides native layer-shell anchoring, no keyboard
focus, empty input region, real energy feedback and terminal-state dwell. Helper
failure cancels capture. See migration.md for the upstream Wayland constraints.

The desktop tray is implemented in Tauri. Closing hides only if a tray was created
and a StatusNotifierWatcher is present. If that watcher disappears the main window
is shown again. Quit always asks for confirmation and backend shutdown enforces
fresh active-work checks. No global Rust shortcut registration competes with the
existing compositor/portal bindings.

Packaging keeps `/usr/bin/caelum` as the CLI/compatibility launcher, adds
`caelum-desktop` and `caelum-engine`, and vendors locked Python wheels under
`/opt/caelum/lib`. The distro Python ABI remains a package dependency; users never
install Python dependencies manually. Existing signed native-package updates and
XDG settings/keys/history paths remain valid.
