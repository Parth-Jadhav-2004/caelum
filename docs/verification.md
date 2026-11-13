# Refactor verification — 13 November 2026

Caelum 0.4.0 replaces the main GTK UI while preserving the Python engine and XDG
data formats. These results describe local automated verification, not certification
of a real microphone, provider account, or every supported desktop.

- pytest: **284 passed, 4 skipped**. The skipped tests require an interactive
  Omarchy/Hyprland session. Retired GTK-main-window tests were removed with those
  widgets; backend regressions remain, plus sidecar and complete mocked
  capture/HTTP transcription/cleanup/history/export/deletion coverage.
- Vitest: **13 passed** across recording/retry/device/waveform/history confirmation,
  staged-key consent/cancellation, onboarding gates, sidebar persistence and
  startup-without-recording checks.
- TypeScript strict compilation, ESLint and Vite production build passed.
- Ruff and Rust formatting/Clippy with warnings denied passed.
- npm audit: **zero vulnerabilities**, including development dependencies.
- Repository and package-stage privacy scans passed.
- Tauri optimized executable and an Arch native package built locally, including
  the Python wheel payload locked by uv.lock.
- Extracted package smoke test passed: all launchers present, versioned IPC,
  empty isolated history, status, EOF cleanup, and vendored imports with Python
  system site packages disabled. The Python main-window path does not load GTK.
- Native WebKit window smoke testing used isolated Xvfb and D-Bus. The initial
  blank software-rendered window was resolved for the test with the per-process
  WEBKIT_DISABLE_DMABUF_RENDERER=1 workaround documented in docs/linux.md.
  Both the packaged dark first-run Setup and Home screens were captured and
  visually inspected using the final 0.4.0 package.
- 21st UI review reported zero findings. Official shadcn primitives were used;
  decorative 21st search results were not included.

## Remaining qualification

Debian/Ubuntu/Fedora package build-and-install jobs are configured in CI but were
not run locally: Docker is installed here, but access to its daemon socket was
denied. The local package was extracted/smoke-tested without installing it over
the user's current application. No live microphone sample or credential-authenticated
provider request was made. Physical shortcuts, tray watcher transitions, MPRIS,
lock/suspend, native Wayland overlay behavior, GPU/driver combinations, and
cross-distribution installation still require the acceptance checks in
[acceptance.md](acceptance.md).

The native layer-shell HUD still requires GTK4, PyGObject/Cairo and
GTK4-layer-shell. This dependency is isolated from the Tauri main window.
Portable desktops retain notifications/manual paste, rather than a universal
floating-overlay claim. Standalone Tauri bundles omit the vendored Python tree;
use scripts/build_package.py for distributable packages. Vite reports a ~626 kB
main JavaScript chunk before gzip (~196 kB compressed); feature screens are lazy
loaded, and the warning is informational rather than a failed check.

## NVIDIA Wayland startup follow-up

A real-session startup probe reproduced GDK Error 71 on this hybrid Intel/NVIDIA
Hyprland host. WAYLAND_DEBUG identified
`wp_linux_drm_syncobj_surface_v1: Missing acquire timeline`; the unmodified build
exited with status 1. Disabling NVIDIA explicit sync kept the app alive. The new
startup policy automatically applies that workaround only to NVIDIA Wayland,
respects explicit user values/X11 preference, and removes only its automatic
setting from the Python sidecar environment.

Both automatic-policy and explicit-user-override builds remained alive during
8-second real Wayland probes without the protocol error. The child environment
probe confirmed the automatic flag was absent from the sidecar and an explicit
user flag was preserved. Three new Rust policy tests and Clippy passed; the
optimized build and Arch package were rebuilt. These startup probes do not replace
recording, resize, suspend, or other long-running interactive acceptance checks.
