# Caelum 0.4.1 qualification — 14 November 2026

## Implemented and checked

- MIT licensing approved by the owner. Own license, pinned third-party notices,
  dependency inventory and unmodified MPL crate source archives ship in packages.
  Public notice provenance includes the upstream omission in react-remove-scroll-bar's
  npm tarball; no dependency copyright was invented.
- Real release-era TOML and SQLite fixtures from GTK-era **0.3.9** and Tauri
  **0.4.0** preserve preferences, hidden settings, historical rows, schema, and
  lifetime totals. Interrupted atomic settings writes preserve the old file.
- Installed-key trust supports overlap, activation/expiry and revocation. Dual
  signatures preserve the original 64-byte signature for older clients. A frozen
  0.4.0 verifier, rotated network/staging path and privileged verification tests
  pass with temporary keys. No production key was generated or rotated.
- Axe semantic checks pass on Dashboard, Statistics, History, Settings and Setup.
  Nested main landmarks, a waveform's prohibited generic label, command-dialog
  labels outside their portal, and lost confirmation-return focus were corrected.
  Keyboard tests cover theme selection, least-destructive initial focus, Escape,
  and focus return. A skip link and current-page navigation semantics were added.
- The contrast audit passes **308 text-token pairs** across seven palettes,
  two appearances and ordinary/high-contrast modes. All audited pairs meet
  4.5:1; upstream palette values needed no changes. This is a token audit, not
  a claim that every composited pixel or disabled/opacity state is WCAG-certified.
- Native WebKit screenshots were inspected at 640×600 and GDK scale 2, in isolated
  Xvfb/D-Bus sessions. Content scrolls vertically at narrow/short sizes. This
  checks those rendered states, not real Wayland GPU resize or a screen reader.
- A live Hyprland HUD protocol/geometry/focus/click-through/dismiss test passed.
  Binding registration skipped because another Caelum service owned shortcuts;
  its bindings were preserved. Other physical native cases were not run.
- Two isolated real D-Bus/MPRIS round-trip tests pass: only a playing player is
  paused, and only the original unchanged track is resumed. This does not certify
  every installed media player.
- Current Python support is explicitly 3.11–3.14. Python 3.15 removes the typing
  API used by the retained dbus-next release. `.python-version` pins development
  to 3.14 and native packages retain their target Python ABI constraints.

## Candidate pipeline

The initial candidate at `b46d62d` passed both checks jobs and package install,
IPC, simulated audio, GUI readiness, and complete artifact assembly on all five
Linux targets:

https://github.com/Parth-Jadhav-2004/caelum/actions/runs/43565310899

Subsequent qualification changes require a new candidate; the final run link and
source SHA are recorded in GitHub Actions and its `candidate.json`, and reported
with delivery. No stable 0.4.1 release has been published or manually certified.
The existing release environment retains owner approval; `main` was added as an
allowed deployment branch for the promotion workflow.

## Performance evidence

Raw measurements and sampling scope are in [qualification-0.4.1.json](qualification-0.4.1.json).
Three sequential warm, fresh-XDG Setup launches were measured per build on one
Omarchy host using X11/software rendering. These are not cold starts or a
representative fleet sample.

Baseline median readiness was **802.31ms**; the split build measured **802.94ms**.
Median proportional memory was **273.36MiB** and **274.01MiB** respectively, with
all seven Tauri/descendant processes covered. These small differences do not
establish a startup or memory improvement. Aggregate RSS double-counts shared
pages; PSS is reported for the memory comparison.

The application entry is **94,278 bytes**, the largest JS chunk **218,754 bytes**,
and the initial static dependency graph **204,601 bytes gzip**. Splitting React,
Motion, UI, and data code removes the oversized single chunk and makes their
cache boundaries explicit. Total initial code still loads; entry shrinkage is
not a bandwidth or latency claim. CI enforces a 120KiB entry, 350KiB largest
chunk, and 230KiB compressed initial-static-graph budget without raising Vite's
warning threshold.

## Physical audio result

The owner explicitly consented to two five-second Groq tests. Capture and the
configured Groq Whisper request completed for both the saved Bluetooth input
and a temporary built-in override; no saved setting was changed. Audio remained
in memory and was not retained on disk. API keys and recognized text were not
printed or stored in the report.

Neither returned the complete supplied phrase: three words for the Bluetooth
sample and six for the built-in sample, versus nine expected. The cause was not
established. The owner chose to leave exact-phrase accuracy unverified rather
than perform another recording. These are transport/capture exercises, **not a
passed accuracy acceptance test**. Cleanup, text insertion and real-history
persistence were not exercised by those standalone physical sample commands.

## Remaining manual gates

Do not set the promotion workflow's desktop-qualified attestation until its
actual acceptance scope is recorded. Still open: controlled phrase accuracy,
real hold/toggle presses, every tray host/background transition, real player
behavior, lock/suspend/resume, mixed-monitor scaling/placement, GPU resizing,
USB/Bluetooth removal/reconnect, native screen-reader use, and provider cleanup
in a real user dictation. Existing automated mocks cover many failure paths but
do not turn these into passed physical tests.

For downgrade recovery, back up configuration/history first. SQLite's tested
schema remains compatible, but old configurations reject unknown options: remove
`desktop.color_theme` from a **copy** before running 0.4.0/0.3.9 against that copy.
Do not blindly replace a new configuration or point the updater backwards.
