# Caelum UI elements and functionality reference

## Scope and baseline

This document inventories the user-facing desktop app: which pages, controls,
information, messages, dialogs, and conditional states exist and what they do.
It deliberately does not describe positioning, spacing, colors, or component
layout.

- **Baseline:** current repository working tree inspected on 7 November 2026,
  including uncommitted UI changes. This is not a promise that every listed
  element is in the currently published or locally installed package.
- **Included:** main application, onboarding/key management, recording feedback,
  tray integration, desktop notifications, and relevant system dialogs.
- **Excluded:** the marketing website, CLI-only commands as an interface, internal
  implementation widgets, and proposed features that are not implemented.
- Labels quoted here are current UI labels. Provider names, device names,
  shortcuts, dates, counts, versions, and error details are dynamic.

## Contents

1. [Shared application elements](#1-shared-application-elements)
2. [Home](#2-home)
3. [Statistics](#3-statistics)
4. [History](#4-history)
5. [Settings](#5-settings)
6. [Advanced settings](#6-advanced-settings)
7. [Onboarding and key management](#7-onboarding-and-key-management)
8. [Recording feedback overlay](#8-recording-feedback-overlay)
9. [System tray](#9-system-tray)
10. [Dialogs and external surfaces](#10-dialogs-and-external-surfaces)
11. [Notifications, errors, and recovery](#11-notifications-errors-and-recovery)
12. [Behavior and information boundaries](#12-behavior-and-information-boundaries)
13. [Implementation sources](#13-implementation-sources)

## 1. Shared application elements

### Identity and navigation

- **Caelum name and application icon:** identify the application and its window.
- **Home:** opens recording/service information, lifetime words, recording
  minutes, recent dictations, and the usage calendar.
- **Statistics:** opens usage totals and the daily activity chart.
- **History:** opens saved transcripts and search/export/delete actions.
- **Settings:** opens recording, provider, retention, login, appearance, and
  update controls.
- **Current-page indication:** identifies the active navigation destination.
  Advanced settings are treated as part of Settings; setup is a separate flow.
- **Toggle sidebar / Open sidebar / Close sidebar:** changes navigation
  visibility and saves that preference. Navigation remains available as named
  controls/tooltips when using its compact presentation.
- **Standard window controls:** supplied by the desktop/window decorations.

### Shared notices

- **Application notice:** shows informational feedback or actionable problems,
  such as copy confirmation, storage failure, setup completion, or save failure.
- **Dismiss:** clears the visible notice. If another notice was queued while an
  error was visible, dismissing the error reveals that queued notice.
- **Error-priority behavior:** a visible error is not immediately replaced by a
  newer unrelated message.
- **Accessible announcements:** changed notices and selected status messages are
  announced through GTK accessibility where supported.

### Application lifecycle

- Opening the application does not itself start a recording. Once setup is
  complete, the app normally ensures the dictation service is available.
- Closing the window hides it and keeps Caelum available when a registered
  system tray exists. Without that tray integration, the normal window-close
  lifecycle applies.
- **Quit Caelum** is available through the tray. Active or retryable work causes
  a discard confirmation before the application and service quit.

## 2. Home

### Dictation service status

- **Status control:** displays the current service condition and starts the
  service when stopped or stops it when running.
- **Status indicator:** accompanies the textual state; it is not a microphone
  device selector.
- **Displayed status values:**
  - **Stopped:** service is unavailable; starting it is required to record.
  - **Paused:** service exists but the shortcut is paused.
  - **Ready:** service is available outside an active recording/processing/error.
  - **Listening:** microphone startup, listening, or recording is in progress.
  - **Processing:** transcription or refinement is in progress.
  - **Awaiting retry:** processing failed but retryable audio remains in memory.
  - **Microphone unavailable:** microphone startup or capture failed.
  - **Recording failed:** a non-retryable recording error occurred.
- **Service action tooltip:** identifies Start service or Stop service and the
  method for opening pause/resume options.
- **Service context menu:** opens with right-click, the keyboard Menu key, or
  Shift+F10 on the status control.
- **Pause / Resume:** changes whether the service accepts recording shortcuts.
  This action is unavailable when the service is stopped.
- **Stop confirmation:** if work is active, stopping asks whether to discard it;
  an idle service can be stopped without that confirmation.

### Recording and recovery controls

- **Shortcut instruction:** shows the configured recording shortcut on the
  native backend, with a hold-to-dictate instruction. Portable mode instead
  instructs the user to use Record and paste the result.
- **Record:** shown for the portable backend; starts a recording when the
  service is ready and not paused.
- **Finish recording:** replaces Record during portable microphone startup or
  capture and finishes the recording for processing.
- **Retry dictation:** appears when a failed session has pending retryable audio.
  Retries processing that audio rather than requiring a new recording.
- **Cancel recording:** available for active recording or processing; cancels
  the current session.
- **Discard recording:** the cancel control's label when pending retry audio
  exists; discards that audio instead of retrying it.
- **Availability rules:** Record is disabled while paused, stopped, processing,
  refining, or holding pending retry audio. Retry/cancel requests are guarded
  against duplicate in-flight actions.

### Session detail and outcome messages

The Home recovery/detail area is shown for errors and completed outcomes. Its
text distinguishes:

- **Microphone preparation:** preparing to record.
- **Listening:** listening for speech, with no interim transcript shown.
- **Recording:** release the shortcut or finish recording to process.
- **Transcription / refinement:** transcribing the recording or refining
  punctuation and formatting.
- **Done:** refined text was sent to the original application.
- **Done · unrefined:** raw transcription was sent to the original application.
- **Copied:** paste manually into the intended application.
- **Saved:** use a saved transcript's Copy text action, then paste it.
- **No speech detected:** nothing was inserted; try another recording.
- **Retry errors:** specific guidance for a missing/invalid key, quota/billing,
  rate limit, offline connection, provider timeout, or unavailable model. The
  message explains that pending audio is in memory only.
- **Raw-result qualification:** saved/copied results can additionally state that
  refinement was skipped or unavailable.

### Usage totals

- **Words dictated:** cumulative lifetime word count from saved dictations.
  Deleting or expiring saved transcripts does not subtract from this total.
- **Minutes:** recording duration of the currently retained saved dictations,
  displayed in minutes to one decimal place. This is not a separate lifetime
  duration counter.

### Recent dictations

- **Recent dictations heading** and **Your latest five dictations** explanation.
- **Up to five most recent completed saved dictations:** independent of the
  search currently entered on the History page.
- Each item shows:
  - The local recording time; a tooltip provides the date and time.
  - The final transcript preview; its tooltip exposes the complete text.
  - **Copy dictation:** copies that transcript to the clipboard.
  - Temporary **Copied** checkmark/tooltip feedback after copying.
- **View all:** opens History.
- **Empty state:** explains that no dictations exist and prompts the user to
  hold the configured shortcut or choose Record, depending on the backend.

### Daily usage calendar

- **Daily usage heading** and current **month/year**.
- **Previous month / Next month:** browse calendar months. Browsing into future
  months is prevented, and Next month is disabled in the current month.
- **Weekday labels** and **date buttons:** identify days in the selected month.
- **Activity intensity:** represents words in saved dictations for each day.
  The implemented bands are zero, 1–99, 100–499, 500–999, and 1,000+ words.
- **Less / More legend:** explains relative activity intensity.
- **Day tooltip/accessibility description:** provides the day's word count and,
  for accessibility, its full date.
- **Selected-day detail:** shows the chosen date and number of words dictated.
- **Future dates:** cannot be selected.
- **Words from saved dictations:** explains the calendar's data source; deleted
  or expired history no longer contributes to these daily counts.

## 3. Statistics

- **Statistics title** and **Your dictation activity** description.
- **Words today:** words in retained saved dictations from the current local day.
- **Words this month:** words in retained saved dictations in the current local
  calendar month.
- **Total words:** cumulative lifetime saved-dictation word count, including
  words whose transcripts were later deleted or expired.
- **Words / recording minute:** retained saved words divided by their total
  recording duration. This is speaking/recording throughput, not processing speed.
- **Daily activity chart:** words for each of the latest seven local dates,
  including today. Shows weekday labels and counts for nonzero activity.
- **Chart empty state:** “Your first dictation starts the chart.”
- **Accessible chart description:** includes weekday names and word counts so
  that the data is not available only as drawn bars.
- There are no chart filter controls, selectable reporting periods, or visible
  cost/latency dashboards in this page's current implementation.

## 4. History

### Page information and actions

- **History title.**
- **Privacy description:** only completed dictations are stored locally; never
  microphone audio.
- **History status note:** explains automatic local saving and the retention
  period, or that history saving is off while old entries remain manageable.
- **Search your dictations:** searches final transcript text as the query changes.
  Matching is case-insensitive substring search. The current UI loads up to
  200 matching entries; it does not provide pagination controls.
- **Export history…:** opens a native save dialog for a JSON Lines export of
  retained history, not just the currently displayed search matches.
- **Delete all:** asks to permanently remove all saved local transcripts, not
  only the search results.

### Each saved dictation

- **Date and time:** shown in the local timezone.
- **Word count.**
- **Recording duration:** shown in seconds.
- **Final transcript:** readable, selectable text.
- **Copy text:** copies the full final transcript and shows a clipboard notice.
- **Delete:** opens a confirmation for that particular saved dictation.
- **Clipboard recovery label:** marks results that used clipboard recovery.
- **Unrefined transcript label:** marks an unrefined result when the clipboard
  recovery label is not taking that position.
- **Raw transcription · refinement skipped or unavailable:** additional
  explanatory text for every unrefined transcript.

### Empty and unavailable states

- **No dictations yet:** history saving is on but no entries exist.
- **No matching dictations:** a search has no results.
- **History saving is off:** explains that new dictations are not saved.
- **History unavailable:** directs the user to local storage and permissions.
  Recording/service controls remain available even when history cannot be read.

### Deletion and export information

- Deleting a transcript is permanent within Caelum.
- Deleting one or all entries does not erase clipboard copies, exported files,
  or lifetime word totals. Deleting all also removes the saved daily activity.
- Exported transcripts are private plain-text data; the app warns the user to
  choose a trusted destination and explains that later history deletion does
  not delete the exported copy.
- Export default filename: `caelum-history.jsonl`.
- Export completion notice: **History exported. Keep this file private.**
- Exports include stored record fields, not just the visible transcript text;
  these include timing/count information, provider model identifiers, and result
  flags. No microphone recording is included.

## 5. Settings

### Shortcut and microphone

- **Shortcut token/button:** displays the current shortcut and enters key-capture
  mode when clicked.
- **Key-capture prompt:** “Keys… Esc cancels.” A modifier-plus-key combination
  can be captured; supported modifier-only combinations require at least two
  modifiers. Backend validation still determines whether a shortcut is usable.
- **Escape:** cancels the pending shortcut change. Tab/Shift+Tab also leave
  capture without committing a new shortcut and allow keyboard navigation.
- **Microphone selector:** offers System default and detected input sources.
  Stores the chosen stable device identifier. Identically named PulseAudio
  sources are distinguished using their source names.
- **Configured but missing microphone entry:** preserves the preference and
  labels it “configured, not detected” rather than silently deleting it.
- **Microphone input-level meter:** visualizes input during a local mic test.
- **Test mic:** records a three-second local sample; disables itself during the
  test and resets the meter afterward. It does not save, play back, or upload
  the sample. An active recording must finish before testing.
- **Successful test notice:** audio was detected locally, nothing saved/uploaded.
- **No-speech notice:** asks the user to speak into the chosen mic and retry.
- **Failure notice:** reports device/capture problems instead of claiming success.
- **Bluetooth fallback behavior:** a selected Bluetooth source that disappears
  can fall back to an available built-in ALSA input, including during recording.
  The saved Bluetooth preference remains, so a subsequent recording can use it
  again after reconnection. This is capture behavior, not an extra UI switch;
  it does not mean a still-detected but stalled headset is automatically replaced.

### Transcription and text cleanup

- **Transcribe with provider selector:**
  - **Groq:** configures Groq transcription and optional refinement defaults.
  - **Transcription only:** configures transcription without refinement.
  - **Custom provider:** opens Advanced settings to edit provider details.
- **Tidy the text selector:**
  - **off:** disables refinement and retains raw transcription.
  - **lightly:** enables refinement with the lighter reasoning setting.
  - **thoroughly:** enables refinement with the higher reasoning setting.
  - Enabling cleanup can restore the previously selected refinement model or
    use `openai/gpt-oss-20b` if none is available in the draft.
- **Provider status indicator and text:** distinguish a locally found key from
  a verified connection, checking state, missing/unavailable credentials,
  unavailable models, and provider/network failures. “Key found” alone does not
  verify connectivity.
- **Manage keys:** appears when provider status needs attention and opens setup.
  Advanced also provides an explicit key-management action.
- **Check connection:** validates provider configuration, credentials, and
  configured model availability through provider model-list requests. It does
  not record or upload audio. The button is disabled while checking.
- **Successful connection feedback:** “Connected.” When multiple providers are
  checked, an actionable failure is prioritized over success text.
- Disabled refinement is treated as raw transcription, not a missing provider.

### Retention and desktop behavior

- **Keep dictations for … days:** opens a numeric retention control, with a
  supported range of 1–3,650 days. The chosen number is displayed in the token.
- **Start Caelum at login:** creates/enables or disables the user's autostart
  entry. Its current state reflects whether that entry exists.
- **Theme selector:** System, Light, or Dark. System follows desktop appearance;
  the selected preference is applied and saved.

### Saving and update information

- Settings save automatically; there is no main Save button.
- **Saving…:** changes are pending/in flight.
- **Saved:** the latest settings were persisted successfully.
- **Saved automatically:** normal settled save status.
- **Not saved: … / Could not save: …:** invalid configuration or persistence
  failures, also surfaced as an error notice.
- **Saved; service not updated: …:** the file was saved but the running service
  could not apply it. Active dictation may need to finish before settings reload.
- **Caelum version:** displays installed package metadata when available, with
  package-version/unknown fallbacks for other execution modes.
- **Update status:** up to date, checking, update available, update queued,
  downloading/verifying, installing/authorization required, discarded, or error.
- **Check:** manually checks updates; disabled without supported installed-package
  metadata. It is replaced by the update action when an update is available.
- **Update & restart:** downloads/verifies an available package after confirmation,
  or retries an already queued update. Requests administrator authorization for
  installation and restarts Caelum afterward.
- **Advanced →:** opens the Advanced settings page.
- Update actions are disabled while an update operation is running. Errors retain
  retry/discard options when a queued package remains.

## 6. Advanced settings

- **Advanced title** and **← Settings** return action.
- **Inline value controls:** clicking a displayed value opens its text editor.
  Enter or leaving the editor returns to value display; changes participate in
  automatic saving. Empty language is displayed as **auto-detect**; other empty
  fields use **off** as their display placeholder.

### Editable provider fields

- **Language:** transcription language, or automatic detection when blank.
- **Transcription URL:** OpenAI-compatible transcription provider base URL.
- **Transcription model:** model identifier for audio-to-text requests.
- **Transcription key variable:** credential name used to find/manage the key;
  this is not the secret key itself.
- **Refinement URL:** refinement provider base URL.
- **Refinement model:** model identifier for optional cleanup; blank disables it.
- **Refinement key variable:** credential name for refinement; may be shared with
  transcription or be a different name.
- **Reasoning effort:** textual provider reasoning setting; availability depends
  on the provider/model rather than representing a universal quality guarantee.

### History, credentials, launcher, and updates

- **Save dictation history:** enables/disables saving new completed transcripts.
  Existing history is not deleted when the option is turned off.
- **Check for updates when Caelum opens:** controls automatic update checks.
  An already queued update is handled separately on launch.
- **Key to manage selector:** lists distinct credential variable names needed by
  the configured transcription and enabled refinement providers.
- **Manage key:** opens provider setup targeting that selected credential, using
  the current Advanced draft after validation.
- **Add to app launcher:** installs the launcher entry and confirms completion.
- **Discard queued update:** shown when an update package is queued; removes it
  and reports **Queued update discarded.**

## 7. Onboarding and key management

### Flow-wide elements and rules

- Setup is embedded inside the application, not a separate standalone welcome
  window. It opens automatically when first-run setup is incomplete.
- Key management reuses this same flow; it is not a separate keys-only page.
- There are **four steps: Provider, Microphone, Shortcut, Practice**.
- **Step N of 4 · name:** identifies the current step.
- **Four progress indicators:** expose current/completed/upcoming step status.
- **Back:** moves to the preceding step; unavailable on step one or while busy.
- **Continue:** validates/advances the current step. Its label becomes
  **Test microphone**, **Working…**, or **Finish** where appropriate.
- **Resume later:** leaves setup and returns Home, cancelling active setup work.
  Entered secrets and practice text are cleared when the setup page closes.
- **Setup notice:** displays validation errors, progress, cancellation, consent
  requirements, and success feedback.
- **Busy behavior:** step inputs and advance/back controls are disabled during
  background operations. Cancellation remains available for validation/testing.
- Progress/completion metadata is saved, but reopening setup deliberately starts
  at Provider to revalidate access; the current implementation does not directly
  reopen the last saved numbered step.
- Completion requires validated providers, a successful local mic test, a
  checked shortcut, and a successful practice result.

### Step 1 — Provider

- **Use [provider] to turn your voice into text:** provider selector with Groq,
  Transcription only, and Custom provider choices.
- **Setup introduction:** connect the provider, check the microphone, and try
  dictation.
- **Credential to edit selector:** shown when separate transcription/refinement
  credentials are needed; selects which credential is being entered.
- **Provider API key field:** masked entry with a reveal/peek control. Its
  placeholder changes for a separate refinement credential. Enter invokes the
  same action as Continue.
- **Credential storage explanation:** distinguishes a system-keyring key, a key
  available from the environment, or an owner-only private file that is not
  encrypted. Existing saved secrets are not displayed in the input field.
- **Get a free key ↗:** opens Groq's API-key page when the transcription endpoint
  is recognized as Groq; hidden for other providers.
- **Custom provider (restarts setup):** exits setup and opens Advanced to edit
  provider fields. Returning to setup requires revalidation.
- **Remove saved key:** conditional action for a removable saved key. Opens a
  destructive confirmation; removal also disables environment fallback for that
  credential until a replacement is saved.
- **How Caelum handles your data expander:** reveals the privacy explanation:
  audio goes to transcription, optional refinement sends text, regular history
  can be disabled, practice text stays in setup unless copied, history is not
  encrypted, clipboard/export copies are independent, and provider limits apply.
- **Provider-processing consent checkbox:** explicitly permits sending audio/text
  to the selected providers. Continue is unavailable without it.
- **Contributor training consent switch:** shown only for a detected Contributor
  endpoint/model. Explains training use of text and is required to continue with
  that model. Acceptance is scoped to the exact endpoint/model.
- **Continue validation:** verifies every selected provider/model and required
  key. New keys are saved after successful validation, not merely after typing.
- **Missing-key feedback:** selects the missing credential and asks for its key.
- **Private-file fallback warning:** explicitly discloses when the keyring is
  unavailable and a new key is saved in an unencrypted owner-only private file.
- **Cancel validation:** appears while provider validation runs. Cancellation
  reports that validation was cancelled and keys were not saved.
- Changing provider resets the visit's validation/practice success and clears
  pending key entries.

### Step 2 — Microphone

- **Say something through [microphone]:** selector for System default and detected
  devices, preserving a configured missing device as **not detected**.
- **Microphone input-level meter:** reacts to local capture during the test.
- **Local-only explanation:** the test stays on this device and saves nothing.
- **Test microphone:** initial primary action starts a three-second local test.
- **Listening for three seconds…:** active-test progress notice.
- **Heard you clearly. Nothing is saved.:** a sample with detected speech passed.
- **No speech detected. Try again.:** the test must be repeated before continuing.
- **Test again:** appears after a successful test and allows retesting.
- **Continue:** becomes the primary action after the local test passes.
- **Cancel test:** cancels capture and discards the sample.
- Changing microphones invalidates the microphone/practice success for this
  visit. Active/retryable dictation must finish or be cancelled before setup tests.

### Step 3 — Shortcut

- **Choose [shortcut] to start dictation:** shows the current shortcut as an
  editable key-capture button.
- **Shortcut guidance:** click to change; Escape cancels a pending change.
  Portable desktops require a letter, number, or function/non-modifier key.
- **Keys… Esc cancels:** active capture prompt; Tab/Shift+Tab also leave capture
  without replacing the shortcut.
- **Desktop options (restarts setup):** exits to Advanced settings. It is a
  navigation action, not a separate backend-options dialog.
- **Continue:** validates/saves the shortcut and advances. Native Hyprland
  validation rejects a conflicting shortcut; portable approval/conflict handling
  can occur through the desktop when the service starts.
- This step does not itself silently grant desktop shortcut permissions.

### Step 4 — Practice

- **Try [shortcut] and say hello:** button labeled with the configured shortcut.
  Clicking it or pressing that shortcut while setup is active starts a bounded
  five-second practice recording; releasing the shortcut does not finish this
  timed practice sample early.
- **Allow this practice upload checkbox:** separate consent for the actual
  practice audio upload. Without it, recording is refused with an explanation.
- **Practice result text area:** read-only text result with a placeholder,
  **Your practice text will appear here.** No text is inserted into another app.
- **Copy practice text:** disabled until a successful result exists; copies the
  result explicitly and shows the clipboard privacy notice.
- **Practice guidance:** explains the five-second sample and Escape cancellation.
- **Recording for five seconds… Speak now.:** initial capture progress.
- **Recording… Speak into your microphone. / Speech detected.:** capture feedback.
- **Transcribing your sample… You can cancel at any time.:** provider processing.
- **Successful refined result:** explains that practice text stays here unless
  copied.
- **Successful plain result:** explains that refinement was off or unavailable.
- **No speech / provider / permission / network errors:** shown in setup notices
  and allow another attempt; they do not mark the flow complete.
- **Cancel test / Escape:** cancel an active practice operation. Cancel test
  changes feedback to **Cancelling…** while the cancellation is handled.
- **Finish:** enabled after success and completes setup, returns Home, and
  requests runtime settings reload.
- **Completion notices:** distinguish normal completion, needing to start the
  service, and needing a service restart to apply settings.
- Leaving setup clears the displayed practice transcript; practice is not added
  to regular saved history.

## 8. Recording feedback overlay

This is the native Wayland layer-shell feedback surface. Portable desktops use
desktop notifications instead. The overlay is passive: it does not take focus,
accept clicks, or provide clickable retry/cancel buttons.

### Capture information

- **Microphone activity indicator:** distinguishes listening and detected speech.
- **Input waveform/level history:** reacts to audio energy; not a live transcript.
- **Elapsed recording timer:** minutes and seconds.
- **Accessible microphone-active status:** exposed during listening/recording.
- **Reduced motion:** suppresses waveform motion and animated progress behavior
  when configured or desktop animation preferences require it.
- **High-contrast support:** available through configuration, not an exposed
  Settings switch in the current app.

### Processing and result states

- **Starting…:** microphone initialization, with a progress indicator.
- **Processing…:** transcription in progress, with a progress indicator.
- **Refining…:** text cleanup in progress.
- **Done:** successful refined result.
- **Done · unrefined:** successful raw result.
- **No speech:** no usable speech/result for insertion.
- **Copied · paste manually:** clipboard fallback/manual insertion is required.
- **Cancelled:** cancellation feedback; it dismisses immediately.
- **Retry or cancel:** generic error state; more specific labels include
  **Microphone unavailable**, **Connection lost**, **Could not insert**,
  **Capture interrupted**, and **Feedback unavailable**.
- **Hidden:** overlay is not presented outside relevant sessions.
- Capture/processing remains visible while active; completion and error feedback
  dismisses automatically. Default dwell times are approximately 0.65 seconds
  for done/unrefined, 0.8 seconds for no speech, 2 seconds for copied, and
  5 seconds for errors, followed by dismissal behavior.
- Transcripts and credentials are never displayed by, or sent into, this overlay.

## 9. System tray

- **Caelum tray icon:** desktop-dependent StatusNotifierItem integration.
- **Tooltip:** Caelum name plus current service status.
- **Open Caelum:** presents the main application window.
- **Settings:** presents the app and opens Settings.
- **Start dictation:** starts the service when stopped; it does not immediately
  record audio.
- **Pause dictation:** pauses the running service.
- **Resume dictation:** re-enables a paused service.
- Those three service actions share one menu entry whose label reflects state.
- **Quit Caelum:** quits the app and service, asking for discard confirmation if
  there is active or retryable work.
- If tray availability disappears, the application makes its window reachable
  again rather than depending on a missing tray icon.

## 10. Dialogs and external surfaces

### Destructive confirmations

These application confirmations default to cancellation. They offer **Cancel**
and the named destructive action, and restore the originating control's focus
when possible.

- **Delete this dictation? / Delete dictation:** permanently removes that saved
  transcript; explains that clipboard/export copies and lifetime totals remain.
- **Delete all saved dictations? / Delete all:** permanently removes saved local
  transcripts/daily activity, while keeping lifetime totals and external copies.
- **Remove the saved provider key? / Remove key:** explains that dictation with
  the key stops working and environment fallback is disabled until replacement.
- **Stop and discard this recording? / Discard and stop:** asks before stopping
  the service with active or retryable work.
- **Quit and discard this recording? / Discard and quit:** asks before quitting
  with active or retryable work.
- Lifecycle checks use fresh service status; if that status cannot be established,
  the app conservatively asks for confirmation rather than assuming no work exists.

### Export dialog

- **Export sensitive transcript history:** native save-file dialog.
- **Filename/destination controls:** provided by the operating system.
- **Export sensitive text:** confirms the destination/export.
- **Cancel:** closes the dialog without exporting.
- Default suggested file: `caelum-history.jsonl`.
- File-writing errors, including unsafe/unavailable destinations, are surfaced
  through the application's error/notice mechanism.

### Update confirmation and authorization

- **Download Caelum [version]?:** identifies the available version.
- **Explanation:** signed package download, administrator authorization,
  automatic restart, finish active dictation first, and preservation of
  settings/keys/history.
- **Later:** declines/defer the update; the default response.
- **Update & restart:** accepts download, verification, installation, and restart.
- **Administrator authorization prompt:** supplied by the desktop/system installer,
  not a Caelum password-entry field.
- Queued updates can request authorization again at a later launch. Cancellation
  or installation failure can leave the verified package queued for retry/discard.

### Desktop/provider surfaces

- **Global-shortcut permission/conflict dialogs:** provided by supporting portable
  desktops when registering the shortcut; approval can be declined. Manual
  Record/Finish recording remains the fallback.
- **Provider key website:** the onboarding key link opens the external Groq
  console; key creation is not embedded in Caelum.
- **System keyring interactions:** storage availability affects the disclosed
  storage mode. Any keyring unlock UI is supplied by the operating system.

## 11. Notifications, errors, and recovery

### Native recovery notification

- **Caelum · dictation paused:** appears for a retryable failure when desktop
  notification actions are supported.
- **Retry / Cancel:** retry processing or discard the pending recording.
- **Memory/expiry explanation:** pending audio expires in memory; it is not a
  durable recording saved to disk.
- If actionable notifications are unavailable, text guidance points to recovery
  options; the main app's Retry/Discard controls remain relevant.
- **Retry-window expiry notice:** reports that pending audio was discarded and a
  new recording is required. Default retry retention is 60 seconds, configurable
  outside the current UI.

### Portable recording notifications

- **Recording:** release the shortcut or choose Finish recording in Caelum.
- **Processing dictation…**
- **Cleaning up your words…**
- **Dictation saved:** open Caelum, choose Copy text, and paste where desired.
- **Dictation failed:** retry or cancel in Caelum.
- **No speech detected.**
- **Recording cancelled.**
- Recording notification is persistent while capture is active, subject to the
  notification server; later phase notifications replace it where supported.

### Additional operational messages

- Microphone unavailable, with configuration/device-access guidance.
- Capture interrupted; no text inserted; check the microphone and record again.
- Recording reached its configured maximum and was finalized.
- Recording stopped because native feedback is unavailable; restart Caelum.
- Target focus changed; text copied for manual paste into the intended app.
- Text copied because history is disabled in portable mode; paste manually.
- Sanitized provider errors: missing/invalid credentials, permission denied,
  unavailable model/endpoint, quota, rate limit, offline connection, timeout,
  credential-storage failure, or general provider unavailability.
- **Service status unavailable. Retrying…:** status could not be read; the app
  continues trying rather than claiming a confirmed stopped state.
- Service could not start; inspect credentials and desktop access.
- Dictation works but history could not be saved; check disk permissions.
- History could not be read; dictation controls remain available.
- Clipboard-copy privacy notice: clipboard managers may retain copied text.
- Launcher installation, settings-save/reload, setup completion, export, and
  update outcomes are reported through application notices/status text.

## 12. Behavior and information boundaries

- **Native recording:** hold the configured shortcut; releasing it initiates
  processing. Escape cancels on the native integration. Final text is sent to
  the original app when safe, otherwise copied for manual insertion.
- **Portable recording:** use an approved desktop shortcut or Record/Finish
  recording. With history enabled, results are saved for explicit copying from
  Caelum; with history disabled, results are copied for manual paste.
- **Practice recording:** a separate timed five-second sample, requiring explicit
  upload consent and never automatically inserted into another application.
- **No interim transcript:** the recording meter/overlay is audio feedback, not
  streaming transcript text.
- **Recording duration:** defaults to a 120-second cap; the current GUI does not
  expose a maximum-duration control.
- **History:** optional final text plus metadata, not stored microphone audio.
  Local history is not encrypted by Caelum. Expiration is enforced as history
  is accessed/written, not through a visible deletion countdown.
- **Usage:** lifetime saved words survive deletion; retained-history metrics and
  activity can decrease after deletion/retention. With history saving disabled,
  new dictations do not contribute to these saved-history totals.
- **Provider checks versus upload:** model/credential checks do not send a mic
  sample. Actual dictation and consented practice do send audio to providers.
- **Cleanup fallback:** refinement failure/off does not automatically discard an
  otherwise usable raw transcription; the UI identifies unrefined outcomes.
- **External copies:** exports and clipboard-manager entries are independent of
  Caelum history deletion.
- **Configuration-only functionality:** backend selection, recording strategy,
  chunking/concurrency, recording/retry limits, silence threshold, vocabulary,
  provider request timeouts, high contrast, reduced motion overrides, and pricing
  inputs are not separate editable controls in the current app GUI. Their
  existence in configuration should not be mistaken for additional UI pages.
- **No extra built-in pages:** there is no implemented dedicated About, billing,
  account/profile, vocabulary editor, audio library, live-transcript editor,
  separate update center, or standalone credentials list page. Version/update
  controls live in Settings; key editing reuses onboarding.

## 13. Implementation sources

The inventory was checked against these current source files rather than only
screenshots or older design proposals:

- `src/caelum/desktop.py`: navigation, pages, actions, notices, dialogs, status,
  settings autosave, key-management entry points, and updates.
- `src/caelum/onboarding_ui.py`: all four setup steps and their conditional controls.
- `src/caelum/onboarding.py`: privacy copy, validation, local tests, and practice.
- `src/caelum/hud.py`: native recording overlay contents and states.
- `src/caelum/tray.py`: tray icon, tooltip, and menu actions.
- `src/caelum/orchestrator.py`: recording outcomes, recovery, delivery, and notices.
- `src/caelum/portable.py`: portable recording/shortcut behavior and notifications.
- `src/caelum/linux.py`: native shortcut/cancel integration and actionable recovery
  notifications.
- `src/caelum/history.py`: saved-record fields, query limit, export, and metric meaning.
- `src/caelum/pulse.py`: microphone discovery, stable selection, and Bluetooth fallback.
- `src/caelum/providers.py`, `src/caelum/credentials.py`, `src/caelum/config.py`,
  and `src/caelum/updates.py`: supporting settings, validation, storage, and update
  semantics reflected in the UI.
