# Caelum 0.3.0

This Linux preview adds guided setup and signed native updates.

- Resumable first-launch setup with provider validation, a local microphone test,
  shortcut selection, and an explicitly consented practice dictation.
- In-app credential management with desktop-keyring storage and a disclosed,
  owner-only file fallback when the keyring is unavailable.
- Update checks, download consent, and signed release metadata pinned to the
  verification key included in official native packages.
- Verified package installation on the next desktop launch through polkit.
  Recording, processing, and retryable audio defer installation rather than
  discarding a dictation.
- Arch package update compatibility for Omarchy with matching system Python.

## Installing

Existing 0.2.0 users must install this first updater-enabled release manually.
Choose the package matching your distribution, architecture, and Python version.
Later stable releases can be downloaded through Settings → Updates.

The public update verification key ships in this release. Keep the initial
installation source trusted; a checksum alone does not authenticate its publisher.
Configuration, keys, and history remain outside the package and are preserved.

## Preview limitations

Native desktop/polkit behavior still requires hardware acceptance on each target
distribution. Source, pip, and AUR source installations continue using their
original installation method rather than the in-app native updater. Flatpak,
Windows, macOS, and ARM packages are not included.
