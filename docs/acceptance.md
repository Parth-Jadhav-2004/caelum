# Tauri refactor acceptance

Passing automated tests and compiling the app do not certify physical desktop
behavior. Check the items below on the release host before publishing.

## Automated checks

```sh
npm ci
npm run check
uv sync --locked --extra dev --python /usr/bin/python3
uv run ruff check python tests scripts
uv run pytest -q
uv run python scripts/generate-contracts.py
bash scripts/check-workflows.sh
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml -- -D warnings
npm run tauri build -- --no-bundle
```

The Python suite covers capture bounds, real WAV contracts, provider errors and
cleanup fallback, chunk seams, session cancellation/retry, media controls,
configuration/credential storage, history retention/export/lifetime totals,
settings reload rollback, signed updates, sidecar protocol/EOF/process termination,
consent gates, and failed-save preservation. React tests exercise recording,
retry protection, device preference preservation, waveform data, shortcut capture,
and destructive-history confirmation. The retired GTK main-window tests were
removed with their widgets; four real Hyprland tests remain opt-in.

## Release-host checks (not established by mocks)

- [ ] First run and resumed key management, separate provider keys, keyring unlock
  and owner-only unencrypted fallback disclosure; provider failures never reveal keys.
- [ ] Real local microphone test and consented practice; no audio written to disk.
- [ ] USB/Bluetooth/default-device capture, missing sources, unplug/reconnect.
- [ ] Actual Groq transcription and optional cleanup, history saving on/off,
  raw fallback, empty speech, quota/offline retry, expiry and discard.
- [ ] Physical hold/toggle hotkey, both modifier orders, Escape and conflicts;
  portable portal approval/rejection and manual Record/Finish fallback.
- [ ] Main window Home/Statistics/History/Settings, search/copy/export/delete,
  autosave errors, sidebar, dark/light/system, keyboard-only and screen reader.
- [ ] Native overlay appears on the intended output, stays click-through,
  preserves focus, and dismisses correctly; scale 100–200%, mixed monitors.
- [ ] Portable notification feedback and manual-copy workflow on GNOME/KDE/X11.
- [ ] MPRIS pauses only playing media and resumes safely after completion/cancel.
- [ ] Lock/suspend cancels capture; no late insertion after unlock.
- [ ] Closing hides only with a working tray; watcher loss reopens the window;
  tray open/pause/resume/quit, active-work quit confirmation, second-instance activation.
- [ ] Parent/sidecar/HUD failure stops recording; no orphan capture/hotkey bindings.
- [ ] App-launcher discovery and next-login autostart with provider credentials.
- [ ] Install each target-native .deb/.rpm/Arch package in a clean desktop image,
  launch without pip, upgrade existing 0.3.9 data, signed update/restart and rejection
  of corrupted/expired/wrong-target packages.

Native tests require an interactive Omarchy login and no running daemon:
`CAELUM_NATIVE_TESTS=1 uv run pytest tests/test_native.py -q`. They can temporarily
focus their disposable test window and preserve a text clipboard in memory;
non-text clipboard formats are outside the fixture's preservation guarantee.
The normal test suite isolates XDG config/data/runtime directories and does not
use real provider credentials or microphone capture.

## Local refactor verification

See docs/verification.md for the checks actually run for this working tree. The
four opt-in native tests are deliberately not inferred from the headless window
smoke test. Smoke scripts for extracted packages are available:

```sh
/usr/bin/python3 scripts/smoke_package.py /tmp/extracted-package
python3 scripts/smoke_desktop.py /tmp/extracted-package --screenshot /tmp/caelum-setup.png
python3 scripts/smoke_desktop.py /tmp/extracted-package --completed-setup --screenshot /tmp/caelum-home.png
```

## Candidate promotion

Follow [releasing.md](releasing.md). Package checks include a native WebKit/Xvfb
launch that waits for real React/bootstrap readiness, plus per-target provenance.
The automated gate does not replace the physical/session checklist above. Record
the candidate run/SHA and manual results before attesting qualification in the
promotion workflow. Published tags/assets cannot be replaced by that workflow.

### Portable first paste — record once per real session

Use a disposable account on Ubuntu GNOME Wayland, KDE Plasma Wayland, and one X11 desktop. Start from the public RC release, check SHA256SUMS and package version, and write down candidate run/attempt/SHA, package hash, distro, desktop/session version, audio device, tester/date and outcome. Deny the portal shortcut first, then grant it if supported. Choose Record → Finish recording → Copy from history → paste into an editor; with history disabled, paste directly and verify no new history row. Repeat for both engines. Local: provision the model, disconnect networking, and complete practice without keys. Online: tester explicitly consents and uses their own key; test cleanup off/on. Never attach credentials, audio or private transcripts.

Before recording, agree on the synthetic phrase **“Start Caelum test number forty two and finish here.”** Require both boundary words, the name and number (digits or words), no missing content, and no invented words on silence. Report counts/pass/fail rather than retaining private speech. Repeat on a built-in and USB/Bluetooth mic, unplug/reconnect, switch away from a wrong input and retry. Complete the lifecycle list above, keyboard-only, screen reader and 200% scaling. Hyprland needs its own hold/release, HUD and original-window paste test before showing it in launch media.

For upgrades, seed disposable stable 0.4.2 settings and history, snapshot the VM, exercise signature/hash rejection and a correctly signed staged update through polkit, restart and verify preserved settings/history. Rehearse restoring the snapshot. Use a controlled staging trust setup for rehearsal, never the production signing secret on a test machine, and record which trust path was tested. A manual RC package install is not a signed updater test. Leave main gated if an authorized signed rehearsal is unavailable.
