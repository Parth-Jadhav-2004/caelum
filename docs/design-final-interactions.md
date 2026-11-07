# Design final review: interactions and accessibility

Scope: independent re-rating of the interaction/accessibility work after the
second implementation pass, in the working tree at
`/home/parththedevil/Projects/caelum` — `src/caelum/desktop.py`,
`src/caelum/onboarding_ui.py`, interaction tests, `docs/design-validation.md`,
and the prior `docs/design-rereview-interactions.md` (overall 8.0/10).
No application code was changed for this review and no sub-agents were used.
All findings below were re-verified against current source; line numbers are
current-tree.

Method: full re-read of the refresh/render/confirm/focus/announce paths,
the `tests/test_overview.py` / `tests/test_desktop.py` /
`tests/test_settings_ui.py` diffs, and rendered-PNG inspection of fresh
captures (`/tmp/caelum-design-wide`, `/tmp/caelum-design-narrow`:
home-dark, history-light, settings-dark narrow, setup2-dark). Touched-area
native tests were executed in this session on the live display
(`GDK_BACKEND=x11 CAELUM_DESKTOP_TESTS=1 pytest`): `test_overview.py`
2 passed (including the new malformed-reply/active-Stop/Quit regression),
`test_desktop.py` + `test_settings_ui.py` 33 passed. The full-suite
260-passed figure in `docs/design-validation.md` was not re-run in full.

Method limits (read first): same as the re-review — seeded widgets, mocked
devices/status/credentials, no live provider/microphone/keyring/timing pass,
no Orca, no physical keyboard-only end-to-end, no hardware run. Dialogs and
notice behavior below are verified in code and (where stated) in tests, not
by driving the GUI.

## Scores (0–10, honest; interaction quality only)

| Area | Re-review | Now | Basis |
| --- | --- | --- | --- |
| Keyboard access | 7.5 | 8.0 | Dismiss added but strands focus (D-3); calendar still 31 stops |
| Focus management | 7.0 | 8.5 | Navigate-all, dialog restore, rebuild parking land; D-1/D-3/D-4 tail |
| Responsive window sizing | 8.5 | 8.5 | Unchanged; scaled captures add confidence, setup min-width caveat stands |
| Disabled / busy states | 8.0 | 8.5 | Pause runs through the guard; pause button shows no in-flight state |
| Async races | 8.0 | 8.5 | R-1/S-1 closed and tested; stale-confirm race D-5 remains |
| Destructive actions | 8.5 | 9.0 | Active Stop/Quit confirmed, cancel/accept tested; only D-1 focus tail |
| Failure recovery | 8.0 | 9.0 | Malformed-JSON recovery and history catch-all, both regression-tested |
| Honest status | 8.5 | 8.5 | Stop notice fixed; transient Stopped-on-malformed (D-2) offsets it |
| **Overall interaction quality** | **8.0** | **8.6** | Medium-high confidence |

**The 9–9.5 target is not met.** The gap is a short tail of small,
fully-specified focus/notice/status defects (D-1–D-7), not structural
breakage: every re-review P0/P1 functional item except the notice-system
core (severity/queue) is repaired and the repairs are tested. The 8.6
reflects that the remaining items are real user-facing papercuts with exact
repros, not polish. The minimal pass to close the gap is listed at the end.

**Launch acceptance readiness is scored separately: not certified.** Orca,
physical keyboard-only end-to-end, text scaling, microphone hot-unplug,
lock/suspend, portal behavior, clean-distro installs, and real
provider/keyring acceptance remain open exactly as listed in
`docs/design-validation.md`. Nothing here closes those gates.

## Verified fixes (second pass claims checked against source/tests)

- **Malformed-JSON status recovery: fixed and tested.** `status_read`
  catches `Exception` → `None` so `status_ready` always runs and resets
  `status_refreshing` (`desktop.py:2116-2124`). The native test raises
  `json.JSONDecodeError` from `request`, asserts `not
  app.status_refreshing`, then asserts a following refresh renders
  "Listening" (`tests/test_overview.py`, malformed block). Observed
  passing in this session.
- **Unexpected history-error fallback: fixed.** History `read()` catches
  `Exception` into the `(None, None, None)` history-unavailable path
  (`desktop.py:2132-2138`), so a `ValueError` from corrupt day strings
  now lands on the named path instead of the cryptic generic branch.
- **Third worker: done.** `max_workers=3` (`desktop.py:322`); the stale
  "keep one worker available" comment now matches reality.
- **Pause guard: done (logical).** `toggle_pause` routes through
  `run_control` (`desktop.py:2087-2108`); re-entrant pause/resume/cancel
  input while `control_busy` is a no-op. Residual: the pause menu item
  itself is never visibly disabled in flight (minor, D-8).
- **Setup-test readiness wait: fixed.** The devices-not-ready early return
  now sits before the `try` whose `finally` quits the app
  (`tests/test_desktop.py:392-394`), so the retry path re-arms instead of
  passing vacuously.
- **Active-recording Stop/Quit confirmation: fixed and tested.**
  `has_unsaved_audio` covers pending audio plus starting/listening/
  recording/processing/refining (`desktop.py:2054-2057`); both
  `stop_service` and `quit_caelum` confirm first. The native test walks
  Stop-cancel, Quit-cancel, Stop-accept and asserts `shutdown` fires only
  on accept. Observed passing.
- **Accurate stop notice: fixed and asserted.** Idle stop reports
  "Dictation service stopped." (`desktop.py:2084`); the test asserts the
  exact string.
- **Mapped dialog focus restore: done for `confirm_action` routes.**
  Origin is captured and restored only if still mapped
  (`desktop.py:2037-2047`); single delete returns its dialog
  (`desktop.py:2358-2365`) and key removal routes through `confirm_action`
  (`onboarding_ui.py:284-294`). Exception: `confirm_delete_all` is still
  bespoke — see D-1.
- **Navigate moves focus on every page: done.** History → search, home →
  status button, others → their nav button (`desktop.py:573-578`).
  Finish → home now lands on a live control instead of a removed setup
  widget. `navigate("setup")` resolves no nav target but `show()` focuses
  the key entry (`onboarding_ui.py:764`).
- **History rebuild focus/timer cleanup: done.** Rebuilds park focus on
  search (history page) or the status button (elsewhere) before clearing
  (`desktop.py:2268-2273`); `clear()` recursively cancels
  `feedback_timer` sources (`desktop.py:2153-2164`). One hole left: D-4.
- **Dismissable notice + autosave announcement: done (core).** The notice
  row carries a Dismiss action (`desktop.py:482-490`); `save_status`
  failures fan out to `message()` and therefore to the announcement path
  (`desktop.py:1424-1428`). Leftovers: D-3, D-6, D-7.
- **Mic meter label / provider-dot AT role: done.** Settings meter bars
  carry "Microphone input level" (`desktop.py:1192`); the decorative dot
  is `PRESENTATION` next to the text label (`desktop.py:1221-1225`).
- **Setup stage-2 primary focus + progress states: done.** Stage change
  focuses Next ("Test microphone") rather than "Test again"
  (`onboarding_ui.py:712-713`); progress bars expose
  current/completed/upcoming (`onboarding_ui.py:731-735`).

Screenshots (rendered PNGs) confirm: visible Ready pill and balanced home
columns at wide width; icon-only rail with selected state, wrapping
history toolbar, readable sentence-settings reflow at narrow width;
missing-key repair row with both actions; setup step labels with a
primary "Test microphone" action. No new layout defects observed.

## Remaining defects (scored into the 8.6)

### D-1 (P1): `confirm_delete_all` still neither restores focus nor returns its dialog

`confirm_delete` was converted to `confirm_action`, but
`confirm_delete_all` (`desktop.py:2367-2386`) still builds its own
`Gtk.MessageDialog` with no origin capture and no return value.
Exact scenario: keyboard to History → Tab to "Delete all" → Enter →
press Esc → focus is on no control (falls back to the window body) and
the next Tab restarts from the top of the page instead of returning to
"Delete all". Minimal fix: route it through `confirm_action` exactly
like `confirm_delete`, or capture `origin = self.window.get_focus()`,
restore on `get_mapped()`, and `return dialog`.

### D-2 (P2): one malformed status reply misreports "Stopped" for a cycle

`status_read` maps *every* exception to `None`, and
`render_service(None)` means "Stopped" (`desktop.py:2116-2124`,
`2166-2176`). Exact scenario: daemon healthy and recording, one
malformed reply (truncated socket line) → pill flips to "Stopped", pause
disables, then the next poll recovers to "Listening". Controls no longer
freeze (R-1 is fixed), but the pill asserts a false state with no
distinguishing message. Minimal fix: return a private `_READ_ERROR`
sentinel from `status_read` on exception and skip `render_service` for
that poll while still resetting `status_refreshing` (optionally show a
one-line "Status update missed; retrying" notice).

### D-3 (P2): activating Dismiss strands focus on the hidden button

Dismiss calls `message("")`, which hides `notice_row` including the
focused Dismiss button itself (`desktop.py:487-492`, `588-593`). Exact
scenario: any notice visible → Tab to Dismiss → Enter → the row hides
with focus on a hidden widget; the next Tab jumps unpredictably instead
of continuing from page content. Minimal fix: in the Dismiss callback,
park focus first — `(self.search if history visible else
self.status_button).grab_focus()` — then clear; also give Dismiss the AT
label "Dismiss notice" (currently bare "Dismiss").

### D-4 (P2): Cancel hiding while focused is not re-parked

`render_service` re-parks focus only for the Retry-hides case
(`desktop.py:2207-2209`). Exact scenario: focus the Cancel button during
an active recording → the recording completes (or the daemon stops), so
`cancel_button` hides while focused → focus is stranded on a hidden
control. Minimal fix: mirror the existing guard — if focus is Cancel and
Cancel is about to hide, `self.status_button.grab_focus()` first.

### D-5 (P2): Stop/Quit confirmation trusts possibly-stale poll state

`has_unsaved_audio` reads `last_service_status`, which is only as fresh
as the last poll (`desktop.py:2054-2057`). Exact scenario: start a
recording (portable Record, or hotkey), then invoke Stop/Quit before the
next status poll lands → last state still says idle → no confirmation,
in-progress audio discarded silently. Window is small but the action is
destructive. Minimal fix: decide in a worker — fetch one fresh
`request("status")` off the main thread, then `idle_add` either the
confirm dialog or the proceed path — instead of reading the cached
status. (Do not block the main thread with a synchronous request; the
socket timeout is 2s.)

### D-6 (P3): repeated identical failures are announced only once

`message()` announces only when the text or visibility changed
(`desktop.py:590-595`), and Dismiss does not reset `last_message`.
Exact scenario: autosave fails with "Not saved: …", user dismisses,
autosave fails again with the identical string → sighted users see the
notice return but screen-reader users hear nothing the second time.
Minimal fix: reset `last_message` when hiding, or always announce when
routing through the failure paths.

### D-7 (P2, known tail): notice is still one unstyled, unqueued label

Dismiss (D-3 aside) and autosave fan-out landed, but errors and
informational notes remain visually identical, rapid messages overwrite
each other (e.g. the history-unavailable message clobbers a storage
error), and nothing queues. Minimal fix is larger than the items above
(severity CSS class + a depth-1 pending slot); tracked as the last
piece of initial O-3/N-1.

### D-8 (P3): one-line hygiene leftovers

- `check_connection` still re-enables its button twice (`checked()` at
  `desktop.py:1721` plus the `finally` idle_add at `:1729`). Benign.
- `update_work` still silently drops re-entrant calls
  (`desktop.py:1451-1453`). Benign; log or disable the invoking control.
- Pause menu item never shows in-flight disabled state during
  `run_control` (input is suppressed, visuals are not).
- Usage calendar remains up to 31 Tab stops with no arrow-key grid;
  sentence words remain separate labels; shortcut arming has no
  click-again-to-cancel; per-frame tick callbacks grew rather than shrank
  (`desktop.py:512,552,852,1112,1440`) — correct but wasteful, still
  non-blocking.
- Edge: if the dialog-invoking widget is destroyed while a modal
  `confirm_action` dialog is open (a background refresh rebuilds history
  rows), `origin.get_mapped()` runs on a disposed widget. No crash
  observed in tests; a `get_root()` guard would close it.

## Evidence and limitations

- Re-read in current form: `desktop.py` refresh/render/confirm/focus/
  announce/notice/autosave paths (lines cited above), `onboarding_ui.py`
  delete/render/focus/progress paths, `desktop.request`, and the
  `test_overview.py` / `test_desktop.py` / `test_settings_ui.py` diffs.
- Executed in this session: `test_overview.py` 2 passed (covers corrupt
  history, malformed-reply recovery, single-delete cancel/accept,
  Stop/Quit cancel/accept, exact stop notice); `test_desktop.py` +
  `test_settings_ui.py` 33 passed. Full 260-test suite not re-run.
- Inspected as rendered images: wide home-dark, wide setup2-dark,
  narrow settings-dark, narrow history-light. Dialogs, live recording,
  and notice-row-visible states are not in the captures; those claims
  rest on code plus the native tests above.
- Not verified: Orca announcements end to end, physical keyboard-only
  flows, the live Tab-while-arming path beyond code reading, text
  scaling beyond the `--font-scale 1.5` captures, HUD click-through,
  real provider/keyring/daemon failures, and any competitor behavior.

## Top actionable blockers to 9–9.5 (smallest implementable pass)

1. Route `confirm_delete_all` through `confirm_action` (origin restore +
   return dialog) — D-1.
2. Park focus before Dismiss hides the notice row; label it "Dismiss
   notice" — D-3.
3. Re-park focus when Cancel hides while focused, mirroring Retry — D-4.
4. Skip `render_service` on status-read errors via a sentinel so a
   malformed reply never asserts "Stopped" — D-2.
5. Decide Stop/Quit confirmation on a fresh worker-fetched status rather
   than the cached poll — D-5.
6. Reset the announce gate when the notice hides so repeated failures
   re-announce — D-6.
7. Severity styling plus a depth-1 queue for the notice — D-7; then the
   D-8 one-liners.

Hardware/launch qualification (Orca, keyboard-only, scaling, hot-unplug,
lock/suspend, portals, clean installs, real provider/keyring runs) stays
a separate gate and is not scored here; none of it is claimed by this
final review.
