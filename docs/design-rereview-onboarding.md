# Design re-review: onboarding (post-redesign)

Independent re-evaluation by Muse Spark 1.3 Contributor. Scope: the four setup
stages only — rendered quality in all captured variants, plus the current
gating/key/storage/abandon/practice/accessibility logic as traced in present
source. No application code was edited for this review.

Evidence convention: **rendered** = seen in the PNG captures listed below;
**traced** = read in current source; **tested** = covered by the current suite;
**untested** = no covering test found. The initial report
(`design-review-onboarding.md`) scored onboarding 5.5/10 as a static review;
its line references are historical and were re-verified below.

## Scores (honest, uninflated)

| Area | Score | One-line reason |
| --- | --- | --- |
| Rendered onboarding (all 4 screens × wide/narrow × light/dark) | 8.5/10 | Clean, consistent, theme-coherent; no clipping; minor copy/density issues only |
| Onboarding flow (gates, keys, retries, abandon, practice, a11y) | 7.5/10 | Major traps fixed and tested; second-order logic/copy gaps remain |
| Launch acceptance readiness (**separate axis, not design**) | 6/10 | Seeded UI + mocked tests only; live provider/keyring/Orca/hardware still open |

The 9–9.5 target is market-quality native design. Rendered quality is close;
flow logic is not there yet because of the concrete issues in §5 (stale
pending-key override, hidden-first-key retry trap, no stage-1 cancel, plus
copy/a11y residue). Readiness is deliberately not folded into the design
scores: unperformed physical checks do not cap visual taste, and passing tests
plus screenshots do not certify a launch.

## Evidence and limitations

- Inspected all 16 setup captures with an image viewer:
  `/tmp/caelum-design-wide/setup{1,2,3,4}-{light,dark}.png` (1100×760) and
  `/tmp/caelum-design-narrow/setup{1,2,3,4}-{light,dark}.png` (480×640).
- Capture method (`scripts/capture_design.py`, traced): a temporary modal
  window hosts the real native widgets at a controlled size, with mocked
  microphones/service/credentials, seeded history, and stages set manually
  (`app.setup_window.stage = stage`). Captures omit the main header bar.
- What the screenshots do **not** show: real provider validation, real
  microphone input, real keyring dialogs, error/notice states, the expanded
  privacy text, busy/cancel states, focus rings in motion, or Orca behavior.
  Stage attractiveness is judged; stage *behavior* is judged from code/tests.
- Suite state as reported for this turn: 260 passed, 4 skipped
  (`GDK_BACKEND=x11 CAELUM_DESKTOP_TESTS=1 pytest -q`); `ruff` and
  `git diff --check` passed. I did not re-run the suite; test claims below
  are from reading `tests/test_desktop.py`, `tests/test_providers.py`, and
  `tests/test_onboarding.py`.
- Competitor note (per brief): public pages of Wispr Flow and Superwhisper
  were fetched this turn as positioning/interaction direction (polished
  writing, transformation examples, shortcut-led demo, modes). No competitor
  installed-app UI was observed; no competitor scores or side-by-side claims
  are made here.

## Rendered assessment: all four screens

Step chrome (all captures): a `Step N of 4 · Name` label plus four progress
bars sits top-left, `Resume later` top-right, `Back` bottom-left, and a green
primary action bottom-right. The step label fix over the initial review's
color-only progress reads well in every variant.

- **Stage 1 · Provider.** Headline `Use [Groq ▾] to turn your voice into
  text.`, orientation subline, large key entry (focused in captures),
  storage note, `Get a free key ↗` / `Custom provider` links, collapsed
  `How Caelum handles your data` expander, and the consent checkbox. Both
  themes are legible; dark-mode green tokens have good contrast. Narrow
  wraps cleanly (headline, consent over two lines). Residual nits: with no
  key stored the note still reads `Stored in your system keyring` (future
  fact stated as present); the focused entry's underline-plus-outline double
  green line looks heavy at 480px; privacy text requires expanding (fine,
  but consent can be given without ever opening it).
- **Stage 2 · Microphone.** Headline with `[System default ▾]` token, meter
  card with 18 bars, `The test stays on this device. Nothing is saved.`,
  right-aligned `Test again`, primary `Test microphone`. Best-looking step;
  identical structure across themes/sizes. Residual nit: before any test
  there are two visible test affordances (`Test again` link *and* the
  `Test microphone` primary) that do the same thing — mild duplication.
- **Stage 3 · Shortcut.** Headline `Choose [Super + Alt + V] to start
  dictation.`, one-line how-to (`Click the shortcut to change it. Press Esc
  to cancel a change. Portable desktops need a letter, number, or function
  key.`), `Desktop and shortcut options` link. Narrow wraps the token
  mid-sentence acceptably. No clipping in any variant.
- **Stage 4 · Practice.** Headline `Try [Super + Alt + V] and say hello.`,
  `Allow this practice upload.` checkbox, empty result card with a muted
  copy icon, instruction note naming click-to-record, no-paste, and Esc.
  `Finish` renders visibly disabled pre-success, which correctly previews
  the gate. Residual nit: the empty card (icon only, no placeholder line
  such as `Your words will appear here`) reads sparse, especially at
  480×640.

No layout breakage, truncated text, or theme-contrast failure was observed in
any of the 16 captures.

## Flow trace against current code

All references are to the present checkout.

**Gates (traced `src/caelum/onboarding_ui.py`).** Stage 1 requires the
consent checkbox (notice + insensitive Continue otherwise, 550–552, 671–674)
and, when the Contributor row is visible, its switch (553–555). Validation
collects missing keys before any network use (589–593), validates candidates
in memory (594), then stores and saves (597–603). Stage 2 runs the mic test
from Continue until `tested` (606–612); mic changes reset `tested`/`succeeded`
(327–333). Stage 3 checks the shortcut and saves before advancing (613–633).
Stage 4 enables Finish only after a successful practice (634–640, 671–674);
`run_practice` re-guards upload consent and `validated and tested` (481–488).
Completion is sticky once Finish is used (635–637; tested).

**Candidate validation/storage (traced + tested).** Pending entry text is
kept in `pending_keys` (563–566) and validated via
`validate_providers(config, pending_keys)` (`onboarding.py:52-64`), which
passes `credential_overrides` into `Providers` (`providers.py:75-76, 94-98`)
so saved credentials are not read for overridden names — directly tested
(`test_candidate_key_validation_does_not_read_or_replace_saved_key`). The
entry is cleared only on the success path (569–571); failures keep the typed
text and store nothing (tested: `setup.key_entry.get_text() == "test-key"`,
`stored == []`). `ProviderError` subclasses `RuntimeError` (`providers.py:26`),
so provider failures pass through `work()` with their specific message rather
than the generic fallback (141–145) — the initial review's worry here is
retired for known errors.

**Abandon behavior (traced + tested).** `finish_setup` (687–698) no longer
saves: it cancels work, clears `pending_keys`, wipes the key entry and
practice text, and detaches the page. Sidebar navigation out of setup
(`desktop.py:561-566`), `Resume later` (683–685), and the Advanced detour
(280–282) all funnel through it; tests assert presets are discarded,
secrets cleared, and completion preserved. README now matches reality
(`Resume later keeps validated settings; reopening starts with provider
checks and a fresh microphone test`). The saved `Progress.stage` remains
write-only for position (reopen always starts at stage 1, `onboarding_ui.py:47`)
but nothing now claims positional resume.

**Practice feedback/cancel (traced, partly untested).** Recording reports
phases through `practice_level` (521–529) and `practice_processing` (531–534);
a visible `Cancel test` button appears while busy on stages 2/4 (663–664,
516–519) alongside Esc handling (463–465, 475–476); cancellation raises
`Recording/Practice cancelled; sample discarded` (`onboarding.py:101-108,
133–135`). No test exercises cancel/level/processing paths (mocks bypass the
level callback) — an evidence gap, not a observed failure.

**Accessible step information (traced).** The `Step N of 4 · Name` label
(67–70, 665) plus stage-change focus moves (656–660) and notice announcements
(92–96) are genuine improvements. Bars still carry only static `Step N` labels
(60–66) with color-plus-active-class as the current indicator (675–679): text
is fixed, programmatic current-step state is not.

## Strengths

- Validate-then-store with in-memory candidates, entry preserved on failure,
  nothing persisted for rejected keys — tested at both unit and native level.
- Abandon path hardened: no draft persistence, secrets wiped, completion
  sticky, docs aligned with behavior.
- Distinct custom keys collected before a single validation; single-key and
  dual-key flows tested, including the unencrypted-file notice routed to the
  local notice area.
- Practice graduated from dead UI to phased text feedback with visible cancel
  plus documented Esc; click-to-record is primary in copy.
- Privacy text now reachable in-flow via expander; consent reworded as
  acknowledgment; step labels and focus management added; key removal gated
  by a destructive confirm that names the environment-fallback consequence.

## Objections: remaining logic and copy issues

Each item names a precise scenario reproducible against current code.

1. **Stale pending key shadows the entry and the keyring (logic).**
   `advance()` only writes `pending_keys[name]` when the entry is non-empty
   (563–566) and never drops it. Scenario: no stored key → paste `bad` →
   Continue fails (entry keeps `bad`, pending holds `bad`) → user clears the
   entry → Continue validates the *remembered* `bad` again and fails with an
   empty entry. Worse with a stored good key: paste `bad`, fail, clear,
   Continue — the stale override shadows the good stored credential through
   `providers.py:94-98`, so the user fails despite a working keyring key and
   an empty field. Only abandoning setup (which clears pending) recovers,
   undiscoverably.
2. **Dual-key retry trap: the first key becomes uneditable (logic).** With
   distinct STT/refinement keys and neither stored: paste k1 → Continue
   stashes k1, clears the entry, prompts for k2 (574–578) → paste k2 →
   Continue validates both and fails. `key_name` is k2's slot with no UI to
   return to k1's slot (`key_names` has no selector; Back is disabled on
   stage 1), and the failure need not name which key failed. Every retry
   re-sends the hidden bad k1; the only exits (preset switch, Resume later)
   discard *both* entries. Single-key Groq flow is unaffected.
3. **No in-flow cancel for stage-1 validation (logic).** `cancel_action` is
   visible only on stages 2/4 while busy (663). A slow/hung `validate_providers`
   network call leaves `Working…` with Back/Continue disabled; the only out
   is `Resume later`, which abandons setup entirely. Stage 3 has the same
   shape but is a fast local check; stage 1 is the gap.
4. **Contributor gate is enforced but not previewed (copy/logic).** `render()`
   desensitizes Continue for consent but not for the Contributor switch
   (671–674 vs 553–555), and the row label `Allow Contributor training use of
   my text` (210) carries no `required` marker though advance blocks without
   it. The switch also still resets on every preset change (254). Net: a
   Contributor-configured user sees an enabled Continue that then refuses.
5. **Practice note never returns to instructions and isn't announced (copy/a11y).**
   `practice_level`/`practice_processing` overwrite `practice_note`/notice
   (521–534), but failure/cancel paths leave phase text (`Recording… Speak
   into your microphone.`) as static idle content, and phase updates go to
   `practice_note`, which has no announce hookup (only `notice` does, 92–96).
6. **Continue during shortcut capture strands capture state (logic).** If the
   user clicks Continue mid-capture, `advance()` validates the old saved chord
   while `recording_key` stays true and the token keeps showing
   `Keys… Esc cancels` (391–409, 424–432, 613–633) — returning via Back shows
   a stuck capture label. Either cancel capture or block with a notice.
7. **Practice fallback jumps too far (logic).** `run_practice` with
   `validated and tested` false always resets to stage 1 (484–488), even when
   only the microphone test is missing. Rare path (Back/forward preserves
   flags), but the jump discards known-good position.
8. **Step bars still lack programmatic current state (a11y).** Visible text is
   fixed; the bars' accessible labels never change (64, 675–679). Also, stage 2
   focuses the secondary `Test again` link rather than the primary action on
   every entry (659), and focus is unmanaged when `Cancel test` hides.
9. **Small copy residue (copy).** Empty-state `key_note` claims `Stored in your
   system keyring` before anything is stored (226–231, visible in captures);
   `Test again` duplicates the pre-test primary (311–313, 666–670); setup token
   labels (`Groq · transcription only`, 239–241) still differ from Settings
   `PRESETS` (`Transcription only`, `desktop.py:101`); `open_settings` (280–282)
   abandons validated setup state without saying the Advanced detour restarts
   checks.
10. **Untested paths (evidence).** Cancel/level/processing (`cancel_test`,
    `practice_level`, `practice_processing`), the empty-entry-after-failure
    case, dual-key failure re-entry, and capture-mid-Continue have no tests;
    existing mocks bypass exactly these branches.

No evidence was found of the old critical defects recurring: invalid keys are
not stored before validation, abandonment persists no drafts, and completion
cannot be undone by reopening key setup (all tested).

## Top actionable blockers (to reach 9–9.5)

Smallest implementable next pass, in priority order:

1. Pending hygiene: when advancing stage 1 with an empty entry for the current
   name, drop `pending_keys[name]` so validation falls back to the stored
   credential; keep other names' pending values. Add a native test for
   fail → clear → Continue (empty must not re-validate the stale candidate;
   stored-good must pass).
2. Dual-key re-entry: on stage-1 validation failure with multiple `key_names`,
   name the failing slot in the notice and add an `Edit previous key` control
   (or key-slot selector) that swaps `key_name`, restores that slot's pending
   value into the entry, and preserves the other slot. Test fail(second key) →
   edit first → succeed.
3. Extend cancel to stage 1 (label it per stage: `Cancel validation` /
   `Cancel test`); the existing post-validation cancelled check (595–596)
   already prevents storing after cancel. Test cancel-mid-validation.
4. Contributor: include the visible-switch requirement in Continue sensitivity
   and mark the row required; preserve the switch across preset changes that
   keep the same consent scope.
5. Practice note lifecycle: snapshot instructions on `run_practice`, restore on
   failure/cancel/completion where appropriate, and route phase changes through
   the announcing notice (or add the announce hookup to `practice_note`).
6. Shortcut capture: if `recording_key` on Continue, cancel capture, restore the
   token label, and either proceed with the saved chord or stop with a notice —
   then test capture-mid-Continue and Back-visibility of the token.
7. Step semantics: update bar accessible labels on render (`Step 2, current
   step`) or expose the step label as a heading; focus the stage-2 primary
   action instead of `Test again`; move focus off `Cancel test` before hiding it.
8. Copy sweep: missing-key note (`No key saved yet. It will be stored in your
   system keyring.`); show `Test again` only after a test; unify preset labels
   with Settings; make the Advanced-detour abandonment explicit
   (`Desktop and shortcut options (restarts setup checks)` or preserve
   validated state through the detour); jump `run_practice`'s fallback to the
   earliest incomplete stage.

## Launch-readiness note (not part of the design score)

Unchanged in kind from `design-validation.md`: no live provider responses
(valid/invalid/quota), no real keyring accept/deny/locked dialogs, no Orca or
keyboard-only pass, no text-scaling/small-window physical check beyond the
480px captures, no mic hot-unplug, lock/suspend, portal permission, clean-distro
install, or signed-update evidence for the setup path. Items 1–3 above are the
design blockers; this paragraph is the acceptance backlog. Neither implies the
other.
