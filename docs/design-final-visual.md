# Caelum final visual design review (rendered, after second fixes)

Scope: typography, spacing, hierarchy, palette, light/dark fidelity,
populated layouts, navigation, Statistics chart, HUD consistency.
Final re-rating after the second implementation pass, against
`docs/design-rereview-visual.md` (8.2/10 rendered) and
`docs/design-review-visual.md` (pre-redesign, 5.8/10; its line references
are historical).

Method: inspected current `src/caelum/desktop.css`,
`src/caelum/desktop.py` theme/layout code, `src/caelum/hud.py`,
`src/caelum/onboarding_ui.py`, the current `git diff`, and 42 freshly
generated native PNG screenshots (seeded widgets in a controlled temporary
window, mocked service/devices/credentials; captures omit the main header
bar):

- `/tmp/caelum-design-wide/` (1100x760): all 18 — home, history, stats,
  settings, advanced, setup1-4, each in light and dark.
- `/tmp/caelum-design-narrow/` (480x640): all 18 — same matrix.
- `/tmp/caelum-design-scaled/` (480x640, `--font-scale 1.5`): 6 —
  settings-dark, home-light, history-light, stats-dark, setup1-dark,
  setup4-light.

No live provider, microphone, or keyring validation is claimed. No
competitor installed app was observed; no competitor scores are claimed.
Suite status taken from `docs/design-validation.md` (260 passed, 4
skipped; ruff and `git diff --check` clean). I did not re-run the suite
(visual scope, read-only, no implementation).

## Scores (0-10, honest, not target-fitted)

| Area | Initial | Re-review | Now | Basis |
|---|---|---|---|---|
| Typography | 5.5 | 7.5 | 8.5 | 24/26 reduction harmonious; still an inventory, not a scale |
| Spacing / layout | 5.0 | 8.0 | 8.5 | Even everywhere; scaled scrolls without overlap |
| Hierarchy | 6.0 | 8.0 | 9.0 | Dot attached, placeholder present, chart clean |
| Color | 6.0 | 8.0 | 9.0 | Focus accent, themed checkbox; HUD color-share remains |
| Light / dark themes | 6.0 | 7.5 | 9.0 | Both themes clean in all 36 normal captures; no leaks seen |
| Cross-page consistency | 5.0 | 7.5 | 8.5 | Checkbox unified, type reduced; arrow-labels/icons remain |
| Navigation | 6.5 | 7.5 | 8.0 | Compact rail verified at every narrow page; header unseen |
| Recording HUD | 7.0 | 7.5 | 7.5 | Unchanged code; fill/stroke distinction only; no capture |
| Icons / brand mark | 6.0 | 6.0 | 6.0 | Unchanged code; render cleanly at used sizes |
| **Overall rendered visual quality** | **5.8** | **8.2** | **9.0** | No visible defect left in normal renders; systemic nits remain |
| Launch acceptance readiness (design-gated) | n/a | 6.5 | 7.0 | Scaled stress exists now; contrast/AT/HUD-runtime still open |

Overall is a judgment, not a mean. 9.0 sits at the bottom of the 9-9.5
target range by judgment, not by fitting: every defect visible in the
re-review renders is gone from the current renders, verified fix by fix
below, but a true type scale, icon refinement, HUD state distinction with
runtime evidence, and header observation are still missing, which is what
withholds anything above 9.0. Readiness stays separate and lower because
screenshots cannot certify contrast ratios, assistive technology, runtime
HUD behavior, or real-device acceptance.

## Second-fix verification (each seen in renders and traced to source)

1. Focus/search-entry color — fixed. History search shows a green focus
   ring in wide and narrow, light and dark (previously Adwaita blue).
   Source: `desktop.css:64-65` now styles `:focus`/`:focus-within` for
   `entry` and `searchentry`, and `:focus-visible` uses
   `@caelum_accent` (`desktop.css:68`).
2. Type reduction — done as specified. Title 28→24, sentence/tokens
   32→26, setup headline 36→26, advanced title 32→24
   (`desktop.css:13,71,78,93,124`). Settings and setup headlines wrap
   gracefully at 480px in both themes; narrow setup3/setup4 two-line
   wraps read well.
3. Attached status dot — fixed. Narrow settings (both themes) now shows
   `● Transcription: GROQ_API_KEY key missing` as one unit; the orphan
   dot line is gone. Source: dot + label grouped in one box
   (`desktop.py:270-277`).
4. Detached comma — fixed. Wide settings (both themes) reads `Keep
   dictations for [30 days] and start Caelum at login`. Source: the
   leading-comma string is gone (`desktop.py:284-286`).
5. Zero chart labels — fixed. Stats (both themes, both widths) prints
   only the nonzero `37` above Saturday; empty days show day labels
   only. Source: value labels are emitted only `if words`
   (`desktop.py:1079-1080`).
6. Themed checkbox — fixed. Advanced "Save dictation history" is accent
   green in both themes, matching the switches. Source: the accent
   checkbox treatment moved from setup-scoped to global
   (`desktop.css:158-161`).
7. Practice placeholder — fixed. Setup4 shows `Your practice text will
   appear here.` inside the card in wide and narrow, both themes (wraps
   to two lines at narrow without clipping). Source:
   `onboarding_ui.py:478-484`, visibility bound to buffer content.

## What else the renders show

- Home, History, Statistics, Settings, Advanced, and all four setup
  stages are coherent and genuinely pleasant in both themes at both
  widths. The sentence-Settings voice survives the 26px reduction.
- Scaled (150% font) degrades gracefully: content scrolls, Back /
  Continue / Finish stay usable, no text overlap observed. Two
  graceful-degradation notes: the Settings provider token ellipsizes
  (`Transcription onl...`), and setup pages exceed 480px minimum width
  (key-entry focus-outline sides clip at the scrolled viewport edge;
  the footer itself is in normal flow below the scroller,
  `onboarding_ui.py:78-111`, so nothing overlaps).
- Narrow Advanced long values (provider URLs) sit at the right edge but
  are ellipsized by construction (`desktop.py:1293`), not clipped
  mid-glyph.
- Narrow stats day labels sit at the viewport bottom edge in the
  capture; that is capture scroll position, not a layout defect — the
  page scrolls.

## Remaining issues (all code-verified, none visible as a defect at normal size)

1. HUD recording/success still share one accent color
   (`hud.py:143-148`); recording fills while success strokes, which is
   the only distinction, and no HUD runtime capture exists. Unchanged
   since the re-review; the one item that most withholds a higher score.
2. Arrows remain inside text labels: `← Settings` (`desktop.py:1256`)
   and `Advanced →` (`desktop.py:1430`), visible in Advanced captures.
3. Icons unchanged: `gear` polygon and `sidebar-collapse` custom drawing
   (`desktop.py:597-666`); they render cleanly at the sizes used, so
   this is refinement, not breakage.
4. Type is a reduced inventory, not a scale: live sizes are
   12/13/14/15/17/18/20/24/26/32/48 (`desktop.css`), with line-height
   set only on `overview-number`. Section stays 18 against the
   re-review's suggested 16; no capture shows disharmony from this.
5. Header bar is omitted from all captures, so header/wordmark
   duplication is still unobserved either way. No evidence claimed.

## Remaining concrete blocker and smallest fix

No launch-blocking visual defect remains in the main app's rendered
output. The single item to close before design sign-off is issue 1:
give HUD success a color-distinct treatment from live recording (smallest
fix: keep the green fill for recording; render success/unrefined as a
neutral ink/white stroke with its existing Done label, one branch in
`hud.py:143-157`), and capture the HUD at runtime
(recording/success/error, HiDPI + loDPI). Everything else above is polish
that can follow without moving the score.

## Evidence and limitations

- Evidence: 42 native renders (full theme × width × page matrix at
  normal size, plus 6 scaled stress captures), current CSS/theme/layout
  code, and the current diff. Every fix claim above was both seen in a
  screenshot and traced to current source.
- Not evidence: header-bar appearance (omitted), real-user data density,
  contrast ratios (not measured), OS-level text scaling and 200%
  certification, Orca behavior, HUD on any display, stock dialogs,
  third-party GTK themes, or any competitor interface. The 9.0 rates
  rendered design quality only.
- The 7.0 readiness score reflects those gaps plus the acceptance work
  already listed in `docs/design-validation.md` (physical input, portal
  behavior, clean installs, signed updates).
