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

## Reliability and CI/CD adoption — 14 November 2026

The following results apply to the local changes after the theme update:

- **331 pytest tests passed, 4 physical/session tests skipped**. Includes real
  JSONL processes, partial settings preservation, typed-error sanitization,
  guarded shutdown, provenance/checksum/expiry verification, interrupted draft
  publication, immutable assets/tags, and rollback prevention. Release tests use
  temporary signing keys and an in-memory GitHub implementation, not a real release.
- **25 frontend tests passed** under the pinned Node 24.22.3 toolchain, including
  runtime result validation, late initial status snapshots, disconnect handling,
  and confirmed restart after save failure. Its strict TypeScript/Vite build passed.
- **9 Rust tests passed**, including stalled pipes, bounded response framing,
  admission control, cancellation cleanup and forced child reaping. Formatting
  and Clippy with warnings denied passed under the pinned Rust 1.99.1 toolchain.
- ESLint, strict TypeScript/Vite production build, Ruff, generated-contract
  consistency, privacy scanning and Actionlint 1.7.12 passed. The existing entry
  chunk-size warning remains informational; it is not hidden or treated as a
  performance improvement.
- The current optimized executable and full locked-wheel Arch package built
  locally. The extracted package passed the native WebKit/Xvfb startup probe
  after actual lazy-screen/bootstrap readiness; the Setup screenshot was visually
  inspected. Nothing was installed over the user's application.
- The CI/release scripts implement a five-distro installed-package matrix and
  verified artifact promotion. These new GitHub jobs and live publication were
  **not executed** from this unpushed working tree. Branch protection and release
  environment review policy remain repository-administrator settings.

See [releasing.md](releasing.md) and [ipc.md](ipc.md) for current procedures and
limits. This work does not establish physical microphone/provider, Wayland,
tray/MPRIS, or every-distro qualification, and does not choose Caelum's license.

## Public-readiness follow-up

The latest scoped results, physical-test limitations, licensing, Python support,
and measured performance are in [qualification-0.4.1.md](qualification-0.4.1.md).
They supersede the earlier remaining-license and single-key-rotation statements.
