# Design final: onboarding (after second fixes)

Independent re-rating by Muse Spark 1.3 Contributor. Scope: the four setup
stages only — rendered quality in fresh captures plus the current
gating/key/storage/cancel/practice/accessibility logic as traced in present
source. No application code was edited for this review, and no sub-agent was
delegated.

Evidence convention: **rendered** = seen in the PNG captures listed below;
**traced** = read in current source; **tested** = covered by the current
suite; **untested** = no covering test found. The re-review
(`design-review` → `design-rereview-onboarding.md`) scored onboarding 8.5
rendered / 7.5 flow; its line references are historical and were re-verified
below against the present checkout.

## Scores (honest, uninflated)

| Area | Score | One-line reason |
| --- | --- | --- |
| Rendered onboarding (4 screens × wide/narrow × light/dark, standard text) | 9.0/10 | No breakage in any of the 16 shipped-size captures; prior copy/sparse-card nits fixed |
| Onboarding flow (gates, keys, cancel, retries, practice, a11y) | 8.8/10 | All three stranding traps repaired and tested; second-order residue remains |
| Launch acceptance readiness (**separate axis, not design**) | 6/10 | Seeded UI + mocked tests only; live provider/keyring/Orca/hardware/scaling still open |

The 9–9.5 target is market-quality native design: treated here as aspiration,
not a mandatory score. Rendered quality at shipped sizes reaches the floor of
that range; flow logic is close but held below 9 by the concrete residue in
§5. Readiness is deliberately not folded into the design scores.

## Evidence and limitations

- Inspected fresh captures (all dated this turn): `/tmp/caelum-design-wide/`
  (1100×760), `/tmp/caelum-design-narrow/` (480×640), and
  `/tmp/caelum-design-scaled/` (480×640 @ 1.5× font) — setup1–4 in both
  themes; wide/narrow/scaled dark viewed in full, both setup1 lights
  spot-checked.
- Capture method (per `design-validation.md`): a temporary modal window hosts
  the real native widgets at a controlled size, with mocked
  microphones/service/credentials and manually set stages. Captures omit the
  main header bar.
- What the screenshots do **not** show: real provider validation, real
  microphone input, real keyring dialogs, error/notice states, the expanded
  privacy text, busy/cancel states, focus rings in motion, or Orca behavior.
- Suite state: `/tmp/caelum-all-tests.log` (fresh this turn) reports
  **260 passed, 4 skipped**; `ruff check src tests scripts/capture_design.py`
  passes (re-run this turn) and `git diff --check` is clean (re-run this
  turn). I did not re-run the suite; test claims are from reading
  `tests/test_desktop.py` and `tests/test_onboarding.py`.
- No live provider, keyring, assistive-technology, or hardware verification
  is claimed anywhere in this report.

## Fix-by-fix verification

Each re-review blocker (§5 of the re-review) checked against present source,
tests, and renders. All `onboarding_ui.py` references are to the present
checkout.

1. **Stale pending key — FIXED and tested.** `advance()` now drops the
   current name's override when the entry is empty (600–604), and switching
   credential slots stashes-or-drops symmetrically (`select_key`, 230–240).
   The fail → clear → Continue case is covered natively
   (`test_desktop.py:427-430`: `"GROQ_API_KEY" not in setup.pending_keys`
   after clearing). The stored-good-key shadowing scenario from the
   re-review no longer reproduces by trace: an empty entry falls through to
   the stored credential via the missing check (629–630) and
   `providers.py:95-97`.
2. **Dual-key retry trap — control FIXED and tested; slot naming PARTIAL.**
   A credential selector appears when two keys are required (271–275), slot
   switches preserve the other slot's pending text (230–240), and the
   missing-key path jumps the selector to the unnamed slot with
   `Add the key for {missing}` (608–616). Repair-first-key is tested
   end to end (573–582). Remaining: a *validation failure* with both keys
   present still shows the provider error verbatim with no slot attribution,
   so the user must guess which of the two keys to repair (see §5.1).
   No longer a trap (both slots are reachable), but still guesswork.
3. **Stage-1 cancel — FIXED and tested.** The cancel action is labeled per
   stage (`Cancel validation` / `Cancel test`, 716) and visible on stages
   1/2/4 while busy (717). Validation polls the cancel flag inside
   `asyncio.wait` (633–644), cancels the in-flight task, and re-checks
   before any storage (646–654), so cancelled keys are never stored.
   Cancel-mid-validation is tested including the no-storage assertion
   (560–568).
4. **Contributor gating — preview FIXED; reset REMAINS.** Continue
   sensitivity now includes the visible-switch requirement (725–729), the
   row is labeled `(required for this model)` (215, 222), and the advance
   block message names the choice (590–592). Remaining: the switch still
   resets on *every* preset change (280), even between presets with the
   same consent scope (see §5.2).
5. **Practice note lifecycle — mostly FIXED; announce REMAINS.**
   Failure/cancel paths restore instructions instead of stranding phase
   text (156–159), the mis-jumping fallback now goes to the earliest
   incomplete stage (521–525), and the transcribing phase routes through
   the announcing notice (568–571). Remaining: live recording phases still
   write to `practice_note`, which has no announce hookup (558–566), and
   the restored instruction text is a shortened variant that drops the
   no-paste clause (see §5.3).
6. **Shortcut capture on Continue — FIXED, untested.** Stage-3 advance
   cancels capture and restores the token label before validating the
   saved chord (665–666). No test exercises capture-mid-Continue (see
   §5.6).
7. **Step semantics and focus — mostly FIXED.** Bars expose
   current/completed/upcoming accessible labels (731–735), and stage 2
   focuses the primary action instead of the `Test again` link (711–713).
   Remaining: no explicit focus move off `Cancel test` before it hides
   (see §5.4).
8. **Copy sweep — mostly FIXED.** Empty-state key note no longer claims
   storage before anything is stored (246–252; confirmed in all setup1
   renders); `Test again` shows only after a test (730; confirmed absent
   pre-test in setup2 renders); stage 4 has a real placeholder,
   `Your practice text will appear here.` (478–485; confirmed in setup4
   renders). Remaining: setup token labels still diverge from Settings
   `PRESETS` (`Groq` vs `Transcription only`, `desktop.py:100`), and the
   Advanced detour still abandons validated state without warning
   (see §5.5).

## Rendered assessment

Standard text, wide + narrow, both themes (16 captures): no layout
breakage, truncated text, or theme-contrast failure observed. Step chrome
is consistent; the fixed key note, gated `Test again`, and practice
placeholder all render as described above. Remaining nits at shipped
sizes: the focused key entry's underline-plus-outline double green line
still looks heavy at 480px, and consent can still be given without ever
expanding the privacy text (a design choice, not a defect).

Scaled stress (480×640 @ 1.5× font): setup2–4 hold up — content wraps and
fixed actions stay legible. **Setup1 does not**: in both themes the
scroll-content/footer boundary collides — the `How Caelum handles your
data` / `Back` line is partially obscured by the `Continue` button, and
the consent checkbox (a gate) sits below the fold. This contradicts the
`design-validation.md` claim of "fixed actions without text clipping at
those actual sizes" for setup1; that sentence should be corrected or
scoped to setup2–4. I treat 150% as scaling-acceptance backlog (the same
document already leaves exact-480px setup at 150%/200%, real desktop
scaling, and AT open), so it does not cap the shipped-size rendered
score — but it is a concrete, observed defect at that size, not a
hypothetical.

## Strengths

- Validate-then-store with in-memory candidates, entry preserved on
  failure, nothing persisted for rejected or cancelled keys — tested at
  both unit and native level, now including the clear-after-failure case.
- Dual-key flow graduated from a hidden-key trap to a selector with
  editable, slot-preserving candidates and missing-slot guidance — with a
  repair-first-key regression test.
- Cancellation is now a first-class stage-1 path: per-stage label,
  in-flight task cancel, pre-storage re-check, and a no-save test.
- Abandon path stays hardened (no draft persistence, secrets wiped,
  completion sticky); step semantics are programmatically exposed; mic
  focus lands on the primary action; practice fallback no longer
  over-jumps.
- Rendered onboarding at shipped sizes is clean and consistent across all
  four screens, both widths, and both themes.

## Remaining blockers (concrete, ordered)

None of these strands the user; together they are the distance to 9–9.5.

1. **Validation failure does not name the failing key slot.** Dual-key
   failure with both keys present shows the raw provider error; add the
   slot (and, when known, the Transcription/Refinement role) to the
   notice. Small; test with fail(both present) asserting slot attribution.
2. **Contributor switch resets on every preset change.**
   `change_provider` unconditionally clears it (280). Preserve the switch
   when the new preset keeps the same contributor scope.
3. **Recording-phase updates are not announced, and restored instructions
   are shortened.** Route `practice_level` through the announcing notice
   (or add the announce hookup to `practice_note`); restore the full
   instruction string including the no-paste clause.
4. **Focus is unmanaged when `Cancel test` hides.** Move focus to a
   stable control (primary action or notice) before hiding the cancel
   action.
5. **Copy residue.** Unify setup token labels with Settings `PRESETS`;
   make the Advanced-detour abandonment explicit in the link labels
   (e.g. noting that setup checks restart) or preserve validated state
   through the detour.
6. **Untested paths.** Capture-mid-Continue, level/processing callbacks,
   and cancel-focus behavior have no tests; existing mocks bypass exactly
   these branches.
7. **150% text: setup1 content/footer overlap.** Gate control below the
   fold with a colliding boundary (observed in both scaled setup1
   captures). Fix or scope the validation doc's no-clipping claim.

## Launch-readiness note (not part of the design score)

Unchanged in kind from the re-review: no live provider responses
(valid/invalid/quota), no real keyring accept/deny/locked dialogs, no
Orca or keyboard-only pass, no microphone hot-unplug, lock/suspend,
portal permission, clean-distro install, or signed-update evidence for
the setup path. Item 7 above joins that acceptance backlog for
text-scaling. Neither the design scores nor the passing suite certify a
launch.
