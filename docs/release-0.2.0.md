Caelum 0.2.0 is the first **Linux portability preview**.

- A portable backend adds Record / Finish recording controls on GNOME, KDE, XFCE,
  and other GTK4 desktops, on Wayland or X11. Completed text is saved locally;
  use Copy text and paste into your chosen application.
- Standard GlobalShortcuts portal integration provides hold-to-record where the
  desktop implements it. If unavailable or declined, use app controls or a custom
  desktop shortcut running `caelum control toggle`.
- Native Hyprland recording, addressed paste, and the click-through recording pill
  remain available. Omarchy is no longer required for lock-state feedback.
- The black interface includes a collapsible sidebar and recent-dictation Copy actions.
- Native x86-64 packages are built for Ubuntu 24.04/26.04, Debian 12/13, Arch with
  Python 3.14, and Fedora 43. Choose the exact OS/version file. Python dependencies
  are locked and bundled; system GTK/audio libraries are installed by the package manager.

**Scope:** this is a prerelease. Automated distro tests and package installation
checks accompany the build, but GNOME/KDE hardware acceptance testing is still
pending. Generic desktops use manual copy, not automatic paste. Portal support
varies by desktop/version. Flatpak/Flathub, AUR publication, ARM packages, Windows,
and macOS are not part of this release. No provider credentials are included.

Install `.deb` with `sudo apt install ./FILE.deb`, Arch packages with
`sudo pacman -U ./FILE.pkg.tar.zst`, and RPM with `sudo dnf install ./FILE.rpm`.
Run `caelum app`, configure provider credentials, and start the service.
Checksums are provided alongside packages; these are not release signatures.
See [Linux installation and compatibility](https://github.com/Parth-Jadhav-2004/caelum/blob/v0.2.0/docs/linux.md).
