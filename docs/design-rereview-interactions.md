# Design re-review: interactions and accessibility

Scope: re-evaluation of the interaction/accessibility redesign in the working
tree at `/home/parththedevil/Projects/caelum` — `src/caelum/desktop.py`,
`src/caelum/onboarding_ui.py`, `src/caelum/desktop.css`, interaction tests,
and `docs/design-validation.md`. Independent re-review; no application code
was changed. Initial report `docs/design-review-interactions.md` (overall
6.0/10) describes the pre-redesign checkout; its line references are
historical and every finding below was re-verified against current source.
Freshly generated native screenshots in `/tmp/caelum-design-wide/` and
`/tmp/caelum-design-narrow/` (all of home/history/stats/settings/advanced
plus setup stages 1–4, both themes where named) were inspected as rendered
PNGs for this review.

Method limits (read first): screenshots show seeded widgets in a controlled
temporary window with mocked devices/status/credentials and manually selected
setup stages; the main header bar is omitted. They demonstrate layout and
reflow, not live provider, microphone, keyring, or timing behavior. No GUI
was driven, no Orca/keyboard-only/hardware pass was run, and no installed
competitor app was inspected — the Wispr Flow / Superwhisper notes in
`docs/design-validation.md` are public-page positioning direction, not
observed UI, and no competitor scores are claimed here.

## Scores (0–10, honest; interaction quality only)

| Area | Before | Now | Confidence |
| --- | --- | --- | --- |
| Keyboard access | 6.0 | 7.5 | High on code + screenshots; physical run still open |
| Focus management | 5.5 | 7.0 | High: gaps are visible in code |
| Responsive window sizing | 7.0 | 8.5 | High: both widths inspected as PNGs |
| Disabled / busy states | 7.0 | 8.0 | High, partly test-backed |
| Async races | 7.0 | 8.0 | High; one new edge case found (R-1) |
| Destructive actions | 5.0 | 8.5 | High, test-backed |
| Failure recovery | 5.5 | 8.0 | High, test-backed |
| Honest status | 5.0 | 8.5 | High: visible in code and screenshots |
| **Overall interaction quality** | **6.0** | **8.0** | Medium-high |

**Launch acceptance readiness is scored separately: not certified.** The
interaction fixes below are real and mostly tested, but Orca, physical
keyboard-only end-to-end, text scaling, microphone hot-unplug, lock/suspend,
portal behavior, clean-distro installs, and real provider/keyring acceptance
remain open exactly as listed in `docs/design-validation.md`. Nothing in
this report closes those gates.

The 9–9.5 market-quality target is not met for interactions. The gap is no
longer P0 breakage — all four initial P0s are repaired — but a tail of
P1/P2 focus, notice-system, and confirmation gaps plus one introduced test
flaw and one introduced (low-probability) robustness edge. The smallest pass
to close the gap is listed at the end.

## Strengths (verified in current code, tests, screenshots)

- **I-1 fixed: service status and lifecycle controls are visible and
  operable.** The pill is now appended to the layout
  (`desktop.py:737` in diff; current `build_home` area) instead of
  `set_visible(False)`; toplevel tests assert visibility and parenting
  (`tests/test_overview.py`). Wide home screenshot shows a visible "Ready"
  pill; the pause menu, tooltips, and AT label (`desktop.py:2155-2157`)
  ride on a reachable widget.
- **I-2 fixed: status and history refresh independently, with a regression
  test.** `refresh()` (`desktop.py:2081-2116`) runs a status worker plus a
  history-only worker; history `sqlite3.Error`/`OSError` yields a
  history-unavailable path that keeps dictation controls live and names
  history (`desktop.py:2206-2210`). The corrupt-SQLite native test asserts
  Retry/Cancel stay usable and recording state still renders.
- **I-3 fixed and visible: invalid keys keep the repair path.**
  `show_provider_status` (`desktop.py:1634-1647`) shows `Manage keys` for
  every non-ok, non-checking state; the invalid-key assertion is in
  `tests/test_settings_ui.py:117-119`, and the dark settings screenshot
  shows the missing-key warning with `Manage keys` and `Check connection`
  side by side.
- **I-4 fixed: single delete is confirmed and named.**
  `confirm_delete` (`desktop.py:2316-2334`) uses a modal with a safe
  default and destructive styling; Copy/Delete carry distinct
  per-date AT names (`desktop.py:2288-2294`). Cancel/Accept paths are
  covered by the new native test.
- **I-5 fixed: success states report.** The recovery block now shows for
  `success/unrefined/copied/saved/no_speech` as well as errors
  (`desktop.py:2198`), with the existing guidance detail; the wider
  detail line is gated by the recovery container so idle pages stay quiet.
- **I-8 fixed for the retry window: pending-audio Stop/Quit and key removal
  confirm.** `confirm_action` (`desktop.py:2013-2026`) backs
  `quit_caelum`/`stop_service` when `pending_audio` is set
  (`desktop.py:2028-2054`) and setup key removal with an explicit
  environment-fallback warning (`onboarding_ui.py:258-278`).
- **I-10 fixed: Retry/Cancel suppress duplicates in flight.**
  `run_control` (`desktop.py:2061-2079`) guards with `control_busy`,
  disables both buttons, and restores via `render_service`
  (`desktop.py:2172-2173`); the double-click single-request assertion is
  in `tests/test_overview.py`.
- **Key repair no longer destroys credentials on failure.**
  Candidate keys validate in memory via `credential_overrides`
  (`providers.py`, `onboarding.py`) and are stored only after success;
  rejected keys stay editable (`tests/test_desktop.py:420-425`) with a
  dedicated provider test that saved-credential lookup is never touched.
- **AT announcements exist where the toolkit supports them.** `message()`
  (`desktop.py:578-584`) announces on change, guarded against re-announcing
  the same 1-second-tick message; setup notices announce via
  `notify::label` (`onboarding_ui.py:91-96`). Search, chart (with a
  per-day text summary, `desktop.py:2260-2267`), and setup steps
  ("Step N of 4 · Name", `onboarding_ui.py:665`) are labeled.
- **Compact navigation keeps its contract.** Below 760px the rail Mapper
  hides labels visually but retains AT labels and tooltips
  (`desktop.py:489-506`, labels created at `:454-459`). Narrow
  screenshots confirm an icon-only rail with a visible selected state,
  a wrapping history toolbar, and readable reflow on home, settings,
  stats, and setup step 1.
- **Shortcut arming has an exit and no Tab trap.** The arming label reads
  "Keys… Esc cancels", and Tab/ISO_Left_Tab cancel capture while letting
  focus move (`desktop.py:1737-1743`, `onboarding_ui.py:398-404`). Setup
  practice shows recording/transcribing phases with a visible cancel
  (`onboarding_ui.py:516-534`).
- **Practice/setup focus exists:** stage changes move focus to the stage
  target (`onboarding_ui.py:656-660`) and history navigation focuses
  search (`desktop.py:569-570`); the history screenshot shows the focused
  search ring.

## Objections (remaining, scored into the 8.0)

### R-1 (P1, introduced): an unexpected status-worker exception freezes controls until restart

`status_ready` is the only path that resets `status_refreshing`
(`desktop.py:2092-2098`). If `status_read` raises anything outside
`(OSError, RuntimeError)` — the realistic case is `json.JSONDecodeError`
(a `ValueError`) from a malformed daemon reply in `request()`
(`desktop.py:26-37`) — `work()`'s error branch shows a message and
`status_ready` never runs, so `status_refreshing` sticks at `True` and no
further status render ever happens: pill, Retry/Cancel, pause, and record
sensitivity freeze. The old single-worker path reset its flag in a
`finally` (`end_refresh`), so this stuck-flag shape is new to the split.
Probability is low (healthy daemons return valid JSON) but impact is a
frozen control surface. Fix is one `try/finally` or `except Exception`.

### T-1 (P1, introduced, test-only): setup-flow retry path quits instead of retrying

`tests/test_desktop.py:390-496`: the devices-not-ready early `return True`
at lines 396-397 sits inside a `try` whose `finally` (lines 490-493) calls
`app.quit()`. If the 300ms verify tick fires before mocked devices load,
the test quits the app and passes with **zero assertions** — including the
new key-repair assertions — instead of re-arming. (Contrast
`tests/test_settings_ui.py:44-47`, where the same early return correctly
re-arms because no `finally` quits.) It likely proceeds on fast machines,
but the retry path is broken by construction. Fix: check devices before
the `try`.

### F-1 (P1): focus management is still partial

- `navigate()` moves focus only for history (`desktop.py:569-570`).
  Settings/Advanced/Home navigations — including Finish → home, where
  focus sat on a setup widget that is then removed from the stack —
  leave focus wherever it was, possibly on a hidden or destroyed control.
- Dialog close never restores focus (single-delete Cancel/Accept,
  Stop/Quit confirms, key-removal confirm).
- History row rebuilds still destroy the focused Copy/Delete on every
  signature change (`desktop.py:2226-2249`); the retry/cancel re-park
  (`desktop.py:2169-2171`) covers only the service buttons, and even
  there misses the case where Retry hides because recording *started*
  (state in the active list suppresses the re-park while Retry still
  hides). `clear()` still does not cancel `feedback_timer`
  (`desktop.py:962-981,2124-2126`).
- Setup stage 2 focuses the secondary "Test again" link rather than the
  primary "Test microphone" action (`onboarding_ui.py:659-660`).

### C-1 (P1): Stop/Quit mid-recording is still unconfirmed, and the stop message overclaims

Confirmation fires only when `pending_audio` is set (`desktop.py:2029,
2044`). Stopping or quitting during an active recording/processing pass
(listening/recording/processing/refining with no pending audio yet) still
discards in-progress work silently. Separately, the success message
"Dictation stopped. Pending audio discarded." (`desktop.py:2053`) is shown
even when nothing was pending.

### N-1 (P2): the notice system is still one unstyled, undismissable, unqueued label

`message()` announces (good) but errors and "Saved" remain visually
identical, rapid messages overwrite each other, and nothing is
dismissable — initial O-3 is unchanged. Concrete AT hole inside it:
settings autosave failures surface only in the `save_status` label
(`desktop.py:1845`), which never announces, so a failed save is silent
for screen-reader users.

### A-1 (P2): remaining AT/label gaps from I-7

Verified still open in current source: provider dot is a bare "●" label
with no state exposure (`desktop.py:1205`); the *settings* mic meter has
no accessible label (setup's equivalent got one,
`onboarding_ui.py:299`); setup progress bars expose "Step N" with no
current/completed state (partly mitigated by the new step label);
`toggle_pause` has no in-flight guard (rapid clicks can flap
pause/resume, unlike retry/cancel); usage calendar remains up to 31 Tab
stops with no arrow-key grid; sentence words remain separate labels.

### Smaller verified residuals

- S-1: the history worker catches `(sqlite3.Error, OSError)` but a
  `ValueError` (e.g. `fromisoformat` on a corrupt day string in
  `summary()`) escapes to `work()`'s generic branch with a cryptic raw
  message and skips the history-unavailable path. Catch-all to the
  `None` triple is the consistent fix.
- S-2: refresh now occupies **both** pool workers
  (`max_workers=2`, `desktop.py:323`) in steady state, so a control
  request (`run_control`, mic test, connection check) queues behind two
  workers instead of one. Fast ops make this negligible in practice, but
  the "keep one worker available" comment states the opposite of what
  the code does; `max_workers=3` is the one-line fix.
- S-3: `check_connection` still re-enables its button twice
  (`desktop.py:1697-1706`); `update_work` still silently drops
  re-entrant calls (`desktop.py:1428-1430`); `confirm_delete` does not
  return its dialog while `confirm_action` does; shortcut arming has no
  click-again-to-cancel path. All benign, all one-liners.
- S-4: per-frame tick callbacks remain (and grew by two: navigation at
  `desktop.py:490` and page adapt at `:540`). Correct but wasteful;
  size-allocate handlers remain the cleanup, non-blocking.

## Evidence and limitations

- Re-read in full in current form: `desktop.py` refresh/render/confirm/
  focus/announce paths (lines cited above), `onboarding_ui.py`
  (delete/advance/render/cancel/practice), `history.py` read/summary
  exception surface, `desktop.request`, and the `tests/test_desktop.py`,
  `tests/test_overview.py`, `tests/test_settings_ui.py`,
  `tests/test_providers.py` diffs.
- Inspected as rendered images: wide home/history/stats-dark/
  settings-dark/advanced/setup1-4-dark, and narrow home/history/
  stats-dark/settings-dark/setup1-dark. Usability reads: status pill
  present; search-first history with focused ring; destructive actions
  in red with safe-default modals (copy verified in code, dialogs not
  screenshotted); invalid/missing-key repair row with both actions;
  compact rail with retained selection; setup step labels and primary/
  Back/Resume-later placement consistent across stages. Narrow stats
  day labels sit tight to the viewport edge but the page scrolls, so
  this is not logged as a defect; narrow settings wraps the provider
  row into a slightly awkward orphan-dot column, acceptable.
- Not verified (unchanged from the initial review's check list): Orca
  announcements end to end, physical keyboard-only flows, the live
  Tab-while-arming path beyond code reading, text scaling, HUD
  click-through, real provider/keyring/daemon failures, and any
  side-by-side competitor behavior.

## Top actionable blockers to 9–9.5 (smallest implementable pass)

1. `tests/test_desktop.py`: move the devices early-return before the
   `try` so the retry path re-arms instead of quitting into a vacuous
   pass (T-1).
2. `refresh()` status worker: reset `status_refreshing` in a `finally`
   (or catch `Exception` → `None`) and add a native regression with a
   `request` mock raising `json.JSONDecodeError` asserting controls
   keep updating (R-1).
3. History worker: catch `Exception` into the `(None, None, None)`
   history-unavailable path; pool `max_workers` 2 → 3 (S-1, S-2).
4. Focus: move focus on every `navigate()` (page heading or first
   control), restore focus to the invoking Delete after confirm dialogs
   close, keep a stable focus target across history rebuilds, and focus
   the primary stage-2 action instead of "Test again" (F-1).
5. Confirm Stop/Quit while actively recording (states
   listening/recording/processing/refining), and make the stopped
   message conditional on audio actually being discarded (C-1).
6. Guard `toggle_pause` in flight; announce `save_status` failures;
   add severity styling plus dismiss to the notice; label the settings
   mic meter and expose or hide the provider dot from AT (N-1, A-1).
7. One-line hygiene: return the dialog from `confirm_delete`, collapse
   the double button re-enable, log `update_work` re-entry (S-3).

Hardware/launch qualification (Orca, keyboard-only, scaling, hot-unplug,
lock/suspend, portals, clean installs, real provider/keyring runs) stays a
separate gate and is not scored here; none of it is claimed by this
re-review.
