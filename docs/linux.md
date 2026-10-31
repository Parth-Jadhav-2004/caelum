# Linux installation and compatibility

Caelum 0.3 is a **cross-distro preview**, not a claim that every desktop has been
qualified. The native Hyprland path has been exercised on this development machine.
The portable backend is covered by automated integration tests; Ubuntu, Debian,
Fedora, and their GNOME/KDE sessions still need hardware acceptance testing.

## Download the package for your OS

The GitHub release contains x86-64 packages for Ubuntu 24.04 (Python 3.12),
Ubuntu 26.04 (Python 3.14), Debian 12 (Python 3.11), Debian 13 (Python 3.13),
Arch (Python 3.14), and Fedora 43 (Python 3.14). Choose your exact OS/version.
Packages declare their Python minor-version requirements and include locked
Python dependencies; GTK, PyGObject, Cairo, and PortAudio come from the OS.
The vendored dependencies do not replace distro Python modules.

Install downloaded packages with the native package manager:

```sh
sudo apt install ./caelum_0.3.1-1_ubuntu-24.04_amd64.deb
# Debian: select the debian-12 or debian-13 file instead.
sudo pacman -U ./caelum-0.3.1-1-x86_64.pkg.tar.zst
sudo dnf install ./caelum-0.3.1-1.fedora43.x86_64.rpm
```

Open **Caelum** from the app launcher, or run `caelum app`. First launch opens setup for provider/key entry, local microphone testing, shortcut selection, and an explicitly consented practice dictation. Reopen it from Settings → Open setup / Manage keys.
No credentials, autostart entry, recording service, or system shortcuts are
installed/enabled automatically. Configuration remains in `~/.config/caelum`;
history remains in `~/.local/share/caelum`. Uninstalling does not erase these files.
Verify the adjacent `.sha256` checksum before installing. The checksums are not
cryptographic release signatures. AUR submission is separate from publishing a
PKGBUILD; this project does not claim an AUR or Flathub listing.

## Desktop behavior

The default `backend = "auto"` selects native Hyprland when its session is present;
otherwise it selects the portable backend. You can set `[app] backend = "portable"`
to exercise the portable path on Hyprland or use an older Hyprland without Lua.
Restart the dictation service after changing backends.

**GNOME, KDE, XFCE and other GTK-capable Linux desktops, Wayland or X11:** start the
service, choose **Record**, then **Finish recording**. Completed text is saved
locally. Choose **Copy text** in Recent dictations or History, then paste in your
chosen application. This avoids restricted focus inspection and background
synthetic input. The service uses logind lock feedback and cancels on lock/suspend.
A desktop session with working logind and notification support is required.

Where `org.freedesktop.portal.GlobalShortcuts` is implemented, starting the service
requests a hold-to-record shortcut from your desktop. Accept/configure it in the
system dialog. A declined or unavailable portal leaves the Record buttons usable.
Modifier-only shortcuts need a letter/key on this backend. Restart the service to
change a portal shortcut; the system dialog may override the requested trigger.
Notifications show recording/processing states without a focus-taking overlay.

On desktops without that portal, create a custom shortcut in the desktop's
Keyboard settings with command **`caelum control toggle`**. Press once to start,
again to finish. `caelum control cancel` cancels, and `caelum control retry` retries
a failed request. Start the service before using these commands. Generic desktops
do not globally intercept Escape; use Cancel in Caelum or a custom cancel shortcut.

**Native Hyprland:** hold the configured chord, release to finalize. Target-addressed
paste and the click-through recording pill remain available. This needs Hyprland's
Lua API, `wl-copy`, and GTK4 layer shell. Omarchy is optional; other Hyprland
sessions use logind when the Omarchy lock helper is absent.

Run `caelum doctor` to see required checks and optional capabilities separately.
It never records or uploads audio. Optional portal availability is not a failure.

## Configuration and credentials

`caelum init` creates a config only when it does not already exist. Configure your
providers there. Manage provider keys in setup; packaged installs include secret-tool for the desktop keyring, with a disclosed private-file fallback if unavailable. Environment keys are still supported. The bundled
native-package launcher also loads `~/.config/caelum/environment` as a shell file;
use permissions `600`. Never put credentials in release packages or the repository.
Source checkouts use `scripts/run.sh` to load that same private file.

## Source installation

Python 3.11 or newer is required; use the distro Python for GI/Cairo compatibility.
Install uv using its official instructions, then install system prerequisites:

```sh
# Ubuntu 24.04+/Debian 12+
sudo apt install python3 python3-venv python3-gi python3-cairo gir1.2-gtk-4.0 libportaudio2 libnotify-bin libglib2.0-bin libsecret-tools wl-clipboard xclip
# Arch
sudo pacman -S python python-gobject python-cairo gtk4 portaudio libnotify glib2 libsecret wl-clipboard xclip
# Fedora
sudo dnf install python3 python3-gobject python3-cairo gobject-introspection gtk4 portaudio libnotify glib2 libsecret wl-clipboard xclip

./scripts/setup.sh
.venv/bin/caelum init
./scripts/run.sh app
```

Install your desktop's appropriate `xdg-desktop-portal` backend for optional global
shortcuts; older portal versions may not implement this interface. The base app
does not depend on Hyprland or gtk4-layer-shell. History-off delivery uses
`wl-copy` (`wl-clipboard`) on Wayland or `xclip` on X11. Install these clipboard
tools before using history-off dictation from a source checkout.

## Release process

Provision the pinned Ed25519 public key and protected release-environment secret
as described in [signed releases and updates](updates.md) before pushing a stable
`v<project version>` tag. CI tests Ubuntu 24.04/26.04, Debian 12/13, Arch, and
Fedora 43, builds and smoke-installs every target package, signs the update
manifest, uploads all assets to a draft, then publishes the complete stable
release after environment approval. Missing or mismatched keys stop publication.
Version and locked dependencies come from `pyproject.toml` and `uv.lock`.
`scripts/build_package.py TARGET` builds the same payload locally (uv + zstd;
RPM additionally needs rpmbuild). Settings → Updates handles signed downloads
and next-app-launch installation for official updater-enabled native packages.

The Arch source PKGBUILD in `packaging/arch` is a template until its source hash is
filled from the published source archive. Release automation produces a separate
ready-to-use PKGBUILD with the verified hash. It uses distro Python dependencies (python-sounddevice may require the AUR or Omarchy repository);
the prebuilt Arch package instead vendors locked dependencies.

Flatpak is intentionally not shipped in this preview: microphone routing,
background service lifetime, credentials, and shortcut permissions need a tested
sandbox implementation before a Flathub submission would be appropriate. Windows,
macOS, Ubuntu 22.04's stock Python 3.10, and non-logind sessions are not qualified.
