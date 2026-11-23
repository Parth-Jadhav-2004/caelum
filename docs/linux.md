# Linux prerequisites

## First-run help

- **No microphone or silence:** select the input in Settings → General. Check the desktop input meter and mute switch; reconnect USB/Bluetooth and wait for device discovery. Use the local microphone test before trying transcription. `caelum devices` lists the inputs visible to the app.
- **Shortcut denied or unavailable:** New setups use **Super+Alt+V** on GNOME, KDE and other portal desktops, or **Ctrl+Super** on native Hyprland. If the portal denies the shortcut, choose **Record** on Home, then **Finish recording**. If you change the shortcut, use **Restart Caelum** in Settings to activate the pending binding.
- **Pasting the result:** If Caelum shows **Copied**, paste in your editor. You can also copy a saved transcript from History. With history and automatic clipboard copying both off, choose **Copy transcript** on Home before recording again. Check `wl-copy` on Wayland or `xclip` on X11 if clipboard delivery fails.
- **No tray icon:** some desktops have no tray watcher. Keep the window open while dictating; reopen Caelum from the app launcher.
- **Blank window:** quit Caelum, then try `WEBKIT_DISABLE_DMABUF_RENDERER=1 caelum-desktop` for this launch only. See the driver notes below.
- **Local model unavailable:** choose a compatible downloaded model in Settings → Transcription. On x86-64, local inference needs AVX2 and sufficient available RAM. A model download needs network and disk space; local dictation does not require an online fallback.
- **Uninstall:** quit the app, then `sudo apt remove caelum`, `sudo dnf remove caelum`, or `sudo pacman -R caelum`, depending on your package. Personal settings and fallback credentials remain in `~/.config/caelum`; history, models and pending downloads remain in `~/.local/share/caelum` (or the corresponding XDG directories). To remove saved keys, use the app before uninstalling; a keyring entry, clipboard history, exports and backups are independent of these directories.

## Building and desktop integration

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
original app. With automatic copy off (the default), both native and portable
Linux modes try to insert at the caret in the same focused, editable AT-SPI
field. Click into the field before pressing the shortcut. Password fields,
terminals, active selections, apps that do not expose editable text, and changed
focus fall back to **Copy transcript** on Home. The clipboard is never used for
this direct insertion. If you enable automatic copy, Hyprland uses clipboard
paste and portable desktops retain their save/copy workflow. Lock/suspend signals
cancel capture; lock feedback failures fail closed.

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
