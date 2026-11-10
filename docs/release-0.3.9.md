# Caelum 0.3.9

Caelum 0.3.9 automatically pauses playing media while you dictate and resumes
it when microphone capture ends.

- Pause playing music and other media before starting microphone capture using
  Linux MPRIS media controls. Compatible music apps and browsers work without
  an additional dependency or configuration.
- Resume the players Caelum paused immediately after recording stops, without
  waiting for transcription. Both hold-to-talk and toggle recording are supported.
- Restore playback after cancellation, the recording time limit, microphone
  startup failure, capture errors, and service shutdown.
- Leave already-paused media alone. Skip resuming a player if it has stopped,
  already resumed, changed tracks, or been replaced by a new player process.
- Keep media controls best-effort with bounded waits: unavailable players or
  a missing session bus do not prevent dictation.

Packages are built for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43, with
signed update metadata. Configuration, credentials, and history are preserved
when upgrading. Restart Caelum after installation to enable this behavior.
