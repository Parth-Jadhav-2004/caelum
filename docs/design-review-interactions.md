# Design review: interactions and accessibility

Scope: interaction logic and accessibility in `src/caelum/desktop.py`,
`src/caelum/onboarding_ui.py`, `src/caelum/hud.py`, `src/caelum/desktop.css`,
interaction tests under `tests/`, and launch acceptance docs
(`docs/acceptance.md`, `docs/public-launch-remaining.md`).
Static review only: no application code was changed, no GUI was driven, no
competitor build was inspected. No claim of zero bugs or launch readiness.

## Scores (0-10, honest, not inflated)

| Area | Score | Confidence |
| --- | --- | --- |
| Keyboard access | 6.0 | Medium-high: full source read; physical keyboard-only run still open |
| Focus management | 5.5 | Medium-high |
| Responsive window sizing | 7.0 | Medium: source + CSS read, min-width tests exist; no live resize check |
| Disabled / busy states | 7.0 | High: states are explicit in code and partly tested |
| Async races | 7.0 | High for guards; medium for timing edge cases |
| Destructive actions | 5.0 | High: paths are short and readable |
| Failure recovery | 5.5 | High for A05 (already reproduced in docs); medium elsewhere |
| Honest status | 5.0 | High: the gaps are visible in code |
| **Overall** | **6.0** | Medium-high |

Blockers to 9-9.5: restore service status and lifecycle controls in the window
(I-1), split service rendering from history reads (I-2 / A05), repair the
invalid-key path (I-3), confirm or undo single destructive deletes (I-4), add
focus guards and AT announcements (I-6, I-7), and complete the manual checks
(Orca, scales, keyboard-only, hardware). Items I-1-I-3 alone cap honest status
and failure recovery below 7.

## Top findings

### I-1 (P0): Service status pill is permanently hidden, so Start/Stop/Pause are unreachable in the window

`desktop.py:698` sets `status_button.set_visible(False)` and nothing ever sets
it back to visible (verified: the only other `status_button` references update
tooltip/label on the hidden widget, `desktop.py:2030-2031`). Consequences:

- The pill title computed in `render_data` (`desktop.py:2011-2022`:
  Stopped/Listening/Processing/Paused/Ready) is never displayed.
- Click (start/stop) and the right-click / Shift+F10 pause menu
  (`desktop.py:699-724`) are unreachable. `pause_button` sensitivity is still
  maintained (`desktop.py:2068-2069`) on a control no one can open.
- The only in-tree alternatives are the tray (`tray_dictation`, `quit_caelum`)
  and auto-start on launch (`ensure_service`). Window-only users cannot pause,
  stop, or restart dictation from the window.
- `tests/test_overview.py:113` even asserts the hidden state
  (`assert not app.status_button.get_visible()`), so the suite locks the defect in.

Recommendation: either show the pill (with its pause menu) or delete it and add
explicit Start/Stop/Pause controls plus a visible status line. Update the
overview test to assert the intended visibility and click behavior. This is a
product launch limitation, not redesign scope: lifecycle control must exist in
the window.

### I-2 (P0): A history failure freezes service controls (known A05, confirmed in code)

`Desktop.refresh` (`desktop.py:1977-1992`) bundles `request("status")` and three
history reads into one worker result. Any history exception routes through
`work()`'s error branch (`desktop.py:340-349`), which shows a message and never
calls `render_data`. So a corrupt/locked/unreadable database leaves recording
controls stale, with a generic "Operation failed..." message (sqlite errors are
not `ValueError`/`RuntimeError`, so the user gets no history pointer). The 1s
timer retries and fails the same way every second. `docs/acceptance.md` and
A05 already track this; the code path confirms it is still present.

Recommendation: fetch status and history independently; always render service
controls from status; show a distinct actionable history-storage error. Add a
native GTK regression with an invalid SQLite file plus healthy mocked daemon:
assert record/cancel/pause controls still update and the history error names
history. Launch limitation, not redesign.

### I-3 (P0): Invalid-key state hides the key-repair entry

`show_provider_status` (`desktop.py:1575-1588`) shows `Manage keys` only when
the text contains "missing"/"key unavailable". An *invalid* key produces the
error dot but hides the repair button, so the user sees "Invalid provider key"
with "Check connection" as the only action. This is the UI remainder of A09:
guidance copy was fixed, but the repair affordance disappears exactly when keys
need replacing.

Recommendation: keep `Manage keys` visible for every non-ok provider state
(missing, invalid, unavailable model where key rotation is plausible). Native
GTK test: invalid-key status -> `key_setup` visible -> opens setup.

### I-4 (P0): Single-history Delete is immediate and unrecoverable

Per-card Delete (`desktop.py:2137-2144`) deletes on click with no confirmation
and no undo, while Delete-all gets a modal with a safe default
(`desktop.py:2166-2184`). One misclick (or one keyboard slip in a long tab
chain of identical "Delete" buttons) permanently destroys a transcript.

Recommendation (pick one before launch): confirm single delete, or add
deleted-row undo within the session. Either way, give each Delete button a
distinct accessible name (date/words). Test: click Delete -> row retained until
confirm (or undo restores it). Launch limitation.

### I-5 (P1): Success states collapse to "Ready"; detail line only exists for errors

`render_data` maps `success/unrefined/copied/saved/no_speech` pill titles to
"Ready" (`desktop.py:2021-2022`) and only shows `status_detail` for
`state == "error"` (`desktop.py:2032-2033`, `2067`). The careful
`service_presentation` titles ("Done", "Copied", "Saved", "Done - unrefined")
never reach the home page except through error recovery. Combined with I-1
(hidden pill), a finished dictation shows no state change at all in the window.

Recommendation: show a transient result line (Done/Copied/Saved/unrefined with
the existing guidance) after completion, distinct from the error recovery block.
Test `render_data` for `saved/copied/success/unrefined/no_speech` states.

### I-6 (P1): Focus is never managed on navigation, rebuilds, or visibility flips

Good: setup grabs the key entry (`onboarding_ui.py:630`), inline edit grabs
focus (`desktop.py:1295-1297`), shortcut capture grabs focus (both files).

Gaps:

- `navigate()` (`desktop.py:529-542`) never moves focus. "View all" -> history,
  Finish -> home, dialog close -> content all leave focus wherever it was,
  possibly on a now-hidden control.
- `render_data` (`desktop.py:2043-2066`) flips retry/cancel/record visibility
  every second. A keyboard user tabbing toward Cancel can have it vanish (focus
  drops to the window) when the recording ends.
- Row rebuilds (`desktop.py:2086-2104`) destroy focused Copy/Delete buttons
  whenever the history signature changes.
- The recent-copy feedback timer (`desktop.py:930-941`) mutates unparented
  buttons after rebuilds; harmless today (unparented, not destroyed) but worth a
  guard.

Recommendation: move focus to the page heading (or first control) on `navigate`;
skip visibility flips for the focused control until blur, or re-park focus on a
stable sibling; clear `feedback_timer` in `clear()`. Tests: navigate moves
focus; hiding a focused Cancel re-parks focus; rebuild during focus keeps a
sane focus target.

### I-7 (P1): Screen-reader coverage is partial; no live announcements in the app

Present and good: accessible labels on nav, icon buttons, fields, switches,
usage days, setup consents, practice result (`desktop.py`/`onboarding_ui.py`
passim); HUD sets an accessible label and calls `announce()` on state change
(`hud.py:307-309`); recent-copy appears on `:focus-within` (`desktop.css:46-49`).

Missing:

- The global notice (`message()`, `desktop.py:544-546`) is a plain label: no
  live region, no `announce()`, no dismiss. Copy confirmations, save errors,
  mic-test results, and setup notices are silent for AT. (`copy_text`'s
  `announce` parameter only controls the visible message, not AT.)
- Setup step bars expose "Step N" labels but no current/completed state
  (`onboarding_ui.py:52-58`).
- `Gtk.SearchEntry` (history search), the stats chart `DrawingArea`
  (`desktop.py:990-993`, daily values have no text alternative), settings mic
  meter (setup's has a label, `onboarding_ui.py:260`; settings' does not), and
  the provider dot (decorative "circle", unread, should be hidden from AT) lack
  labels or alternatives.
- Sentence tokens other than theme have no accessible label; AT name falls back
  to the token text without sentence context. Each sentence word is a separate
  label (`desktop.py:1045-1058`), which may read word-by-word depending on the AT.
- Usage calendar is up to 31 Tab stops with no arrow-key grid navigation or skip
  link; history cards make long Copy/Delete tab chains with identical names.

Recommendation (launch slice): announce notice/message changes via
`Gtk.Accessible.announce`; mark the step state and provider dot; label search,
chart (plus a text summary of daily values), and settings meter; distinct
Delete/Copy names. Arrow-key calendar navigation and sentence AT-verbosity
tuning are redesign-adjacent follow-ups. Manual Orca run required either way
(open in `docs/acceptance.md:27`).

### I-8 (P1): Destructive or surprising actions without confirmation

- Stop service / Quit discard pending (retryable) audio with only an
  after-the-fact message (`desktop.py:1948-1960`; README documents it, but the
  UI never confirms). Quitting mid-retry-window destroys work the UI just asked
  the user to retry.
- Setup "Remove saved key" (`onboarding_ui.py:228-239`) is immediate and also
  writes a tombstone disabling environment fallback -- surprising blast radius
  for one click.
- "Discard queued update" (`desktop.py:1525-1532`) is immediate (low stakes,
  re-downloadable; acceptable, but log/confirm parity with the consented staging
  flow would be cleaner).

Recommendation: confirm Stop/Quit when `pending_audio` is true (offer
Retry-first); confirm key removal with one line stating the env-fallback effect.
Tests for both dialogs including Cancel-keeps-state.

### I-9 (P2): Shortcut recorder swallows keys with no on-screen exit hint in Settings

Both recorders consume every key while arming including Escape-to-cancel
(`desktop.py:1678-1718`, `onboarding_ui.py:355-389`). Setup shows "Release to
insert. Esc to cancel." (`onboarding_ui.py:342`, ambiguously about dictation,
not capture); Settings shows no hint at all. Tab while arming is consumed
rather than moving focus (whether GTK focus navigation pre-empts the controller
needs a live check), which is a mild keyboard trap; there is also no mouse path
to cancel arming besides completing a chord.

Recommendation: show "Press keys... (Esc to cancel)" on the token while arming,
let Tab/Escape cancel, and add a click-again-to-cancel path. Test: arming +
Escape restores the old hotkey (already covered in
`tests/test_settings_ui.py:49-54` for Escape) plus Tab behavior once verified
live.

### I-10 (P2): Retry/Cancel have no in-flight disabled state

`toggle_recording` disables its button during the request (`desktop.py:1885-1887`),
but retry/cancel (`desktop.py:737-742`) stay enabled; rapid clicks rely on
backend duplicate suppression. `update_work` likewise silently drops concurrent
calls (`desktop.py:1369-1371`), though all entry buttons are disabled while busy
so this is currently unreachable from the UI.

Recommendation: disable retry/cancel while their request is in flight (rely on
`refresh` to restore); make `update_work` re-entrancy log rather than silently
ignore. Test: double-click retry issues one request and disables until refresh.

### Smaller observations (verified in source)

- O-1: `check_connection` re-enables the button twice: in `checked()`
  (`desktop.py:1639`) and in the worker `finally` via idle_add (`desktop.py:1647`).
  Benign duplication; the generation guard (`1640`) correctly discards stale
  text. Collapse to one path.
- O-2: Portable shortcut label always reads "Hold X to dictate"
  (`desktop.py:667-672`), even where manual Record is the supported path; the
  error-free portable guidance ("Use Record...") exists only in
  `service_presentation`. Make the label backend-aware.
- O-3: The single global notice has no queue or dismiss; rapid messages
  overwrite each other and some persist until the next message. Add dismiss and
  severity styling (error vs info); today errors and "Saved" look identical.
- O-4: `Delete all` dialog (`desktop.py:2166-2184`) and update dialog
  (`desktop.py:1495-1523`) use safe defaults (Cancel) -- good -- but neither
  destructive button uses a destructive style class. One-line CSS addition.
- O-5: Responsive breakpoints (home <760, settings <760, footer <680;
  `desktop.py:789-801,1034-1040,1352-1358`) run as per-frame tick callbacks that
  always return True. Correct but wasteful; convert to size-allocate handlers.
  Content otherwise wraps well (SentenceLayout, FlowBox, clamped widths);
  remaining squeeze risks are the stats 2-column grid and the history toolbar
  row at 480px, both unexercised live (tests assert minimum widths, not wrapped
  appearance).
- O-6: History reads run three times per refresh tick plus on every keystroke
  (`desktop.py:1975-1988`). Fine at small DB sizes; consider debouncing search
  refreshes separately from the 1s status tick when splitting I-2.
- O-7: `begin_updates` disables the whole stack during install with a status
  line (`desktop.py:1454-1456`) and restores on error (`desktop.py:1404-1405`)
  -- good busy discipline. Setup is force-finished first; acceptable for a
  restart flow.
- O-8: Setup `Resume later` stays enabled during busy while Back/Next disable
  (`onboarding_ui.py:583-589`), and `finish_setup` correctly skips saving while
  busy (`605-617`). Good. Navigating away mid-setup also finishes setup
  (`desktop.py:529-534`); acceptable since drafts persist, but a busy-mid-validation
  navigation silently cancels validation -- surface a notice.
- O-9: HUD input handling is appropriately minimal: keyboard NONE, non-focusable,
  empty input region (`hud.py:67-83`), no transcripts accepted
  (`hud.py:234-283`), reduced-motion and high-contrast paths (`hud.py:61,135`),
  per-state dwell times (`hud.py:293-301`). Error dwell (5s) is short for slow
  readers, but the app home persists the error -- acceptable pairing once I-1/I-2
  are fixed. Physical click-through and screen-reader runs remain open
  (`docs/acceptance.md:25-27`).

## Directional benchmark note (Wispr Flow / Superwhisper)

No competitor build, screen, or recording was inspected for this review, so no
specific competitor behavior is claimed. Directionally, the dictation-app
category competes on: (1) always-available push-to-talk with trustworthy overlay
state; (2) hands-free insertion with a visible fallback; (3) a fast
dictate-verify-correct loop; (4) first-dictation success within minutes of
install. [All category claims in this paragraph are unverified inference, not
observed evidence.] Against that bar: Caelum's HUD pill, retry/cancel/expiry
model, unrefined labeling, and resumable setup are the right shapes; the gaps
that would show in any side-by-side are I-1 (no visible service state or
lifecycle control in the window), I-5 (no result feedback on success), no
post-dictation edit/correction loop beyond copy, and no in-window recording
control on the Hyprland path if the global hotkey fails. The last two are
roadmap/redesign scope; I-1 and I-5 are launch fixes.

## Recommended tests for material bugs

All native tests follow the existing `CAELUM_DESKTOP_TESTS=1` pattern.

1. Service controls visible and operable (I-1): status shown for
   stopped/ready/recording/processing/paused/error; start/stop/pause clicks hit
   the daemon; replace the hidden-pill assertion in `tests/test_overview.py`.
2. History failure independence (I-2): corrupt SQLite + healthy mocked daemon ->
   controls update, Cancel/Finish usable, history error names history.
3. Invalid-key repair (I-3): invalid-key status keeps `Manage keys` visible and
   it opens setup; retry after key replace preserves pending audio.
4. Single delete (I-4): confirm/undo behavior; distinct accessible names.
5. Result feedback (I-5): `render_data` for success/unrefined/copied/saved/
   no_speech shows the right line; error block stays hidden.
6. Focus (I-6): navigate moves focus; focused-control visibility flip re-parks
   focus; rebuild-during-focus keeps a valid target.
7. Announcements (I-7): notice/message changes invoke AT announcement; step
   state, search, chart summary, settings meter exposed (property-level asserts
   where Orca is unavailable).
8. Quit/Stop with pending audio (I-8): confirmation appears; Cancel preserves
   retry; key-removal confirm states the env-fallback effect.
9. Recorder (I-9): arming shows exit hint; Escape/Tab cancel; click cancels.
10. Retry/cancel in-flight (I-10): double-click issues one request; disabled
    until refresh.

## Launch limitations vs redesign scope

Launch (fix before wider rollout): I-1, I-2, I-3, I-4, I-5, I-6 focus guards,
I-7 launch slice (announcements + missing labels), I-8 confirmations, O-2/O-3/O-4.

Redesign / roadmap (do not block launch once the above land): post-dictation
in-app editing and correction loop; in-window manual recording on Hyprland as a
hotkey fallback; arrow-key calendar grid and list semantics for history;
sentence-AT verbosity tuning; notice center/queue design; global command
palette or voice commands; per-frame tick cleanup (O-5) can ride along anytime.

## Checks still needed (manual / hardware)

- Orca screen-reader pass over setup, settings, history, and error recovery;
  toolkit text scaling at 1.25x+; high-contrast theme (open: `docs/acceptance.md:27`).
- Keyboard-only end-to-end: setup to first dictation to retry to export, plus
  the Tab-while-arming question (I-9).
- Live resize across 480-1100px and 100/125/150/200% scales, mixed monitors,
  small work areas (open: `docs/acceptance.md:28`).
- Physical hotkey orders, autorepeat, rapid start/cancel/restart; real device
  unplug; lock/suspend; HUD crash and daemon kill recovery
  (open: `docs/acceptance.md:24-30`).
- Real provider error surfacing (invalid key, quota, rate limit) through the
  repaired I-3 path; two-version update with cancel/interrupt.
- Reconcile README's tray statements ("tray menu offers..." vs "A system tray
  icon" listed outside the preview) so support expectations match the shipped
  UI.

## Evidence and method

Read in full: `src/caelum/desktop.py` (2246 lines), `src/caelum/onboarding_ui.py`
(631), `src/caelum/hud.py` (358), `src/caelum/desktop.css`,
`tests/test_desktop.py`, `tests/test_overview.py`, `tests/test_settings_ui.py`,
`tests/test_desktop_lifecycle.py`, `tests/test_onboarding.py`, `README.md`,
`docs/acceptance.md`, `docs/public-launch-remaining.md`. Grepped all
accessible-label, sensitivity, visibility, focus, timer, and async-guard call
sites. Findings cite exact files and lines; anything requiring live GTK, AT, or
hardware is labeled as a check, not a verdict. Competitor remarks are
explicitly marked inference. Prior audit items referenced (A05, A09) were
re-verified against current source rather than assumed.
