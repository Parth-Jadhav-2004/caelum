# Linux prerequisites

Build inside the target distro; do not reuse an Arch-linked executable on Debian.

- Arch/Omarchy: `base-devel rust nodejs npm uv webkit2gtk-4.1 libappindicator-gtk3
  librsvg patchelf portaudio libpulse libnotify libsecret wl-clipboard xclip
  python-gobject python-cairo gtk4 gtk4-layer-shell zstd`.
- Debian/Ubuntu: `build-essential pkg-config libwebkit2gtk-4.1-dev
  libayatana-appindicator3-dev librsvg2-dev patchelf libportaudio2 pulseaudio-utils
  libnotify-bin libglib2.0-bin libsecret-tools wl-clipboard xclip python3-venv`.
  Optional native HUD: `python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-4.0`
  and gtk4-layer-shell (not shipped by all supported releases).
- Fedora: `gcc gcc-c++ make pkgconf-pkg-config webkit2gtk4.1-devel
  libappindicator-gtk3-devel librsvg2-devel patchelf portaudio pulseaudio-utils
  libnotify libsecret python3-gobject python3-cairo gtk4 rpm-build`.

Install Node 24+, current stable Rust, and uv for source builds. Native packages
install the required runtime libraries automatically. gtk4-layer-shell is optional
on portable desktops and required for native Hyprland mode; `caelum doctor`
reports missing native integration. Use `app.backend = "portable"` explicitly
when layer-shell/native Lua integration is unavailable.

`caelum doctor`, `caelum devices`, `caelum models stt`, and `caelum control status`
remain available. A Wayland desktop login needs a working XDG runtime directory,
session D-Bus, login1 lock feedback, microphone access, and the appropriate portal
for global shortcuts. If shortcut permission is declined, use Record/Finish.
Caelum does not install broad keyboard hooks or bypass compositor permissions.

On Hyprland the existing bindings are installed dynamically and removed by exact
handle; no user compositor config is rewritten. Native insertion targets the
original app and falls back to clipboard if focus identity changes. Lock/suspend
signals cancel capture; lock feedback failures fail closed. The native HUD does
not activate or steal keyboard focus. Portable mode uses notifications and saved
history/manual copy. This distinction is intentional.

Tauri uses WebKitGTK on Linux. GPU/driver rendering issues require testing on the
deployment host: https://v2.tauri.app/develop/debug/linux-graphics/ . Do not force
XWayland globally merely to make a layer-shell surface appear.

For software-rendered/Xvfb environments, this refactor's native smoke test required
`WEBKIT_DISABLE_DMABUF_RENDERER=1` to avoid a blank WebView. If the same symptom
occurs with a particular GPU/driver, try that environment variable for the Caelum
process only. It is not set globally or forced on normal desktop sessions.

On NVIDIA Wayland (including hybrid Intel/NVIDIA laptops), Caelum now sets
`__NV_DISABLE_EXPLICIT_SYNC=1` before creating its main WebView. This addresses
Hyprland's `wp_linux_drm_syncobj_surface_v1: Missing acquire timeline`, surfaced
by GDK as `Error 71 (Protocol error)`. It retains the accelerated rendering path.
The workaround applies only when the NVIDIA kernel module is loaded, Wayland is
available, and X11 is not explicitly preferred. Existing values are respected:
`__NV_DISABLE_EXPLICIT_SYNC=0` opts out. An automatically applied value is removed
from the Python sidecar's environment so the native recording overlay is unchanged.
The `libayatana-appindicator is deprecated` message is a separate nonfatal warning
from Tauri's tray dependency; it does not explain the Wayland protocol failure.
