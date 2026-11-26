# Changelog

Release notes, newest first.

## 0.5.4

- On Hyprland, dictation can now type directly into apps that lack an accessible text field, including Chromium and single-line terminal prompts, while keeping your clipboard intact.
- Direct typing checks the original window before each keystroke. When Caelum detects a protected field, or a transcript contains tabs or multiple lines for a terminal, the transcript stays available through **Copy transcript**.

## 0.5.3

- The **Styles** page lets you choose an online writing style and preview an example.
- Local transcription formats clearly dictated English lists with built-in rules and needs only the speech model. It keeps spoken fractions within their item and leaves lists with more than ten consecutive ordinal markers as dictated.
- Automatic clipboard copying is off by default. When copying is off, the dictation shortcut inserts at the caret in supported Linux text fields and keeps your clipboard intact. If insertion is unavailable, use **Copy transcript**. Existing explicit clipboard preferences are preserved.
- Removed the sidebar status and pause card and the accent picker in **Appearance**.

## 0.5.2

Changes since stable v0.5.0, including the v0.5.1 testing releases.

### Dictation and local models

- Light and Thorough cleanup format clearly dictated lists with a spoken heading, numbered steps or unordered bullets. Standalone English commands “new line”, “new paragraph”, and “bullet point” also work offline and with cleanup off.
- Local models can use a separately installed NVIDIA runtime. Settings shows whether the loaded model uses CUDA or CPU, and an explicit GPU request reports setup failures instead of accepting CPU fallback.
- Browse speech models in Setup and Settings without starting a download. Choose **Download** or **Download and continue** after checking the size, then follow progress, pause, resume, or cancel.

### Settings, history and Linux fixes

- If a settings file prevents startup, Caelum shows its path. Edit it and retry, or choose **Back up and reset settings** to keep a copy and return to setup.
- On GNOME and KDE, finishing, pausing or cancelling a speech model download no longer shows “Recording cancelled.”
- On Hyprland, retrying a failed dictation dismisses its Retry/Cancel notification. If the retry fails too, only the new notification can act on it.
- History export now replaces the selected file after you confirm the overwrite. If the export fails, the previous file stays intact.
- On Linux, keeping a transcript available for manual copying now runs fewer background lock checks while idle.
- On Linux, the control socket now replies “Invalid request” when a client sends a malformed or oversized request, or misses the one-second deadline.
- Appearance and sidebar changes save quietly during dictation. Changes to recording mode, clipboard copying, and history settings take effect after dictation finishes or is cancelled, without restarting Caelum.

### Also included from 0.5.1 testing

- The desktop sidebar toggle sits beside the Caelum logo and replaces it when collapsed, giving pages more vertical space.
- New setups use **Super+Alt+V** on GNOME/KDE portal desktops, **Ctrl+Super** on native Hyprland and **Ctrl+Win** on Windows. Setup reports shortcut registration failures; use **Record** and **Finish recording** on Home. Settings shows active and pending portal shortcuts and offers **Restart Caelum** to apply changes.
- Windows dictation preserves the clipboard when inserting into a focused Edit or RichEdit field. If direct insertion fails and the clipboard has changed, choose Retry to copy the finished transcript.
- Turn off automatic clipboard copying in Settings to keep your clipboard intact, including when insertion fails. **Copy transcript** on Home works even with history disabled. You can start the next recording from the tray when a transcript is saved or ready to copy, or after an error with no audio left to retry.
- Windows keeps recovery notices on Home for clipboard fallback, microphone errors and expired retries. The updater says **Installer opened** and checks the running version on next launch; a cancelled installer can be reopened.
- Windows setup uses your regional language and detects NVIDIA display adapters when recommending a speech model. An explicit language selection takes priority.
- If Windows Credential Manager is unavailable, Caelum protects saved provider keys with your Windows account using DPAPI. Existing plaintext fallback entries are migrated on access.
- New profiles start with an empty custom vocabulary. Existing vocabulary is preserved.
- CLI commands now name the config section that must be a TOML table instead of printing a Python traceback.
- Caelum verifies local model content before loading it and offers repair for damaged downloads. Desktop engine startup and connection failures now report errors and allow the app to quit.
- Downloading or switching local speech models in setup or Settings no longer disconnects the desktop app from the engine.
- The website demo now shows the full transcript after hold-to-talk recording and processing finish. The FAQ explains how to copy or insert it on each supported desktop.

## 0.5.0

Changes since stable v0.4.2.

### Added

- Dictate offline with a downloaded speech model. Setup recommends models for your memory and language and verifies downloads. Online mode still supports your own provider.
- New onboarding guides you through speech mode, microphone, shortcut and a practice dictation. Local practice works without a key or upload after the model download.
- Windows x64 adds an installer with the bundled engine, global shortcuts and focus-aware paste. Online setup saves validated API keys in Windows Credential Manager.
- The Linux x86-64 AppImage bundles Python and the local engine. It needs an Ubuntu 24.04-compatible userspace, WebKitGTK 4.1 and PortAudio. Native Arch, Debian, Ubuntu and Fedora packages remain available. Model weights download separately.

### Changed

- New setups default to Ctrl + Win on Windows and Ctrl + Super on Linux. On desktops that require a non-modifier key, select another shortcut or use the on-screen controls.

### Fixed

- Fixed clipboard delivery when the Linux selection owner forks. On portable desktops, use Record and Finish recording, then paste in your editor. With history on, use Copy on the saved transcript.

## 0.4.2

- **Automatic updates.** A new stable version enables signed in-app upgrades from 0.4.0 and the 0.4.1 testing packages. Manual checks also show testing releases with a separate package-manager download action, rather than calling the whole app up to date when only the stable feed was checked.
- **Build identity.** Native packages record their source commit and source date so testing candidates with the same package version can be distinguished from the installed build.
- **Desktop polish.** Remember the accessible Ctrl+B sidebar state, restore appearance at startup, add loading states and short reduced-motion-aware fades, improve screen focus and long History lists, distinguish Home from History, and keep Setup navigation stable.
- **Settings and microphone checks.** Restore useful on-screen help, remove duplicate controls, use the published logo consistently, improve the light-mode status card, save microphone choices before testing, and wait for capture teardown before retrying.
- **Native feedback.** Fade the recording pill and its controls together, disable tray actions after engine disconnection, and avoid rebuilding the tray for unchanged microphone feedback.

### Downloads

Native x86_64 packages target Arch Linux, Debian 12, Ubuntu 24.04/26.04, and Fedora 43. Use the package matching the distribution and system Python minor version. Package filenames, sizes, and SHA-256 hashes are bound by the signed `update.json`; `candidate.json` and `build-info-*.json` identify the exact source and candidate workflow.

### Upgrade

In Settings → System, choose **Check updates**, then **Update & restart**. The installed updater verifies the release signature and package hash before requesting package-manager authorization. Finish dictation and any pending retry first. A running older binary may require one quit/reopen before the local update-check changes appear.

Configuration, credentials, history paths, and the history schema are unchanged. Automated upgrade fixtures cover preservation from 0.3.9 and 0.4.0. Keep local backups when testing recovery or downgrades; there is no automatic rollback.

### Known limitations

Native Wayland overlay behavior, physical shortcuts, live microphone/provider workflows, device reconnects, mixed-monitor scaling, screen readers, and suspend/resume require release-host acceptance testing. Headless X11/WebKit launches and simulated audio do not certify those cases. Python support remains 3.11–3.14; native package dependencies constrain each target's ABI.

### Verification

Release publication requires the five-target candidate workflow, package installation/IPC/simulated-audio/native bootstrap checks, checksums and provenance verification, and the protected signing environment. The exact candidate run and source SHA accompany the release assets. The update-check changes passed 94 frontend tests, 372 Python tests (6 opt-in cases skipped), 10 Rust tests, lint, contrast, build, and bundle-budget checks locally; the release workflow reruns its automated checks for this version.

### Full changelog

https://github.com/Parth-Jadhav-2004/caelum/compare/v0.4.0...v0.4.2


## 0.4.1 release candidate 1

- **Theme selection.** Choose T3 Code, T3 Chat, Grove, Ocean, Ember, Iris, or Caelum mint in Settings.
- **Engine recovery.** Requests have bounded deadlines, validated responses, and explicit recovery without replaying recordings.
- **Release verification.** Native packages pass installation, IPC, simulated-audio and GUI startup checks before promotion.
- **Accessibility.** Improve landmarks, confirmation focus, keyboard navigation, and theme contrast checks.
- **Update trust.** Support overlapping keys and dual signatures while retaining older updater compatibility.
- **MIT license.** Project licensing and third-party notices are included in distribution packages.

### Packages and upgrades

Candidate targets are Arch x86_64, Debian 12, Ubuntu 24.04/26.04, and Fedora 43.
Packages vendor Python dependencies and retain their system Python/native library
requirements. Configuration and SQLite data paths remain unchanged.

### Known limitations and qualification

This is a prerelease for testing, published as `v0.4.1-rc.1`; package versions
are `0.4.1`. It is excluded from the stable update feed. The candidate workflow
and desktop acceptance results must be reviewed before stable publication; see
[qualification](https://github.com/Parth-Jadhav-2004/caelum/blob/v0.4.1-rc.1/docs/qualification-0.4.1.md).
Physical capture and Groq transport were exercised, but phrase accuracy remains unverified. Native Wayland overlays,
physical shortcuts, provider workflows, scaling and suspend behavior require the
qualification record in docs/acceptance.md. GTK4 remains isolated to the native HUD.

### Changelog

https://github.com/Parth-Jadhav-2004/caelum/compare/v0.4.0...v0.4.1-rc.1

## 0.4.0

The main application moves from GTK4/PyGObject to Tauri 2, React, TypeScript,
shadcn/ui and Tailwind. Home, statistics, history, settings and consented setup
share a dark-first design system, with optional light/system appearance.

Python capture, transcription, cleanup, retry handling, SQLite history, TOML
preferences, credentials, MPRIS and native/portal shortcuts retain their existing
implementations and data paths. A managed JSON-lines sidecar connects the new UI.
The native GTK4 layer-shell recording overlay remains an isolated helper because
ordinary Tauri Wayland windows cannot provide its placement/input contract.

Release packaging includes the native executable and locked Python dependencies
for Ubuntu, Debian, Fedora and Arch. Full physical desktop/provider qualification
and clean-install checks on every target are documented in docs/acceptance.md.
On NVIDIA Wayland sessions, Caelum automatically applies the scoped WebKitGTK
explicit-sync workaround to prevent the startup crash reported as GDK Error 71
("Missing acquire timeline"). Explicit user overrides are respected, and the
isolated native recording overlay retains its normal graphics environment.
Startup was verified on the affected hybrid Intel/NVIDIA Hyprland host. The
libayatana-appindicator deprecation warning is nonfatal and may still appear.

The headless WebKit smoke test uses a per-process DMA-BUF renderer workaround.
Prolonged interactive use, GPU resize behavior, real microphone/provider flows,
and clean installation on all distribution targets remain qualification tasks;
see docs/verification.md and docs/acceptance.md for the tested scope.

## 0.3.9

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

## 0.3.8

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

## 0.3.7

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

## 0.3.6

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

## 0.3.5

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

## 0.3.4

Caelum 0.3.4 updates Home, Settings, navigation, and background operation.

- Restore the sentence-style Settings page, with System, Light, and Dark theme selection inside Settings and automatic saving.
- Add a collapsible sidebar with the supplied collapse icon and a Statistics page between Home and History. Remove green button outlines while retaining keyboard focus indicators.
- Show five recent dictations beside a monthly daily-usage calendar. Calendar tooltips show the number of words dictated.
- Replace today's word count on Home with cumulative words dictated. Remove the session count and Ready pill, and simplify Statistics by removing weekly word and output-dispatch metrics.
- Start the dictation service when the app opens, reusing an existing service. Add a system tray menu for Open Caelum, Settings, Start/Pause/Resume dictation, and Quit Caelum. Closing the window keeps Caelum in a supported system tray; Quit stops the app and service.
- Preserve completed onboarding when managing keys or changing providers, so setup stays complete after restarting.

The cumulative word total starts from existing saved history and adds future saved dictations. Retention and deletion do not reduce it; dictations deleted before this feature cannot be recovered. With history saving off, new dictations do not add to the counter. No audio is saved by this feature.

Packages are available for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43. Downloads contain four packages, update.json, and update.json.sig. Signing, package hash verification, and exact distribution/version matching remain unchanged. Settings, keys, and history are preserved when upgrading.

Tray placement is controlled by your desktop. The Caelum-only placement on the left of the local Omarchy bar is a user configuration, not a system layout change made by the package.

## 0.3.3

Fixes global dictation shortcuts in native packages, including Ctrl + Super on Hyprland. Shortcut commands now carry Caelum’s library path explicitly instead of relying on the compositor to inherit the daemon’s environment.

Releases now provide packages for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43. Release downloads contain the four packages plus signed update metadata; Debian packages, per-package checksum files, and the Arch source recipe are no longer uploaded.

Package verification continues to use the signed SHA-256 digests in update.json. The signing key, exact distribution/version checks, and update signature verification are unchanged.

Settings, keys, and history are retained when upgrading.

## 0.3.2

- Setup now opens inside the main window with four sentence-style steps, a progress indicator, and one primary action per step.
- Continue saves provider keys automatically. Keyring storage, explicit provider and practice consent, Contributor consent, and local microphone testing are retained.
- Choose System, Light, or Dark appearance from the bottom of the navigation rail. The preference saves automatically.
- The navigation rail now displays the Caelum name.
- Approved updates install and restart Caelum automatically after administrator authorization. Pending settings are preserved; cancelled or deferred installation can be retried.

Ubuntu and Debian packages now declare the GTK Cairo bridge needed to render icons. Responsive layout sizing is corrected across distribution themes.

Existing settings, keys, and history are retained.

## 0.3.1

This release refreshes the desktop interface with a redesigned Overview and sentence-style Settings. Settings changes save automatically, with provider and advanced options available inline.

It also improves setup layout and privacy guidance. Existing settings and history are retained when upgrading.

## 0.3.0

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

### Installing

Existing 0.2.0 users must install this first updater-enabled release manually.
Choose the package matching your distribution, architecture, and Python version.
Later stable releases can be downloaded through Settings → Updates.

The public update verification key ships in this release. Keep the initial
installation source trusted; a checksum alone does not authenticate its publisher.
Configuration, keys, and history remain outside the package and are preserved.

### Preview limitations

Native desktop/polkit behavior still requires hardware acceptance on each target
distribution. Source, pip, and AUR source installations continue using their
original installation method rather than the in-app native updater. Flatpak,
Windows, macOS, and ARM packages are not included.

## 0.2.0

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
