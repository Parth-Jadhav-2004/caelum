# Caelum visual design re-review (rendered)

Scope: typography, spacing, hierarchy, palette, light/dark fidelity, populated
layouts, navigation, Statistics chart, HUD consistency. Re-evaluation of the
redesigned checkout against `docs/design-review-visual.md` (pre-redesign, 5.8/10;
its line references are historical).

Method: inspected current `src/caelum/desktop.css`, `src/caelum/desktop.py` theme
and layout code, the current `git diff`, and 10 freshly generated native PNG
screenshots rendered this turn (seeded widgets in a controlled temporary window,
mocked service/devices/credentials, manually selected setup stages; captures omit
the main header bar):

- `/tmp/caelum-design-wide/`: home-light, history-light, stats-dark,
  settings-dark, advanced-light, setup1-dark, setup4-dark (1100x760)
- `/tmp/caelum-design-narrow/`: home-light, history-light, settings-dark (480x640)

No live provider, microphone, or keyring validation is claimed. No competitor
installed app was observed; the Wispr Flow / Superwhisper page fetches this turn
are positioning direction only, with no competitor scores claimed. Suite status
taken from `docs/design-validation.md`: 260 passed, 4 skipped; ruff and
`git diff --check` clean. I did not re-run the suite (visual scope, read-only).

## Scores (0-10, honest, not target-fitted)

| Area | Initial | Now | Basis |
|---|---|---|---|
| Typography | 5.5 | 7.5 | System stack first, 15px base, tabular metrics; still no scale |
| Spacing / layout | 5.0 | 8.0 | One gutter rule, duplicates gone; renders evenly |
| Hierarchy | 6.0 | 8.0 | Status pill restored, toolbar wraps, chart rebuilt |
| Color | 6.0 | 8.0 | Token coverage much wider; setup primary now accent |
| Light / dark themes | 6.0 | 7.5 | Both themes render cleanly; two small leaks observed |
| Cross-page consistency | 5.0 | 7.5 | One scaffold rhythm; Settings/Advanced still two languages |
| Navigation | 6.5 | 7.5 | Compact icon nav works; header duplication remains |
| Recording HUD | 7.0 | 7.5 | Accent now green; success/live still share it; no HUD capture |
| Icons / brand mark | 6.0 | 6.0 | Unchanged; two rough glyphs, one icon size |
| **Overall rendered visual quality** | **5.8** | **8.2** | Coherent, tasteful native app; short of excellent on details |
| Launch acceptance readiness (design-gated) | n/a | 6.5 | Contrast, scaling, Orca, HUD runtime unverified — see limits |

Overall is a judgment, not a mean. 8.2 reflects what is on screen: a coherent,
quiet, genuinely pleasant native app with a distinctive sentence-Settings voice.
It is below the 9-9.5 excellent/market-quality target because of the concrete,
fixable issues below — most visibly the focus-ring leak and typographic loose
ends — not because of any structural problem. Readiness is scored separately and
lower because rendered screenshots cannot certify contrast ratios, text scaling,
assistive technology, or runtime HUD behavior.

## What is working (verified in renders)

- Home (wide + narrow): restored Ready pill with green dot, tabular 37 / 0.9
  metrics, clean Recent rows with copy affordances, full-month usage calendar
  with legend. Narrow stacks correctly under the compact icon rail.
- History: search-first toolbar wraps to two lines even at wide width; card
  metadata now uses structured `Nov 07 . 21:50 . 15 words . 18s` separators;
  Delete actions consistently danger-colored; narrow render has no clipping.
- Statistics (dark): accent-green bars on dark surface with gridlines, day axis,
  and value labels — the debug-chart complaint is resolved.
- Settings sentence UI (dark, both widths): striking and legible; mic meter,
  Test mic link, provider status row, switches all render in-voice.
- Setup stages: labeled steps ("Step 1 of 4 . Provider"), themed progress
  segments, accent Continue/Finish buttons, Back/Resume-later links; key entry
  shows a correct green focus treatment (`:focus-within` + underline).
- Token system genuinely widened: `accent_ink`, `accent_wash`, `accent_hover`,
  `danger`, `usage_1/2/3`, `usage_ink`, `switch_knob` now theme-defined in
  `apply_theme`; hardcoded component hex is largely gone from the CSS.
- Setup primary is now accent-filled, resolving the old dual-primary
  (ink-inverted vs green) split.
- HUD accent constant changed to `#6FD3A4` green (`hud.py`, one line), linking
  the overlay to the app palette.

## Objections / remaining issues (all observed, code-verified)

1. Focus ring leaks Adwaita blue for pointer focus. The History search entry in
   wide history-light shows a clearly blue outline. The stylesheet only styles
   `:focus-visible` (`desktop.css:63-65`); mouse/touch and `grab_focus()` focus
   matches `:focus` only, so everyday users see stock blue instead of the green
   accent. Small fix with high visibility: also style `:focus` for entries.
2. Detached comma in Settings. Wide settings-dark shows `Keep dictations for
   [30 days] , and start...` — the `", and start Caelum at login"` string is a
   separate FlowBox child (`desktop.py:1230-1231`), so the word gap lands before
   the comma. Attach the comma to the token or render it as punctuation without
   the leading gap.
3. Status-dot orphan at narrow width. Narrow settings-dark shows the amber `●`
   alone on its own line above "Transcription: ... key missing". The status row
   is a wrapping flow (`desktop.py:1204-1213`) with the dot as an independent
   child; keep dot+label together as one non-wrapping unit.
4. Zero-value chart labels add noise. Stats-dark prints a green `0` above every
   empty day. Suppress value labels for zero bars (keep the axis labels).
5. Stock blue checkbox in Advanced. Wide advanced-light shows an Adwaita-blue
   checked "Save dictation history" box next to a green switch — the one
   unthemed control in the page. The setup-page checkbox is already accent-
   styled (`desktop.css:155-158`); extend that treatment to Advanced.
6. Practice card is an empty cavern. Setup4-dark shows a large dark card with
   only a copy icon and no in-card hint; guidance sits below it. Add a muted
   placeholder line inside the card ("Your practice text will appear here").
7. Type scale still ad hoc. Base moved to 15px system-ui and metrics are
   tabular (good), but Title 28 / section 18 / sentence-token 30 / advanced 32
   / metric 48 remain an inventory, not a scale; only `overview-number` sets
   line-height. The 30px tokens wrap acceptably at 480px (verified), so this is
   polish, not breakage — but 9+ needs the scale.
8. Unchanged from the initial P2: `gear` polygon and `sidebar-collapse` 16px
   scaled construction (`desktop.py:603+`); duplicate header/sidebar wordmark;
   arrow-in-label back links; `border`/`divider` still two names for one dark
   value; HUD recording/success still share one color; no HUD runtime capture.

## Evidence and limitations

- Evidence: 10 native renders across both themes and both widths, current CSS
  and theme code, and the current diff. Every numbered issue above was both
  seen in a screenshot and traced to current source.
- Not evidence: header-bar appearance (omitted from captures), real-user data
  density, contrast ratios (not measured), text scaling >100%, Orca behavior,
  HUD on HiDPI/loDPI, stock dialogs, third-party GTK themes, or any competitor
  interface. The 8.2 rates rendered design quality only.
- The 6.5 readiness score reflects exactly those gaps plus the acceptance work
  already listed in `docs/design-validation.md` (physical input, portal
  behavior, clean installs, signed updates).

## Top actionable blockers to 9-9.5

1. Fix the `:focus` ring leak (issue 1) — the single most visible defect.
2. Typography pass: comma attachment, status-dot unit, zero-label suppression
   (issues 2-4) — one small editing session.
3. Theme the Advanced checkbox and add the practice-card placeholder
   (issues 5-6).
4. Adopt a reduced type scale (Title 24, section 16, tokens ~24-26) and confirm
   at 480px — the only item needing design judgment rather than repair.
5. Capture the HUD at runtime (recording/success/error, HiDPI + loDPI) and give
   success a distinct treatment from live recording.

None of these is structural. Issues 1-6 are the smallest implementable next
pass; issue 4's scale change plus a HUD capture would put an honest 9.0 in
reach. Icons/nav-duplication cleanup can follow without blocking that score.
