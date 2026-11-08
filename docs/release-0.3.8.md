# Caelum 0.3.8

Caelum 0.3.8 adds a choice of recording shortcut behavior and increases the
default recording limit to three minutes.

- Choose **Hold to talk** or **Press to toggle** in Settings. Toggle mode starts
  recording on the first shortcut press and finishes it on the next; releasing
  the shortcut keeps recording. Hold-to-talk remains the default.
- Save the recording mode automatically and apply changes while the service is
  idle. Hyprland and desktop portal shortcuts support both modes. Manual Record
  controls continue to toggle recording.
- Increase the default recording limit from 120 to 180 seconds. Existing
  configuration values are preserved; set `app.max_recording_seconds = 180` in
  `~/.config/caelum/config.toml` to raise an existing 120-second cap. The supported
  upper bound remains 600 seconds.
- Fall back to the built-in microphone when a selected Bluetooth input
  disconnects, including the fallback change already on main since 0.3.7.

Packages are built for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43, with
signed update metadata. Configuration, credentials, and history are preserved
when upgrading. Restart Caelum after installation to use the new Settings
selector.
