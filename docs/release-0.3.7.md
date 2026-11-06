# Caelum 0.3.7

Caelum 0.3.7 detects stalled microphone capture and makes the local microphone
test report a clear result.

- Detect PipeWire/PulseAudio streams that stop delivering audio for two seconds,
  instead of waiting indefinitely while Bluetooth still reports Connected.
  Report an actionable reconnect message and preserve capture-error details.
- Handle partial PCM pipe reads without falsely reporting a disconnected device.
  Normal microphone silence continues to be captured rather than treated as a
  stalled transport.
- Show success or no-speech feedback after Settings → Test mic, and restore the
  test button after success or failure. The test remains local-only; it never
  saves or uploads audio.
- Discard interrupted setup/test samples, including errors detected while the
  stream is stopping, instead of treating partial capture as a successful test.
- Document a reversible WirePlumber workaround for affected Linux Bluetooth
  voice transports: disabling mSBC negotiation can avoid repeated SCO failures,
  at the cost of lower Bluetooth microphone fidelity. Normal A2DP music codecs
  remain enabled. This is an optional machine-level workaround, not a setting
  automatically changed by the app or its packages.

Repeated local capture checks with CMF Buds 2 passed after applying that
machine-level workaround, including checks using the installed 0.3.6 package.
This release adds app safeguards and troubleshooting guidance; it does not
claim to fix the underlying kernel/PipeWire Bluetooth bug for every headset.

Packages are available for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43,
with signed update metadata. The waveform app logo and desktop association
fixes from 0.3.6 remain included. Configuration, credentials, and history are
preserved when upgrading. Restart Caelum after installation.
