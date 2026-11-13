# Caelum 0.4.0

The main application moves from GTK4/PyGObject to Tauri 2, React, TypeScript,
shadcn/ui and Tailwind. Home, statistics, history, settings and consented setup
share a dark-first design system, with optional light/system appearance.

Python capture, transcription, cleanup, retry handling, SQLite history, TOML
preferences, credentials, MPRIS and native/portal shortcuts retain their existing
implementations and data paths. A managed JSON-lines sidecar connects the new UI.
The native GTK4 layer-shell recording overlay remains an isolated helper because
ordinary Tauri Wayland windows cannot provide its placement/input contract.

Release packaging includes the native executable and locked Python dependencies
for Ubuntu, Debian, Fedora and Arch. Full physical desktop/provider qualification
and clean-install checks on every target are documented in docs/acceptance.md.
On NVIDIA Wayland sessions, Caelum automatically applies the scoped WebKitGTK
explicit-sync workaround to prevent the startup crash reported as GDK Error 71
("Missing acquire timeline"). Explicit user overrides are respected, and the
isolated native recording overlay retains its normal graphics environment.
Startup was verified on the affected hybrid Intel/NVIDIA Hyprland host. The
libayatana-appindicator deprecation warning is nonfatal and may still appear.

The headless WebKit smoke test uses a per-process DMA-BUF renderer workaround.
Prolonged interactive use, GPU resize behavior, real microphone/provider flows,
and clean installation on all distribution targets remain qualification tasks;
see docs/verification.md and docs/acceptance.md for the tested scope.
