# Public launch — remaining work

Goal: a **public Linux beta** where someone else can install Caelum, add their own
free Groq key, and get a first successful dictation without your local setup.

**P0** is required before that beta. **P1** can follow during beta.

Last reviewed: **2026-10-31**, working checkout based on `472a529` (0.3.0),
including concurrent uncommitted onboarding/UI changes. A checked implementation
item means code and relevant automated coverage exist; it does **not** certify
live-provider, hardware, or distribution acceptance. Historical verification
sections below describe the checkout tested on their dates.

## Current assessment — 2026-10-31

**Not ready for wider rollout.** The main features are implemented, but the audit
found **seven P0 issues** and **four P1 follow-ups**, listed with evidence and
completion criteria in [Code audit findings](#code-audit-findings--2026-10-31).
These findings are open; documenting them does not fix them.

The initial GTK-enabled suite passed **201 tests, with 4 skipped**. A final rerun
following concurrent UI copy edits gave **200 passed, 1 failed, 4 skipped**: the
invalid-key message test still expects the old wording (A09). Lint and the local
privacy scan pass. This working tree is therefore not fully green either.

Implemented and supported by automated coverage:

- One-key Groq transcription-only defaults, optional same-key refinement,
  sanitized provider errors, bounded request retries, and raw-text fallback.
- Ordinary retry/cancel/expiry and duplicate-click protection. Partial native
  paste failures remain an exception: see A03.
- GTK pages, presets, connection checks, recording/recovery controls, keyboard
  navigation, text scaling, and the Alt container-outline fix. Database failure
  can still prevent service controls from updating: see A05.
- Resumable setup, model-list validation, local microphone testing, shortcut
  preflight, and separately consented cloud practice. The GTK workflow tests mock
  providers, microphone capture, and keyring operations.
- Keyring/private-file credentials, environment-key tombstones, optional history,
  retention/deletion/export, Contributor consent, and sensitive-data regression
  checks. Semantic cleanup validation needs strengthening: see A06.
- Signed manifest verification, consented staging, privileged reverification,
  idle-only update shutdown, and six-target package workflows. Real upgrades are
  still unqualified, and the latest main-branch CI run fails: see A07.

Still required for the launch decision:

1. Fix A01–A07 and add regression coverage for their failure paths.
2. Pass the complete distro test/package workflow on the final release commit.
   Inspect that commit's artifacts; an older successful release does not qualify
   newer code.
3. Qualify real Groq transcription and optional refinement: multilingual/noisy/
   quiet speech, short/long recordings, model/request compatibility, quota errors,
   meaning preservation, and latency. Keep refinement off by default until qualified.
4. Run clean-machine installation, launcher, actual next-login autostart,
   keyring unlock, portal permission/fallback, crash recovery, lock/suspend,
   microphone unplug, and browser/editor/terminal/chat insertion checks on every
   advertised desktop/distro combination. Narrow advertised support if these
   cannot all be qualified.
5. Exercise a real two-version signed update on every supported package target,
   including authorization cancellation, service restart, interrupted installation,
   and preservation of settings, keys, and history.
6. Choose and add a project license, review dependency notices, align release
   documentation, and run a small external beta before wider promotion.

The Ed25519 public key, protected release environment, signing-secret name, and
`v*` deployment policy are provisioned. GitHub shows a published
[v0.3.0](https://github.com/Parth-Jadhav-2004/caelum/releases/tag/v0.3.0).
Neither fact proves real desktop upgrades or broad-user acceptance.

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

- [x] **P0 — Ship a default free setup.** Fresh configurations use Groq Whisper
  Turbo and no refinement; `GROQ_API_KEY` is the only required credential.
  The Groq preset optionally uses `openai/gpt-oss-20b` with that same key.
  Saved configurations are preserved. Real availability, free-tier limits, and
  the optional refinement quality/latency benchmark remain acceptance work;
  OpenAI is no longer the fresh-config default.
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
  recovery must not insert the same text twice. Ordinary paths have regression
  coverage, but ambiguous native delivery can duplicate paste: fix A03, then
  verify actual applications and notification actions.
- [x] **P0 — Check request construction per preset.** Tests cover Groq Whisper,
  Groq gpt-oss reasoning settings, OpenAI token/storage fields, and a custom
  endpoint. Provider-specific filtering is implemented. This verifies payload
  construction, not live model availability or arbitrary custom API compatibility;
  real Groq inference remains open in section 5.
- [ ] **P0 — Verify the service lifecycle.** Start, stop, pause, resume,
  close-window, autostart, and recovery after a crash. Ordinary controls have
  tests; fix A01, A02, and A04 before crash/device-failure qualification.
- [x] **P0 — State desktop behavior accurately.** App and package descriptions
  distinguish native Hyprland paste from portable manual paste. History-off
  portable delivery copies directly to the clipboard. Hardware qualification is
  still required; broader documentation drift is tracked in A11.

- [ ] **P1 — Add more provider presets** after the free Groq path works.
- [ ] **P1 — Local or offline inference** is a separate project.

## 2. UI

The normal UI paths below are implemented. A05 is an additional P0 fault-handling
requirement; A09 tracks the remaining CLI/key-repair verification. Screen-reader and physical
multi-display acceptance remain open.

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
- [x] **Provision release signing before publishing.** The tracked public key is
  Ed25519. Read-only GitHub checks confirm `CAELUM_UPDATE_SIGNING_KEY` exists in
  the `release` environment, a required-reviewer rule is configured, and the
  deployment policy allows `v*` tags. The published v0.3.0 workflow succeeded.
  Secret contents were not read. Continue protecting the key/environment;
  see `docs/updates.md`.
- [ ] **Exercise a real two-version signed update on each target distro.** Check
  polkit approval/cancellation, next-launch installation, service restart,
  interrupted-package-manager recovery, and preservation of settings/keys/history.
- [ ] **P0 — Run tests and lint on the release commit.**
  The initial local suite passed; a final rerun has a stale key-message assertion
  after concurrent UI edits (A09). Lint and the local privacy scan pass. The latest
  main-branch six-distro workflow fails before pytest at the privacy scan (A07).
  Require green tests, lint, scan, and package jobs on the final release commit.
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

## Release work order

1. Fix the confirmed P0 findings below, preserving privacy and recoverable text.
2. Add fault-injection regressions and obtain a green six-target build.
3. Complete provider/hardware/update acceptance and license/release documentation.
4. Run a small external beta, then decide which platforms can be advertised.

The earlier first batch (presets, raw fallback, named errors, key entry, optional
history) is implemented. Reimplementing those features is not the remaining gap.

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


## Code audit findings — 2026-10-31

Scope: capture/segmentation, providers/cleanup validation, orchestration, native
and portable desktop integration, service/IPC/reload, credentials, onboarding,
GTK/history, updater, CLI/launchers, package builders, release workflow, and the
corresponding tests/docs. This is a source and fault-injection review, not a claim
that all hardware/provider combinations were exercised. No application fixes
were made by this audit.

### Confirmed P0 findings

- [ ] **A01 — Handle lock-state lookup failure without crashing the monitor.**
  In [`service.lock_monitor`](../src/caelum/service.py), the exception branch
  assigns `locked = True` instead of `is_locked = True`. If the first lookup
  fails, the next statement raises `UnboundLocalError` before calling cancel.
  After a previous successful lookup, it reuses the previous result and replaces
  the lookup callable with a boolean. An injected `RuntimeError` reproduced the
  first case with zero calls to `core.handle`. The service's failed-task callback
  then shuts the daemon down; this is an availability/recording-loss issue, not
  evidence that it continues recording through a lock.
  **Done when:** lookup errors trigger controlled fail-closed cancellation, never
  reference an unset/stale value or overwrite the callable, and first/subsequent
  failures plus actual lock/suspend have regression/acceptance coverage.

- [ ] **A02 — Recover native shortcuts after an unclean daemon exit.**
  [`linux.Bindings.install`](../src/caelum/linux.py) checks collisions before
  removing the compositor's previous `_caelum` handles. A hard-killed daemon
  cannot remove its Lua bindings, so restart rejects its own old shortcut as a
  collision. Injecting an existing `Caelum hold to dictate` binding reproduced
  the rejection before any cleanup command. The single-instance daemon lock
  does not clean compositor state.
  **Done when:** crash/restart reclaims only positively identified Caelum-owned
  handles while preserving real user conflicts and unrelated bindings. Test hard
  kill/relaunch and compositor reload, not just orderly removal.

- [ ] **A03 — Treat ambiguous native paste as uncertain delivery, not safe retry.**
  [`linux.insert`](../src/caelum/linux.py) can dispatch paste key-down and then
  fail sending key-up. [`Orchestrator.finalize`](../src/caelum/orchestrator.py)
  retains PCM on that exception. A fault-injection probe sent a successful first
  key-down, failed key-up, retried, and observed a second key-down. An application
  that pastes on key-down can receive the text twice. A timeout after dispatch
  can have the same uncertainty; passing tests currently model insertion as an
  all-or-nothing operation.
  **Done when:** distinguish failures before dispatch from uncertain post-dispatch
  outcomes, attempt key release on every relevant failure path, and offer explicit
  clipboard/manual recovery without automatically issuing a second paste for an
  uncertain delivery. Add partial-side-effect and timeout regressions.

- [ ] **A04 — Preserve cleanup/recovery when stopping the microphone fails.**
  [`Capture.stop`](../src/caelum/audio.py) calls `stop()` and then `close()` without
  a `finally`. A stop error skips close. In
  [`Orchestrator.release`](../src/caelum/orchestrator.py), `self.capture` is cleared
  and the UI enters processing before stopping; the same error exits before PCM
  is retained or finalization is scheduled. Fault injection reproduced processing
  with neither a capture nor retry PCM, and an unclosed stream. Abort/shutdown
  also rely on the same stop method and can skip subsequent resource cleanup.
  **Done when:** stop/close errors leave a defined cancelled or recoverable state,
  close is attempted, buffers are disposed only after capture is quiescent, and
  shutdown releases bindings, HUD, client, and lock despite individual failures.
  Test stop and close failures plus real device unplug.

- [ ] **A05 — Keep service controls usable when history is unreadable.**
  [`Desktop.refresh`](../src/caelum/desktop.py) fetches status and reads history
  in one worker result. A corrupt/locked/unwritable history database causes that
  result to fail before `render_data` updates service controls. A native GTK probe
  with an invalid SQLite file and a mocked healthy recording daemon left
  `Checking dictation service…` displayed and Cancel hidden. This can prevent
  portable users from finishing/cancelling through the window.
  **Done when:** render service status independently of history reads; show an
  actionable history-storage error and keep Stop/Cancel/Finish usable. Preserve
  existing data rather than silently deleting a corrupt database. Test corrupt
  SQLite, denied access, and lock contention while recording.

- [ ] **A06 — Strengthen meaning/number checks on optional refinement.**
  [`quality.validate_cleanup`](../src/caelum/quality.py) accepts both
  `I do not approve the transfer today.` → `I do approve the transfer today.`
  and `Transfer 10 dollars today.` → `Transfer 100 dollars today.` as refined
  output. Both were reproduced directly. Similarity permits negation deletion,
  and protected values use substring membership (`10` occurs inside `100`).
  Prompt instructions and the present heuristic do not guarantee meaning.
  **Done when:** reject protected-token/amount changes using exact boundaries,
  add conservative negation/critical-content regression cases, fall back to raw
  text on rejected edits, and qualify English/Hindi/Hinglish meaning preservation.
  Keep optional refinement unqualified/off by default until that evidence exists;
  automated heuristics alone cannot certify semantic equivalence.

- [ ] **A07 — Repair the failing container CI privacy-scan step.**
  [Run 41177743908](https://github.com/Parth-Jadhav-2004/caelum/actions/runs/41177743908)
  for `472a529` fails on all six distro test jobs. Logs show
  `git ls-files -z` inside `scripts/scan_privacy.py` fails with Git's
  `detected dubious ownership` error; pytest and downstream package jobs do not
  run. [The workflow](../.github/workflows/release.yml) configures `safe.directory`
  in the package job, but not before the test job's new scan.
  **Done when:** establish trust for the exact checked-out workspace in each test
  container before the scan (not a global wildcard), retain the privacy gate,
  and get green test/GTK/package jobs on the intended release commit.

### Confirmed P1 follow-ups

- [ ] **A08 — Distinguish identically named microphones.**
  [`desktop.microphones`](../src/caelum/desktop.py) returns `(name, name)` pairs;
  Settings/setup deduplicate them with `dict.fromkeys`. A probe with two inputs
  named `USB Audio` produced only one selectable entry. PortAudio name lookup can
  also be ambiguous across host APIs. Users with duplicate USB devices or host
  API aliases cannot reliably select the intended input.
  **Done when:** display distinguishing device/host-API information, use a device
  identity that resolves the intended input, and handle reordered/disconnected
  devices without silently switching to another microphone.

- [ ] **A09 — Point credential failures to in-app key repair.**
  At `472a529`, desktop error/connection text tells users to edit the launch
  environment and restart for missing/invalid keys. **Concurrent uncommitted UI
  edits now correct that text** to point to setup and retry; that part is already
  addressed in the working tree and should not be reimplemented. The final
  test rerun fails `test_service_status_copy` for `invalid_key`: it still expects
  `Update the key`, while the UI now says `Replace the key`.
  [`service.serve`](../src/caelum/service.py) still says to export a key.
  Managed setup keys take precedence over environment values and are read on
  subsequent requests. Editing an environment key can therefore have no effect;
  restarting also discards a pending recording unnecessarily.
  **Done when:** direct users to Open setup / Manage keys, explain precedence and
  locked-keyring errors, and allow repair followed by retry where safe. Preserve
  a pending recording when merely replacing a credential, and update the stale
  message assertion so the current suite passes.

- [ ] **A10 — Validate malformed config structure and offer startup recovery.**
  [`config.load`](../src/caelum/config.py) assumes every section is a table and
  immediately calls `.copy()`. A file containing `app = 1` raises `AttributeError`
  instead of a useful validation error; the CLI's error boundary does not catch
  it. The app loads config before building its window, so invalid settings can
  block access to the UI used to repair them.
  **Done when:** validate top-level/section structure, report sanitized actionable
  errors, preserve the bad file, and provide an explicit recovery/edit/reset
  route. Cover wrong section types, malformed TOML, and unknown options.

- [ ] **A11 — Align release and architecture documentation with shipped behavior.**
  `README.md` and install examples in `docs/linux.md` still name 0.2.0 although
  `pyproject.toml`, the Arch recipe, and the published release are 0.3.0.
  [`docs/architecture.md`](architecture.md) says history always persists, its
  toggle is retired, launchers require a source checkout, and automatic upgrades
  are absent. Those claims conflict with the current privacy controls, packaged
  launcher, and updater. `docs/acceptance.md` still names GPT-6 Luna in its
  provider-qualification item.
  **Done when:** align the release commands/current-version links and distinguish
  mandatory/default/optional history and refinement accurately in every user and
  maintainer document; retain truthful platform and acceptance limitations.

### Evidence and limits of this audit

- `GDK_BACKEND=wayland CAELUM_DESKTOP_TESTS=1 .venv/bin/pytest -q`:
  initial baseline **201 passed, 4 skipped**; final rerun after concurrent UI
  edits **200 passed, 1 failed, 4 skipped**. The failure is the stale invalid-key
  text expectation described in A09. The skipped checks are opt-in native
  HUD/binding/capture/insertion tests; they were not enabled against the user's
  live service.
- `.venv/bin/ruff check src tests scripts`: passed.
- `.venv/bin/python scripts/scan_privacy.py`: passed for tracked working files.
- `git diff --check`: passed after the documentation update.
- Separate deterministic probes reproduced A01–A04, A06, A08, and A10 using
  synthetic input and mocked boundaries. A05 was reproduced in an isolated native
  GTK app with a synthetic corrupt database. A07 is backed by GitHub job logs;
  A09/A11 are source/document contradictions, with the concurrent UI correction
  to A09 explicitly noted. These probes are evidence,
  not newly committed regression tests; fixes need durable regression coverage.
- Read-only GitHub checks confirmed the failing current CI run, a successful
  earlier v0.3.0 release run, the public release, public-key type, environment
  secret **name**, required reviewer, and tag policy. No secret value was read.
- No real provider calls, private recordings, privileged installs, or changes to
  the running dictation service were made. Fresh package installation, real
  keyring/portal dialogs, actual device unplug/lock/suspend, screen-reader and
  multi-DPI use, real two-version upgrades, and external-user testing remain open.

## Interactive desktop privacy verification — 2026-10-31

Used the agent-desktop CLI against the actual GTK application with separate XDG
config/data/runtime directories, a synthetic ALSA microphone, a dummy credential
in the real Secret Service keyring, and a localhost OpenAI-compatible provider.
The initial native Wayland observation exposed the welcome-page layout issue;
interactive keyboard tests ran through Xwayland because agent-desktop's Wayland
keyboard backend requires Mutter. No room audio or real provider keys were used,
and no audio/transcripts were sent to an external provider. The user's existing
Caelum instance, credentials, settings and history were not changed.

Verified through the GUI and independently checked persisted state/request counts:

- Welcome privacy consent blocks Continue. Contributor consent blocks validation;
  model validation makes two model-list requests and sends no dictation content.
- Saving and replacing a dummy key uses the actual keyring; credential metadata is
  mode 600 and contains no key value. Deletion clears the actual keyring item and
  leaves a deletion tombstone. Test credentials were removed after testing.
- The three-second local microphone test passes without provider uploads. Practice
  refuses unchecked upload consent; consented practice succeeds, enables Finish,
  and creates no history files.
- Service start, pause, resume, regular Record/Finish and explicit Copy work.
  A completed history-on dictation creates exactly one retained session.
- Turning history saving off and saving applies to the running service. A later
  dictation populates the clipboard and leaves the existing database count at one.
  The disabled preference and delivery wording survive closing/reopening the app.
- A simulated 401 produces Awaiting retry with recovery controls. Restoring the
  localhost provider and choosing Retry completes delivery. Provider response
  sentinel text is not exposed in the UI.
- Editing a consented Contributor model invalidates consent: transcription still
  completes, raw-result status appears, and the refinement request count does not
  increase. Cancel recording makes no further transcription request.
- Search filters history. Export creates one JSONL row with mode 600. Delete all
  empties history/statistics while leaving the export in place and accessible
  controls available with history disabled.
- Closing the window leaves the service running. Reopening resumes incomplete
  setup, preserves saved preferences, and reconnects to the service. Explicit
  Stop service shuts down the isolated daemon. Test windows/processes were closed.

Corrections made during this pass:

- Setup now measures the visible page's height so hidden pages do not push welcome
  navigation below the default viewport. GTK coverage checks the allocated button
  position rather than only configured widget properties.
- Credential error, connection and startup guidance points to in-app key management
  and retry. The stale invalid-key test expectation reported in A09 is repaired.
  History-off delivery instructions no longer promise new text below the controls;
  Delete all explicitly says clipboard copies and exports are independent.
- Source-install dependencies include keyring and clipboard tools.
- The A07 ownership failure is fixed in the scanner: its Git command trusts only
  the exact repository containing the script, for that invocation. A regression
  runs the scanner from another working directory with Git's different-owner test
  flag. This verifies the code fix locally; green remote release jobs still need
  to be confirmed on the intended release commit.

Final validation: **202 passed, 4 opt-in native tests skipped** with GTK enabled;
lint, privacy scan (including simulated container ownership), and whitespace
checks passed. Real Groq inference, native Hyprland paste/focus, physical microphone
unplug/lock/suspend, keyring unlock prompts, and clean-distro installs remain
acceptance work. The separate source-audit findings above remain tracked; this
GUI pass does not claim to resolve that full audit list.
