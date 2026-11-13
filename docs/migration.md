# Tauri migration

The baseline is 0.3.9 and docs/ui-functionality-reference.md. The marketing site
is independent and is not migrated. No database or credential migration is needed:
XDG paths, SQLite schema, owner-only credentials, and TOML fields are preserved.

## Mapping

- desktop.py GTK widgets, desktop.css → src/features (Home, Statistics, History,
  Settings), shadcn primitives, Tailwind tokens, Zustand navigation.
- desktop.py non-widget operations → python/caelum/desktop_services.py.
- onboarding_ui.py → src/features/setup.tsx; onboarding.py remains the bounded
  local-test/practice/provider validation implementation.
- Gio tray → Tauri tray with open/pause/resume/quit and watcher availability checks.
- audio/providers/quality/segmenter/orchestrator/history/config/credentials/media →
  python/caelum, preserving the working implementations.
- service/control socket → unchanged UID-checked Unix socket, accessed by sidecar.
- python/caelum/sidecar.py → version 1 JSON-lines request/response/event protocol,
  managed by Rust. No shell or provider credentials exposed to the webview.
- hud.py → isolated native GTK4 layer-shell helper. It is not a second main UI.
- release packaging → Tauri executable plus locked, vendored Python dependencies;
  system Python/PortAudio/WebKitGTK remain declared distro dependencies.

## Wayland decision

Tauri's ordinary setPosition is unsupported on Linux Wayland:
https://docs.rs/tauri-runtime-wry/latest/tauri_runtime_wry/struct.Window.html
Layer-shell requires initialization before a surface is mapped:
https://github.com/tauri-apps/tauri/issues/15913
https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md
The native HUD retains output anchoring, click-through input, no keyboard focus,
Escape handling, lock safety, bounded energy feedback, and helper supervision.
Portable desktops keep notifications/manual paste as before. GNOME does not
support this layer-shell protocol. No claim of a universal floating overlay.

## Verification scope

Legacy GTK main-window interaction tests are retired alongside those widgets;
UI behavior is covered by React tests and sidecar integration tests. Native HUD,
provider, capture, storage, media, compositor, and service tests remain. Hardware,
real provider credentials, desktop portal permissions, tray watcher transitions,
lock/suspend, and package installation need the explicit host acceptance checks
in docs/acceptance.md. Automated tests cannot establish those properties.

## Remaining acceptance and workflow differences

The new settings use standard labeled controls and a shadcn Tabs advanced section
instead of GTK sentence controls. Autosave remains debounced with saved/reload
failure status. Quit and stop use conservative confirmation dialogs, including
when active state cannot be read. Key validation and audio tests are cancellable;
provider keys are staged until verification. Update installation explicitly
restarts the native process after the verified package is applied.

The distributable path is scripts/build_package.py, which packages Tauri and the
vendored Python library together. Bare `tauri build` bundles do not include that
full library tree and are not release artifacts. The current targets are x86_64
Ubuntu 24.04/26.04, Debian 12, Fedora 43, and Arch/Omarchy. No arm64 packages are
claimed. Full cross-distribution installation and physical desktop acceptance
remain release gates, not results inferred from a successful local build.
