# Caelum 0.3.6

Caelum 0.3.6 fixes the waveform logo in application switchers and desktop launchers.

- Install `io.caelum.Dictation.desktop`, matching the GTK application's existing
  Wayland app ID, and declare the same `StartupWMClass` for desktop association.
  The previous `caelum.desktop` filename did not match the running window's ID.
- Migrate older Caelum-generated user launchers when the app opens. Their generic
  microphone icon no longer overrides the waveform. Preserve the existing launch
  command, configuration path, and extra settings; leave custom launchers alone.
- Keep the legacy generated launcher usable, but hide its menu entry to prevent
  duplicates. Preserve any existing canonical user entry and custom icon choice.
- Use one desktop-entry template across native packages and add package smoke
  checks for app-ID, window-class, and icon association on every supported distro.

The Bluetooth microphone fixes from 0.3.5 remain included. Packages are available
for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43, with signed update metadata.
Configuration, credentials, and history are preserved. After updating, fully quit
and reopen Caelum so the running app and desktop switcher use the updated identity.
