# Caelum 0.3.5

Caelum 0.3.5 fixes Bluetooth microphone selection and adds the product-page
waveform as the application logo.

- Use actual PipeWire/PulseAudio input sources instead of JACK playback monitors
  and application ports in the microphone selector. Save stable source names and
  continue supporting existing uniquely named microphone settings.
- Fix CMF Buds 2 and other microphones whose native sample rate differs from
  dictation's 16 kHz format. The audio server converts capture to 16 kHz mono;
  ALSA-only desktops retain PortAudio support.
- Use the same capture path for dictation, onboarding, and the local microphone
  test. Disconnected selected sources fail instead of silently recording a
  different input; identically named sources have distinct selector labels.
- Mark recording streams for communication so WirePlumber can switch Bluetooth
  earbuds into headset mode while recording and restore playback afterward.
  Desktops with automatic switching disabled still need manual selection of a
  hands-free/headset profile. Bluetooth headset mode may lower playback quality.
- Add the waveform logo to desktop launchers, app windows, and the system tray,
  including regular and symbolic icons in native packages.

Packages are available for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43.
They include the PulseAudio-compatible client tools needed for microphone
routing; these also work with PipeWire. Downloads contain four packages,
`update.json`, and `update.json.sig`. Signing and package verification are
unchanged. Configuration, keys, and history are preserved when upgrading.

The microphone fix was checked locally with CMF Buds 2, including headset-profile
switching and restoration. Test audio stayed in memory and was discarded, never
saved or uploaded. Broader Bluetooth hardware compatibility is not guaranteed.
