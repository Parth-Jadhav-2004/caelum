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
- History, retention, delete-one, delete-all, and JSONL export exist. History is
  always on.
- Credentials stay in the environment or a mode-600 `environment` file. They are
  not entered in the app and are not stored in the keyring.
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

None of this flow exists. First run is still “edit config and export a key”.

- [ ] **P0 — First-launch setup:** welcome, privacy explanation, provider and key,
  microphone, shortcut, practice dictation.
- [ ] **P0 — Link to Groq key creation** and say that free usage has provider
  limits.
- [ ] **P0 — Enter, replace, and delete the key inside the app**, stored securely.
- [ ] **P0 — Validate the key and selected models** before setup is marked done.
- [ ] **P0 — Local microphone test**, separate from a cloud transcription test.
  Settings already has a three-second local meter; the wizard should use that
  and label it as local-only.
- [ ] **P0 — Detect shortcut conflicts** and explain desktop permission dialogs.
- [ ] **P0 — Finish with one successful practice dictation** and show where the
  text went.
- [ ] **P0 — Resume setup later**, and reopen it from Settings.

- [ ] **P1 — Optional autostart** offered only after setup succeeds. Launcher and
  start-at-login toggles already exist in Settings.

## 4. Privacy and security

- [ ] **P0 — Store the API key in the desktop keyring**, with a private-file
  fallback only where the keyring is unavailable. Today the key is an
  environment variable or `~/.config/caelum/environment`.
- [ ] **P0 — “Don’t save history”.** History is always saved. A saved
  `history_enabled = false` is ignored and removed. People need a way to dictate
  without a local transcript database.
- [ ] **P0 — Explain data flow before the first upload.** Audio goes to the
  transcription provider. Text goes to the refinement provider when refinement
  is on. Final text goes to local history and the clipboard.
- [ ] **P0 — Require opt-in for Contributor models**, and explain that submitted
  text may be used for training. README mentions Muse Spark Contributor. The app
  does not gate it.
- [ ] **P0 — Keep retention, delete-all, and export easy to find.** These exist
  in History and Settings. **Verify** they stay obvious after onboarding.
- [ ] **P0 — State the limits.** Local history is not encrypted by the app.
  Clipboard managers and exports keep their own copies. `docs/privacy.md`
  already says this. **Verify** the app says it too.
- [ ] **P0 — Scan the repository and release packages** for secrets, recordings,
  transcripts, databases, and personal config.
- [ ] **P0 — Confirm logs and errors omit audio, transcripts, prompts, and
  keys.** Current design claims this. **Verify.**
- [ ] **P0 — Use the same privacy wording** in onboarding, the app, the README,
  and package descriptions.

## 5. Testing and release

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
