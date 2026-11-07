# Caelum interface redesign — overall design acceptance

Independent acceptance review by Muse Spark 1.3 Contributor. Scope: the
completed redesign as a whole — application visual quality, onboarding
appearance and flow, and interaction/accessibility logic — judged from the
current checkout, the current diff, and fresh native captures. No
application code was edited and no delegates were launched for this review.

Prior independent reports (all in this directory): rendered visual 9.0
(`design-final-visual.md`), onboarding appearance 9.0 / flow 8.8
(`design-final-onboarding.md`), interactions 8.6
(`design-final-interactions.md`). Those scores predate the final
corrections listed in `design-validation.md` ("Final corrections and
evidence"), which this review verifies and scores.

## Method and evidence

- Read `design-validation.md` and the three final reports above.
- Re-read the touched paths in the current tree: `src/caelum/desktop.py`
  (notice, confirm, focus, status, lifecycle), `src/caelum/onboarding_ui.py`
  (setup flow), `src/caelum/onboarding.py` (role-attributed validation),
  `src/caelum/hud.py` (state distinction), `src/caelum/desktop.css`
  (notice severity, setup footer), and the new/changed tests.
- Inspected fresh seeded native captures (mocked service, devices,
  credentials; captures omit the main header bar): `/tmp/caelum-design-wide`
  and `/tmp/caelum-design-narrow` (1100×760 and 480×640, all pages × both
  themes) and `/tmp/caelum-design-scaled` (480×640 @ 1.5× font stress).
  Viewed in full: wide home-dark, setup1-dark, setup4-dark, settings-dark,
  stats-dark; narrow setup1-dark, history-light, home-light; scaled
  setup1-dark, settings-dark.
- Suite state taken from `design-validation.md`: 261 passed, 4 skipped
  (opt-in native integration), ruff and diff-whitespace checks green. I did
  not re-run the suite; test claims below are from reading the tests.
- Contrast spot-check: recomputed the core sRGB token pairs from the actual
  palette in `desktop.py:1952-1976` and confirmed the documented figures
  (body/muted on page, danger on surface, token on wash, primary
  button pair) — all match, all ≥ 5:1. This is a token computation, not a
  rendered-widget audit.

What this review does not claim: live providers, keyring dialogs, real
microphone input, Orca end to end, physical keyboard-only flows, HUD on
hardware, OS-level scaling certification, or release qualification. Those
are separate gates (§5), not folded into the design scores.

## Scores (0–10, independent; the 9–9.5 aspiration did not set them)

| Area | Prior | Now | Basis |
| --- | --- | --- | --- |
| Application visual quality | 9.0 | 9.2 | No visible defect at shipped sizes; HUD distinction, footer, preset labels landed |
| Onboarding appearance | 9.0 | 9.2 | Clean 16-capture matrix; scaled setup1 boundary repaired |
| Onboarding flow and logic | 8.8 | 9.1 | All 7 residue items closed and tested; no stranding path left by trace |
| Interaction and accessibility logic | 8.6 | 9.1 | Entire D-1–D-5/D-7 tail repaired and tested; D-6 rejected as unsupported |
| **Overall design acceptance** | — | **9.1** | Launch-quality user-visible design; no material defect left |

Overall is a judgment, not a mean. 9.1 reflects that every concrete,
reproducible finding from the three final reports is either repaired with
a regression test or rejected on source evidence below, while systemic
polish (type scale, icon refinement, header observation, runtime HUD
evidence) still withholds anything higher. There is no material defect
preventing **design** acceptance.

## Acceptance decision

**ACCEPTED for design.** The current UI is coherent and launch-quality at
shipped sizes in both themes and widths: quiet green identity intact,
sentence-style settings readable, navigation compact without losing labels,
History search-first with confirmed deletions, Statistics clean with
guidance, setup explicit at every gate, service state and destructive
confirmations honest. This acceptance covers user-visible design and
traced logic correctness only; §5 lists the separate qualification gates
that still stand between this checkout and a public launch.

No installed-competitor comparison is made and no zero-bug state is
claimed: public pages (Wispr Flow, Superwhisper) were used only for
positioning direction, per `design-validation.md`, and passing tests plus
seeded captures cannot certify absence of bugs.

## Final-correction verification (traced in current source)

Interaction tail (prior D-1–D-5, D-7) — all fixed:

- Delete-all now routes through shared `confirm_action` with origin focus
  restore and a returned dialog (`desktop.py:2426-2432`, `2060-2076`),
  including the `get_root()` guard for the destroyed-invoker edge.
- Dismiss parks focus on search/nav/status before hiding, carries the
  "Dismiss notice" accessible label, and surfaces the pending slot after
  clearing (`desktop.py:589-600`, `487-488`).
- Cancel hiding while focused re-parks on the status button, mirroring
  Retry (`desktop.py:2264-2268`); setup's disappearing Cancel moves focus
  to Next before hiding (`onboarding_ui.py:730-733`).
- Malformed status replies return an `unavailable` sentinel, preserve the
  last known service state, and show a retry notice instead of asserting
  "Stopped" (`desktop.py:2163-2177`); the native test asserts Listening is
  preserved with the notice (`test_overview.py:208-219`).
- Stop/Quit confirmation fetches fresh status in a worker; unknown states
  require confirmation rather than risking silent discard
  (`desktop.py:2083-2101`); cached-idle→fresh-active is tested
  (`test_overview.py:242-264`).
- Pause runs through the control guard with visible busy state on
  retry/cancel/pause (`desktop.py:2134-2144`).
- Error notices carry a danger border (`.notice.error`, `desktop.css:191`)
  with a depth-1 pending slot so informational text cannot erase an error
  (`desktop.py:602-607`); retention and dismissal are tested
  (`test_overview.py:231-238`).

Onboarding residue (§5.1–§5.7 of the final onboarding report) — all fixed:

- Validation failures name the credential role and key
  (`onboarding.py:56-64`, e.g. `Refinement (REFINEMENT_KEY): …`), tested
  (`test_onboarding.py:130-138`).
- The Contributor switch preserves consent across preset changes within the
  same scope (`onboarding_ui.py:264-290`).
- Practice announces first detected speech through the announcing notice,
  and failures restore the full guidance string including the no-paste
  clause (`onboarding_ui.py:569-580`, `163-164`, `18-20`).
- Setup uses the same `PRESETS` names as Settings (`desktop.py:100`,
  `onboarding_ui.py:171-175`, `desktop.py:1231-1233`); detour links state
  "(restarts setup)" (`onboarding_ui.py:201,421`).
- Shortcut capture ends before advancing, with the token label restored —
  now covered natively (`test_desktop.py:460-465`).
- The scaled setup1 scroll/footer collision is repaired: opaque footer
  with separator (`desktop.css:193-194`), Back/Continue cleanly separated
  in the current scaled captures; gating controls below the fold require
  scrolling, which is correct graceful degradation at 150% font stress.

Visual tail — fixed in code:

- HUD Done/Unrefined render as a neutral check/label, distinct from the
  green live-recording fill (`hud.py:143-157`). Runtime HUD capture on
  hardware remains a separate gate (§5).

## Rejected prior finding

D-6 (repeated identical failures announced only once) does not reproduce
by source inspection and is rejected. `message("")` unconditionally sets
`last_message = text` (`desktop.py:617`), so after Dismiss the next
identical failure differs from `""`, `changed` is true, and the announce
path runs (`desktop.py:614-619`). The report's premise — that hiding does
not reset the gate — is contradicted by the current code.

## Remaining non-blocking polish

Deliberately brief: none of this is user-visible breakage or logic
incorrectness, and none moves the score. Arrows stay inside two text
labels; icons are unchanged but render cleanly; type is a reduced
inventory rather than a scale with no observed disharmony; the header bar
remains outside all captures so header appearance is unobserved either
way; D-8 hygiene (double button enable, silent re-entrant drop, up-to-31
calendar tab stops, per-frame tick callbacks) is benign. Scaled stress
shows expected graceful degradation (token ellipsis, below-fold controls,
setup minimum width above 480px). HUD runtime evidence is still owed (see
§5).

## Separate qualification gates (not design, not scored here)

Unchanged in kind from `design-validation.md`: real provider/keyring
acceptance, Orca and keyboard-only end-to-end, physical HUD/input
behavior, microphone hot-unplug, lock/suspend, GNOME/KDE portal behavior,
exact-480px setup at 150%/200% text, actual desktop scaling, clean-distro
installs, and signed updates. Historical core-engine/release findings in
`public-launch-remaining.md` stay outside this interface pass except A05,
already repaired. None of these gates is closed by this acceptance.
