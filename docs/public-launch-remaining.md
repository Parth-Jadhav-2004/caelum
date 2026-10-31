# Public launch — remaining work

Goal: a **public Linux beta** where someone else can install Caelum, add their own
free Groq key, and get a first successful dictation without your local setup.

**P0** is required before that beta. **P1** can follow during beta.

This list is what is still open in the current checkout. Items marked **verify**
already exist in code or docs and still need a hands-on pass. Live Groq calls and
desktop acceptance are not covered by the mocked test suite.

## Already in the tree

These are not remaining implementation tasks. They still need the checks called
out below.

- Default speech-to-text is Groq Whisper Large v3 Turbo (`whisper-large-v3-turbo`).
- Cleanup can be turned off with an empty model, and a failed or slow cleanup
  falls back to the raw transcript (“Done · unrefined”).
- Retry, cancel, 60-second in-memory expiry, and clipboard recovery exist.
- Hyprland pastes into the original window. Other desktops copy text for manual paste.
- The GTK app can start, stop, pause, and resume the service. Closing the window
  leaves dictation running.
- Optional history, retention, delete-one, delete-all, and JSONL export exist.
- In-app credentials use the desktop keyring, with a visible mode-600 private-file
  fallback when unavailable. Legacy environment keys remain supported.
- `.github/workflows/release.yml` runs tests and builds distro packages.
- `docs/privacy.md` and `docs/acceptance.md` exist. Many acceptance boxes are
  still unchecked. There is no `LICENSE` file.

## 1. Functionality

- [ ] **P0 — Ship a default free setup.** Keep Groq Whisper Turbo for transcription.
  Use one Groq key for refinement too. Candidate model: Groq-hosted
  `openai/gpt-oss-20b`. Benchmark it before making it the default. Today’s
  default cleanup model is OpenAI `gpt-6-luna`, which is not a free path for
  other people. Meta Muse Spark 1.3 Contributor stays an explicit opt-in, not
  the public default.
- [x] **P0 — Let transcription start when refinement cannot.** Removed the
  startup cleanup model-list dependency. Missing credentials, unavailable models,
  and outages fall back to raw text. Portable service integration tests cover
  startup and recording with an unavailable model and missing cleanup key.
- [x] **P0 — Name provider failures.** Sanitized failure categories distinguish
  invalid key, permissions, rate limit, explicit quota codes, timeout, offline,
  and unavailable model/service. STT notifications offer recovery guidance;
  cleanup records its fallback reason. Retries honor numeric/date Retry-After
  within the overall deadline. Provider-specific live error responses still need
  acceptance testing; an ambiguous 429 is reported as a rate limit.
- [ ] **P0 — Verify recoverable work.** Retry, cancel, expiry, and clipboard
  recovery must not insert the same text twice. **Verify.**
- [ ] **P0 — Check request fields per preset.** Reasoning settings, token limits,
  and related parameters must be valid for Groq Whisper, the chosen Groq
  refinement model, and any custom preset. Do not send OpenAI-only fields to
  Groq.
- [ ] **P0 — Verify the service lifecycle.** Start, stop, pause, resume,
  close-window, autostart, and recovery after a crash. **Verify.**
- [ ] **P0 — State desktop behavior accurately.** Native paste only on qualified
  Hyprland sessions. Portable desktops copy and paste manually. **Verify** the
  app, README, and package text say the same thing.

- [ ] **P1 — Add more provider presets** after the free Groq path works.
- [ ] **P1 — Local or offline inference** is a separate project.

## 2. UI

- [x] **P0 — Add simple provider presets.** “Groq”, “Transcription only”, and
  “Custom provider”. Base URLs and technical parameters live under Advanced.
- [x] **P0 — Show connection status.** Key missing, connected, invalid key, or
  connection unavailable.
- [x] **P0 — Make service states obvious** in the desktop window: stopped, ready,
  recording, processing, paused, and awaiting retry. The HUD pill already has
  several of these states.
- [x] **P0 — Show refinement status.** The user should see when the result is raw
  transcription. The pill already says “Done · unrefined”; the app should say
  the same.
- [x] **P0 — Make errors actionable.** Say what happened and offer the next step:
  retry, update the key, pick a microphone, or copy the text.
- [x] **P0 — Explain paste behavior.** Say whether this desktop will paste
  automatically or whether the user must copy.
- [x] **P0 — Check keyboard navigation, text scaling, contrast, and small
  windows.**

- [ ] **P1 — Tray or status indicator**, if background-service behavior confuses
  testers.

## 3. Onboarding

Implemented as a resumable native setup window; live-provider and desktop/keyring acceptance remain release checks.

- [x] **P0 — First-launch setup:** welcome, privacy explanation, provider and key,
  microphone, shortcut, practice dictation.
- [x] **P0 — Link to Groq key creation** and say that free usage has provider
  limits.
- [x] **P0 — Enter, replace, and delete the key inside the app**, stored securely.
- [x] **P0 — Validate the key and selected models** before setup is marked done.
- [x] **P0 — Local microphone test**, separate from a cloud transcription test.
  Settings already has a three-second local meter; the wizard should use that
  and label it as local-only.
- [x] **P0 — Detect shortcut conflicts** and explain desktop permission dialogs.
- [x] **P0 — Finish with one successful practice dictation** and show where the
  text went.
- [x] **P0 — Resume setup later**, and reopen it from Settings.

- [ ] **P1 — Optional autostart** offered only after setup succeeds. Launcher and
  start-at-login toggles already exist in Settings.

## 4. Privacy and security

- [x] **P0 — Store the API key in the desktop keyring.** Setup uses Secret Service;
  unavailable keyrings use an explicitly labelled, owner-only private-file fallback.
  Real desktop unlock dialogs remain acceptance work.
- [x] **P0 — “Don’t save history”.** Settings exposes Save dictation history;
  `desktop.history_enabled = false` is preserved and prevents new database writes.
  Existing entries remain deletable/exportable. Portable history-off delivery copies
  directly to the clipboard; clipboard failure preserves retry audio.
- [x] **P0 — Explain data flow before the first upload.** Setup explains audio,
  refinement, optional history, clipboard and provider limits before consented practice.
  Settings repeats the notice; direct CLI service startup prints it before capture.
- [x] **P0 — Require opt-in for Contributor models.** Setup saves explicit training
  consent for the exact endpoint/model. The provider enforces it before sending text,
  including outside setup. Missing/stale consent falls back to raw transcription.
  Custom aliases cannot expose undisclosed provider training policies.
- [x] **P0 — Keep retention, delete-all, and export easy to find.** History remains
  a top-level page with Export/Delete all; retention and history saving are in Settings.
- [x] **P0 — State the limits.** Setup and Settings explain unencrypted history and
  independent clipboard-manager/export copies; README and privacy policy agree.
- [x] **P0 — Scan the repository and release packages.** Tracked files and local
  artifacts scanned; CI scans tracked files and every native package staging tree.
  Scans reject private runtime filenames and recognizable credential/private-key
  patterns without printing values. This is not detection of arbitrary personal prose.
- [x] **P0 — Confirm logs and errors omit audio, transcripts, prompts, and keys.**
  Provider errors are fixed categories; regression checks inject sensitive response
  content and check errors, captured logs, metrics and HUD payloads. Clipboard text
  travels over stdin rather than command arguments.
- [x] **P0 — Use the same privacy wording** in onboarding, Settings, README and
  package descriptions: cloud dictation with optional local history. The full policy
  ships with native packages.

## 5. Testing and release

- [x] **Signed native updater implementation.** CI signs expiring per-target
  manifests; the desktop prompts before download and installs verified packages
  on the next app launch through polkit. Busy dictation and retry audio defer
  installation. Security and GTK consent tests cover the implemented flow.
- [ ] **Provision release signing before publishing.** Commit the public Ed25519
  key and configure the protected `release` environment secret. The updater stays
  disabled and publication fails closed until this is done. See `docs/updates.md`.
- [ ] **Exercise a real two-version signed update on each target distro.** Check
  polkit approval/cancellation, next-launch installation, service restart,
  interrupted-package-manager recovery, and preservation of settings/keys/history.
- [ ] **P0 — Run tests and lint on the release commit.**
  `pytest`, `ruff check`, and the desktop test job in `release.yml`.
- [ ] **P0 — Call Groq for real.** Transcription and the chosen refinement model.
  Mocked tests are not enough. `docs/acceptance.md` still has this unchecked.
- [ ] **P0 — Try a speech set:** English, Hindi and Hinglish, accents, noise,
  quiet speech, names, numbers, URLs, and code.
- [ ] **P0 — Check that refinement keeps meaning**, especially negation, amounts,
  identifiers, and mixed-language text.
- [ ] **P0 — Measure short and long dictations**, including slow responses and
  fallback to raw text.
- [ ] **P0 — Break it on purpose:** network loss, quota errors, unplugged
  microphone, cancel, lock and suspend, and crashes.
- [ ] **P0 — Check insertion and focus** in a browser, an editor, a terminal, and
  a chat app.
- [ ] **P0 — Install on each advertised distro and desktop** from a clean
  machine, including upgrade, uninstall, the launcher, and next-login autostart.
- [ ] **P0 — Inspect the packages** produced by `.github/workflows/release.yml`.
  The workflow exists. Confirm the artifacts match the install docs and contain
  no secrets.
- [ ] **P0 — Add a license**, dependency notices, install steps, and known
  limitations. There is no `LICENSE` file.
- [ ] **P0 — Run a small external beta.** Fix install failures, lost text,
  duplicate paste, and privacy bugs before wider posts.

- [ ] **P1 — Widen platform coverage** after the first supported setups are
  reliable. Flatpak, Flathub, AUR, ARM, Windows, and macOS are out of this beta.

## First batch

Implement these before the UI and onboarding sections:

1. Groq preset for transcription plus the chosen free refinement model.
2. Transcription still starts when refinement is missing or down.
3. Clear provider errors, including rate limits.
4. In-app key entry with keyring storage.
5. Optional history.

That is the gap between a working personal setup and someone else’s first
dictation.

## Functionality implementation verification — 2026-10-30

Fresh configs now need only GROQ_API_KEY and default to transcription only.
The same-key Groq refinement configuration is documented in README and the
example config. The gpt-oss-20b quality/latency benchmark remains open, so
refinement is deliberately not enabled by default. Existing saved settings
are not rewritten.

Automated coverage includes request fields for Groq, OpenAI, and a custom
endpoint; Groq gpt-oss reasoning settings; invalid credentials, permissions,
quota, rate limits, Retry-After, offline and timeout; missing cleanup credentials;
retry success, repeated retry after paste/clipboard delivery, cancellation,
late responses, expiry, pause/resume, service shutdown, settings reload and
shortcut collision rollback. Custom endpoint compatibility still depends on
that endpoint implementing the configured OpenAI-compatible API.

Verification commands:
- pytest -q
- ruff check src tests
- GDK_BACKEND=wayland CAELUM_DESKTOP_TESTS=1 pytest tests/test_desktop.py -q
- CAELUM_NATIVE_TESTS=1 pytest tests/test_native.py -q

GTK checks passed. Native HUD and visible GTK paste checks passed; native binding
and service checks skipped to preserve another running Caelum service.
README, app behavior, installed desktop entry and generated launcher descriptions
agree: qualified Hyprland uses native paste, portable desktops require manual
copy/paste from history.

Still open before marking all Functionality P0 complete:
- Benchmark the opt-in Groq refinement model using a consented speech corpus.
- Verify actual Groq model availability, accepted fields, quota errors and timing.
- Exercise crash/relaunch and next-login autostart on a disposable session.
- Verify insertion/focus in browser, editor, terminal and chat apps.
- Qualify portable desktop behavior on the advertised desktop/distro matrix.
UI, onboarding, and privacy P0 work are separate sections and are not completed
by this functionality batch.


## UI P0 implementation verification — 2026-10-30

- Settings offers Groq, Transcription only, and Custom provider. Selection edits
  the draft; Save settings remains explicit. Custom configurations remain intact
  on opening Settings. Groq refinement remains opt-in pending live qualification.
- Advanced holds endpoint, model, key-variable, language and reasoning fields.
  Connection checks run off the GTK thread against the current draft, validate
  URLs before sending credentials, and discard stale results after edits.
  Checks send no audio/transcript and do not start automatically.
- Connection text distinguishes missing key, model available, rejected key,
  unavailable model, timeout, quota/rate limit and unavailable connection.
  Model-list access does not prove available quota or successful inference.
- Overview names stopped, ready, recording, processing, paused and awaiting retry,
  with error-specific guidance, conditional Retry/Discard/Open Settings actions,
  and explicit automatic versus manual paste instructions.
- Raw transcription is identified in completion status and recent/history cards,
  including portable saved results and clipboard fallback.
- Controls wrap, the sidebar collapses below 800 px, pages scroll vertically,
  text inherits the system font size, field controls have accessible labels,
  and keyboard focus uses a high-contrast outline.

Verification: full suite with GTK enabled: 119 passed, 4 native checks skipped;
ruff and diff whitespace checks passed. Native GTK checks cover preset edits,
connection status delivery, recovery controls, Tab/Shift-Tab navigation, all pages
at <=640 px minimum width with collapsed sidebar, and larger system text within
800 px. Palette contrast was checked for text and focus against application
surfaces. No microphone or cloud request is needed for these UI checks.
A screen-reader review, additional display scales/themes, and actual provider
connection/inference checks remain release acceptance work.

Rapid queued Retry clicks also have a regression check: only one finalization
task is scheduled, preventing duplicate delivery before the UI refreshes.


## Onboarding P0 implementation verification — 2026-10-30

First launch opens setup, and Settings can reopen it for setup or key management.
The flow covers privacy, provider/key/model validation, microphone selection and
a three-second local test, shortcut preflight and desktop-permission guidance,
and a five-second practice dictation with separate upload consent. Practice text
appears in setup only; copying is explicit and practice writes no history.
Completion requires successful model validation, microphone test, and practice.
An incomplete setup resumes at provider validation so stale access cannot be
assumed. Configured microphone, providers, and shortcut persist between launches.
Custom endpoints can be configured in Settings and then validated in setup.

Managed keys use secret-tool / Secret Service; packages declare the required
libsecret tools. Unavailable keyrings fall back to an atomic mode-600 private
JSON file with a visible unencrypted-storage notice. Deletion clears managed
storage and disables legacy environment fallback. A locked keyring deletion
fails visibly instead of claiming success. Secret lookup runs outside GTK and
the event loop; cleanup key lookup shares the bounded cleanup deadline.

Verification with GTK enabled: **138 passed, 4 native checks skipped**; lint and
whitespace checks passed. Automated checks cover keyring/fallback storage, replacement, deletion, file
permissions, environment precedence, all-model validation, native shortcut
conflicts, portable permission guidance, recording disposal, cancellation,
first-launch activation, resumability, and completion gates. The GTK workflow
uses mocked microphone/provider/keyring operations; it does not upload or store
real credentials. Real Groq practice, real keyring unlock dialogs, portable
shortcut permissions, and fresh-machine installation remain acceptance checks.

## Privacy/security P0 verification — 2026-10-31

- Preserved and enforced `desktop.history_enabled`, with a Settings switch and
  existing-history deletion/export still available. Tests cover no database
  creation, saved false values, session snapshots, portable clipboard delivery,
  clipboard failure/retry, and duplicate-retry prevention.
- Contributor training consent is persisted for the selected refinement endpoint
  and model and checked in the provider before credential lookup or upload.
  GTK tests cover blocking unchecked consent and saving checked consent. Provider
  tests cover missing consent and changed endpoint/model.
- Setup and Settings share the data-flow and storage-limits notice. README,
  privacy policy, and native package descriptions describe optional local history.
  Direct service CLI startup prints the notice before capture starts.
- Existing credential tests verify keyring storage, private-file permissions,
  replacement, deletion, locked-keyring failure, and environment tombstones.
- Sensitive-content regression tests cover provider errors, logs, metrics and HUD;
  clipboard subprocesses receive text through stdin, never command arguments.
- `scripts/scan_privacy.py` checks tracked files in CI and every native package
  staging tree before packaging. Current tracked files, the four existing local
  artifacts (two DEBs, Arch package, wheel), and a fresh Debian build passed.
  Detection covers private runtime filenames and recognizable credential patterns;
  arbitrary prose and unknown secret formats still require human review.

Verification: GTK-enabled full suite **201 passed, 4 native checks skipped**;
`ruff check src tests scripts`, repository scan, and whitespace checks passed.
A fresh Debian package built successfully with its staging privacy scan enabled.
No real credentials, recordings, transcripts, or cloud requests were used.
Real keyring unlock dialogs and desktop clipboard integration on each supported
session remain release acceptance checks.
