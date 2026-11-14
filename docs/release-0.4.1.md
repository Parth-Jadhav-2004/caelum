# Caelum 0.4.1 release candidate 1

- **Theme selection.** Choose T3 Code, T3 Chat, Grove, Ocean, Ember, Iris, or Caelum mint in Settings.
- **Engine recovery.** Requests have bounded deadlines, validated responses, and explicit recovery without replaying recordings.
- **Release verification.** Native packages pass installation, IPC, simulated-audio and GUI startup checks before promotion.
- **Accessibility.** Improve landmarks, confirmation focus, keyboard navigation, and theme contrast checks.
- **Update trust.** Support overlapping keys and dual signatures while retaining older updater compatibility.
- **MIT license.** Project licensing and third-party notices are included in distribution packages.

## Packages and upgrades

Candidate targets are Arch x86_64, Debian 12, Ubuntu 24.04/26.04, and Fedora 43.
Packages vendor Python dependencies and retain their system Python/native library
requirements. Configuration and SQLite data paths remain unchanged.

## Known limitations and qualification

This is a prerelease for testing, published as `v0.4.1-rc.1`; package versions
are `0.4.1`. It is excluded from the stable update feed. The candidate workflow
and desktop acceptance results must be reviewed before stable publication; see
[qualification](https://github.com/Parth-Jadhav-2004/caelum/blob/v0.4.1-rc.1/docs/qualification-0.4.1.md).
Physical capture and Groq transport were exercised, but phrase accuracy remains unverified. Native Wayland overlays,
physical shortcuts, provider workflows, scaling and suspend behavior require the
qualification record in docs/acceptance.md. GTK4 remains isolated to the native HUD.

## Changelog

https://github.com/Parth-Jadhav-2004/caelum/compare/v0.4.0...v0.4.1-rc.1
