# Caelum visual design review

Scope: typography, spacing, hierarchy, color, light/dark, Home/History/Statistics/Settings
consistency, navigation, recording HUD, icons. Static review of
`src/caelum/desktop.py`, `src/caelum/desktop.css`, `src/caelum/hud.py`,
`src/caelum/icons/`, `src/caelum/onboarding_ui.py`, plus `README.md`,
`docs/product-page-design.md`, and `tests/test_desktop.py`,
`tests/test_overview.py`, `tests/test_settings_ui.py`.

Method: source and stylesheet inspection only. The GTK app was not launched and no
runtime screenshots were taken in this review turn. No competitor app was opened in
this turn. Competitor notes below are directional inferences labeled as such, except
where they cite `docs/product-page-design.md` lines 80-82. This review makes no
zero-bug or launch-readiness claim.

## Scores (0-10, honest, not target-fitted)

| Area | Score | Confidence | One-line basis |
|---|---|---|---|
| Typography | 5.5 | Medium | Coherent intent, no scale, three font stacks |
| Spacing / layout | 5.0 | Medium | Three page gutter systems, duplicate rules |
| Hierarchy | 6.0 | Medium | Home metrics and sentence-Settings are clear; History/Stats weaker |
| Color | 6.0 | Medium | Restrained green accent, but many hardcoded bypasses |
| Light / dark themes | 6.0 | Low-medium | Token-swap architecture is sound; dark leaks unverified at runtime |
| Cross-page consistency | 5.0 | Medium | Three scaffolds, three button languages, two card languages |
| Navigation | 6.5 | Medium | Quiet sidebar selection is good; header/brand duplication |
| Recording HUD | 7.0 | Low-medium | Best-crafted surface; weak link to app accent |
| Icons / brand mark | 6.0 | Medium | Simple waveform mark; custom nav glyphs uneven |
| **Overall visual design** | **5.8** | Medium | Restrained direction, unfinished system |

Overall is a judgment, not a mean. It sits below 6 because consistency, spacing
discipline, and token coverage are systemic, not one-screen issues.

## What is working

- Restrained native direction: quiet fills instead of outlines for selection
  (`desktop.css:26-29,162-164`), no heavy shadows except the HUD pill.
- Green accent (`#2F6F57` light / `#6FD3A4` dark, `desktop.py:1846-1850`) plus warm
  paper light background (`#F6F5F2`) is a plausible differentiator against the
  typical blue/dark dictation look.
- Sentence-Settings ("Hold X to talk") is distinctive and matches the product's
  plain-language tone (`desktop.py:1114-1115,1144,1171-1172`).
- HUD engineering is careful: layer-shell overlay, input-transparent, bottom-anchored,
  per-state dwell, reduced-motion and high-contrast flags (`hud.py:63-83,293-301`).
- Theme architecture (one `@define-color` block swapped in `apply_theme`,
  `desktop.py:1858-1878`) is the right GTK approach; tests pin the two ink values
  (`tests/test_overview.py:92-96`, `tests/test_settings_ui.py:76-78`).

## Findings by area

### 1. Typography

Evidence:

- Base stack is `Inter, system-ui, sans-serif` at 16px (`desktop.css:6`). Inter is
  named but not bundled or declared as a dependency in the inspected sources, so on
  most Linux systems this resolves to `system-ui`. That is acceptable, but the design
  intent (Inter metrics) is not what ships.
- Two other stacks coexist: HUD timer uses `monospace` and HUD labels use
  `Adwaita Sans` (`hud.py:169,179`); Statistics chart uses `Adwaita Sans`
  (`desktop.py:1000`). `docs/product-page-design.md:70` recommends Adwaita Sans with
  a bundled-webfont decision for web, which conflicts with the app's Inter-first CSS.
- Size inventory from `desktop.css`: 12 (captions, usage-day), 13 (recent-time,
  theme-menu), 14 (muted, settings-muted, recent-empty), 15 (status-pill, hotkey,
  recent-text, calendar-title), 16 (base, recent-text override), 17 (wordmark),
  18 (section-title, setup textview), 28 (title), 32 (metric, sentence,
  advanced-title, token buttons), 36 (setup-headline), 48-56 (overview-number).
  Only `overview-number` sets `line-height`. Weights used: 400, 500, 600, 650.
- Large numerals (`overview-number`, `metric`) use proportional text; no tabular
  figures, so values will shift width as they update (`desktop.css:16-17`).
- Shortcut label uses a Pango bold colored span (`desktop.py:670-672`); Settings
  inline values use monospace (`desktop.css:92-101`). Both are reasonable, but the
  shortcut is the product's most-repeated string and has no dedicated type style.

Assessment: 5.5. Intent is quiet and readable, but there is no type scale, no
line-height system, and three font authorities.

### 2. Spacing

Evidence:

- Three page gutter systems: `.page { 36px 40px }` for History/Statistics
  (`desktop.css:10`), `.overview { 32px 40px }` for Home with an earlier
  `44px 64px` rule overridden later (`desktop.css:11,176`), and
  `.sentence-page { 56px 72px }` with compact `32px 24px` for Settings/setup
  (`desktop.css:66,111`). A user moving Home -> History -> Settings sees three
  different left edges.
- Duplicate navigation rules: `.navigation { 28px 15px }` (`desktop.css:8`) then
  `{ 24px 12px }` (`desktop.css:162`); same for `headerbar button`,
  `.recent-row`, `.settings-footer`, `.overview-number`. Later rules win, but the
  file reads as two designs overlaid.
- One-off gaps: 9px word gap in `SentenceLayout` (`desktop.py:260`), 10/14px
  buttons, 22px panels, 28/24px overviews. No 4/8pt grid.
- `recent-list` and `usage-calendar` share `min-height: 340px`
  (`desktop.css:202`), which forces tall empty states to match each other rather
  than their content.

Assessment: 5.0. Spacing looks deliberate screen-by-screen but is not systematic.

### 3. Hierarchy

Evidence:

- Home (`desktop.py:674-801`): top row = session controls + right-aligned shortcut
  label; recovery box below; then two giant metrics; then Recent + Daily usage
  side by side, stacking below 760px. The metric-first order is good for a
  dictation habit product.
- Concern: `status_button` is created then `set_visible(False)`
  (`desktop.py:684-698`) and no inspected code path sets it visible again, while
  `render_data` keeps updating its label/tooltip (`desktop.py:2023-2031`). If that
  is current behavior, Home has no visible service pill and the top-left slot is
  controls-only. Verify at runtime; either remove the dead pill or restore it.
- History (`desktop.py:945-963`): heading + note + one horizontal row holding
  search + Statistics + Export + Delete-all. At the 480px minimum window width
  (`desktop.py:409`) this row will compress or clip; there is no wrap or overflow
  treatment. Cards use `.panel` with a metadata line built as one string with
  four-space separators (`desktop.py:2121-2127`), which is fragile hierarchy.
- Statistics (`desktop.py:965-1012`): 2x2 panels plus a custom Cairo bar chart.
  Bars are filled with the foreground text color, labels drawn at 11px with no
  axis, gridlines, or empty state (`desktop.py:996-1012`). It reads as a debug
  chart next to polished panels.
- Settings main vs Advanced: sentence UI with 32px tokens vs monospace
  inline-value rows with top/bottom hairlines (`desktop.css:70-75,89-101`).
  Individually fine, but the transition is abrupt; Advanced looks like a different
  app.

Assessment: 6.0. Home and sentence-Settings carry the score; History toolbar and
Statistics chart pull it down.

### 4. Color

Evidence:

- Semantic tokens exist for page/surface/ink/muted/border/divider/active/fill/
  accent/amber (`desktop.py:1858-1860`). Values are restrained and warm-neutral
  in light, near-black in dark (`desktop.py:1846-1850`).
- Hardcoded bypasses in `desktop.css`: token green `#E3EEE8`/`#D7E7DE` (light) and
  `#16251E` (dark override, `desktop.py:1862-1868`), error `#B43838`/`#FF8E8E`,
  setup track `#DAD8D1`, switch slider `white`, usage levels `#DCEAE1/#A9CBB9/
  #6AA386/#2F6F57` plus four dark overrides, status-dot base `#8A8984`.
  The token system therefore covers roughly the chrome, not the components.
- `border` and `divider` are identical in dark (`#26262B` twice) and near-identical
  in light (`#E4E2DC` vs `#EEECE6`), so they are one token wearing two names.
- Two competing "primary" signals: accent green for dots/switches/meters, but
  `setup-primary` is inverted ink-on-page (`desktop.css:139-142`). One of them
  should own the primary-action meaning.
- Focus uses `outline: 2px solid muted` (`desktop.css:61-63,108,151-153`). Muted
  is a text color, not a focus color; contrast of the outline against page and
  surface in both themes needs measuring.

Assessment: 6.0. Palette taste is good; system coverage is not.

### 5. Light / dark themes

Evidence:

- Selection follows System/Light/Dark with `gtk-interface-color-scheme` preferred
  and `gtk-theme-name` suffix fallback (`desktop.py:1836-1844`); live updates via
  settings notify signals (`desktop.py:1879-1882`). Correct approach.
- Dark adapts mostly through the token swap plus a small dark override block for
  tokens and provider-dot error (`desktop.py:1861-1868`) and usage-level overrides
  (`desktop.css:195-198`).
- Likely dark leaks (static reading, runtime check required): setup progress track
  `#DAD8D1` is a light gray with no dark override (`desktop.css:124`); token
  hover `#D7E7DE` is light-only with the dark override covering only the resting
  token background, so confirm hover in dark; HUD is intentionally always near-black
  (`hud.py:135`), which is correct for an overlay but means its gray-on-black text
  must be checked against the app's dark text scale.
- Entries, dropdowns, popovers inherit tokens (`desktop.css:50-60`), which should
  adapt, but stock GTK widgets (switches, checks, file chooser, message dialogs in
  `desktop.py:1495,2167,2187`) will still render partly in the system GTK theme.
  That is normal for a native app, but it means Caelum never fully owns dark mode;
  screenshots on at least Adwaita light/dark are required.

Assessment: 6.0 with low-medium confidence. Architecture earns the score; the
unverified leaks prevent more.

### 6. Cross-page consistency

Evidence:

- Page scaffolds: `build_home` uses `.overview` (`desktop.py:678`), `page()` uses
  `.page` (`desktop.py:506-517`), `settings_page()` uses `.sentence-page`
  (`desktop.py:1029-1043`), setup reuses `.sentence-page.setup-page`
  (`onboarding_ui.py:35-36`). Four page rhythms for five destinations.
- Buttons: default filled (`desktop.css:21-25`), `text-link` underline
  (`desktop.css:166-169`), `token` 32px pill (`desktop.css:70-77`), `setup-primary`
  inverted (`desktop.css:139-142`), `icon-button` 44px (`desktop.css:45`),
  `usage-day` cells (`desktop.css:186-194`). History uses filled Copy/Delete;
  Settings uses text-links for the same weight of action (Test mic, Check
  connection, Manage keys). Same hierarchy, different clothes.
- Cards: `.panel` (Stats, History cards), `.recent-list` + `.recent-row` (Home),
  `.usage-calendar` (Home), `.setup-card` (setup). Four radii (10/12/16/20px),
  three border treatments, inconsistent inner padding (16 vs 20/24 vs 22 vs 24).
- Captions under Home columns ("Your latest five dictations", "Words from saved
  dictations", `desktop.py:784,844`) have no counterpart on History/Statistics.

Assessment: 5.0. This is the largest visual debt: the app reads as three designs
(Home, History/Statistics, Settings/setup) sharing a palette.

### 7. Navigation

Evidence:

- Sidebar 184px with 44px nav-items, 22px line icons, 6px inter-item gap,
  selection as quiet fill + ink (`desktop.py:423-455`, `desktop.css:162-164`).
  Collapsible via header toggle, state persisted (`desktop.py:519-527`). Good,
  restrained, native-feeling.
- Brand appears twice: sidebar `wordmark` centered with 24px bottom margin
  (`desktop.py:426-429`) and header `wordmark` shown only when the sidebar is
  hidden (`desktop.py:419-420,471,523`). Two wordmark instances for one identity;
  the header variant exists only to fill the void left by the collapsed sidebar.
- HeaderBar is otherwise empty: no search, no status, no primary action
  (`desktop.py:411-421`). At 184px + toggle the chrome is minimal, which suits the
  product, but the empty bar plus hidden status pill leaves Home's top edge
  under-explained.
- `navigate("advanced")` keeps Settings selected (`desktop.py:535-542`) and
  Advanced offers a text back-link "Advanced →" / "← Settings"
  (`desktop.py:1179,1348`). Correct state handling; the arrow-in-label style is
  the weakest nav element (no icon, locale-fragile arrow).
- Revealer transition is `NONE` (`desktop.py:466`): instant collapse, no animation.
  Fine for reduced motion; slightly abrupt as the default.

Assessment: 6.5. The sidebar itself is the most resolved chrome in the app.

### 8. Recording HUD

Evidence (`src/caelum/hud.py`):

- Geometry: 280x96 surface, 232x48 pill, 24px radius, bottom-anchored with 8px
  margin (`hud.py:66,74,79-80,129`). Shadow built from six expanding strokes at
  0.018 alpha each (`hud.py:130-133`); 1px `#2E2E2E`-equivalent stroke on
  near-black fill (`hud.py:134-139`). Legible overlay treatment.
- Capture layout: hollow/filled dot + 17 waveform bars + monospace 13px `MM:SS`
  timer (`hud.py:155-172`). Idle layout: centered glyph + 13px label, shrinking to
  12px past 180px (`hud.py:173-216`). Glyph set covers starting/processing
  (spinner arc), success (check), refining (sparkle), error (triangle + dot),
  default (rounded rect). Thoughtful state coverage.
- Issues: (a) accent is light gray `#D8D8D8`-equivalent for recording/success and
  near-white otherwise, with pinkish error (`hud.py:143-152`) — the app's green
  accent never appears, so the HUD and app read as two products. (b) Recording
  and success share one color, so the most important transition (live -> done) has
  no color change. (c) "Done · unrefined" and "Copied · paste manually" are the
  longest labels; the 180px shrink-to-12 path has no ellipsis, so long translations
  may still overflow the 232px pill. (d) `high_contrast` only raises fill alpha to
  1.0 (`hud.py:135`); stroke, waveform, and error colors are unchanged, so the
  flag's visual effect is small. (e) Two x-origins (capture `x+24` vs idle `x+39`,
  `hud.py:153`) mean the pill's optical center shifts between states.
- Product-page direction (`docs/product-page-design.md:7,69`) proposes a sky-blue
  `#87BFEA` recording indicator on charcoal. That conflicts with both the current
  HUD grays and the app green. A single recording color must be chosen and used in
  both places.

Assessment: 7.0, low-medium confidence without runtime capture. Best-crafted
surface, weakest system link.

### 9. Icons and brand mark

Evidence:

- `icons/hicolor/scalable/apps/caelum.svg`: 40px rounded square `#171717`, five
  white rounded bars (waveform). `caelum-symbolic.svg`: same bars in `#2e3436` on
  transparent. Simple, legible, dictation-appropriate. Only `scalable/apps`
  shipped; no 16/24/32/48 pre-rendered sizes and no monochrome app-icon variant.
- Nav/action glyphs are hand-drawn Cairo strokes in `line_icon`
  (`desktop.py:548-651`): 12 glyphs on a 24 grid at 1.7 width, scaled to 22px.
  Consistent weight except `sidebar-collapse`, which scales a 16px-viewBox glyph
  by 1.5 at width 1.0 (`desktop.py:566-581`) — visibly different construction from
  its siblings. The `gear` glyph is a 32-vertex polygon (`desktop.py:596-602`),
  which will render lumpy at 22px next to the clean arcs of `clock`/`retry`.
- No use of the freedesktop symbolic theme for nav glyphs, so they will not track
  GNOME symbolic style/weight automatically. That is a deliberate custom-icon
  choice; it obliges the project to maintain the set.

Assessment: 6.0. Mark is good; maintenance burden and two rough glyphs cap it.

## Directional competitor note (do not treat as observed)

Verified repo evidence: `docs/product-page-design.md:80-82` records that Wispr Flow
was browsed for its benefit statement, primary download action, and speech-to-writing
demo, and Superwhisper for its concise promise and explicit platform downloads, with
the instruction to borrow clarity while keeping Caelum's own typography, desktop
scene, and copy. No competitor screens were inspected in this review turn, and no
pixel-level comparison is claimed.

Source-only directional inferences (low confidence, for positioning only):

- Both competitors are remembered in the market as one-action products: big promise,
  one download path, persistent recording affordance. Caelum's closest equivalents
  (sentence-Settings, HUD pill) are conceptually aligned but visually split across
  three languages; unifying them matters more than adding features.
- Caelum's warm-paper light theme and green accent are a plausible contrast to the
  dark/blue dictation default. Recommendation: keep the restraint, do not chase a
  glowing-waveform aesthetic the product-page doc already rejects (lines 74-76).

## Proposed token system: quiet native desktop

Goal: one semantic layer both themes share, no hardcoded component colors, HUD
linked to the app by a single recording hue.

### Semantic color tokens (light / dark)

Keep the current page/surface/ink/muted bones; rename and complete:

| Token | Light | Dark | Use |
|---|---|---|---|
| `page` | `#F6F5F2` (keep) | `#0B0B0D` (keep) | Window background |
| `surface` | `#FFFFFF` (keep) | `#151517` (keep) | Cards, rows, popovers, inputs |
| `surface-2` | `#F1F0EC` (current `fill`) | `#1D1D21` (new, between surface and fill) | Hover wells, calendar level-0 |
| `ink` | `#1B1B1A` (keep) | `#F2F2F3` (keep) | Primary text |
| `muted` | `#5E5D58` (keep) | `#9A9AA3` (keep) | Secondary text only, never focus |
| `line` | `#E4E2DC` (merge border+divider) | `#26262B` (merge) | All hairlines |
| `fill` | `#E9E7E0` (current `active`) | `#252528` (current `active`) | Selected nav, hover fills |
| `accent` | `#2F6F57` (keep) | `#6FD3A4` (keep) | Success, active recording link, switches |
| `accent-ink` | `#FFFFFF` | `#0B0B0D` | Text on accent fills |
| `accent-wash` | `#E3EEE8` (current token bg) | `#16251E` (current dark token bg) | Token pills, selected calendar top level |
| `warning` | `#9A6A23` (current amber) | `#CDA764` (current amber) | Paused, missing-key states |
| `danger` | `#B43838` (promote from hardcoded) | `#FF8E8E` (promote) | Errors, destructive confirm |
| `focus` | `#2F6F57` light / `#6FD3A4` dark (accent, not muted) | — | All focus outlines |
| `recording` | `#2F6F57` (same as accent light) | `#6FD3A4` (same as accent dark) | HUD live dot + waveform + app recording states |

Rules: delete `divider` (merge into `line`); delete `fill` vs `active` split (one
`fill`); move every hardcoded hex in `desktop.css` and the `desktop.py:1862-1868`
dark block into this table; HUD imports `recording` instead of its gray. Resolve
the sky-blue `#87BFEA` proposal in `product-page-design.md:69` explicitly: either
adopt it as `recording` everywhere (app + HUD + marketing) or drop it. Do not keep
green in-app, gray in-HUD, and blue in-docs.

### Type scale (system stack first)

Stack: `system-ui, "Adwaita Sans", Inter, sans-serif`; monospace: system mono for
timers, shortcuts, inline values. Rationale: ship what Linux has; stop naming an
unbundled Inter first.

| Role | Size / weight / line-height | Maps from |
|---|---|---|
| Display (Home metrics) | 48 / 600 / 1.0, tabular | `overview-number` |
| Headline (sentence, setup) | 30 / 600 / 1.15 | `sentence`, `setup-headline`, `advanced-title` |
| Title (page headings) | 24 / 600 / 1.2 | `title` (reduce from 28) |
| Section | 16 / 600 / 1.4 | `section-title` (reduce from 18) |
| Body | 15 / 400 / 1.5 | base (reduce from 16) |
| Secondary | 13 / 400 / 1.45 | `muted`, `settings-muted` |
| Caption | 12 / 400 / 1.4 | `calendar-caption`, `recent-time` |
| Token pill | 24 / 500 / 1.2 | sentence tokens (reduce from 32) |
| Mono | 13 / 400 / 1.4 | timers, shortcuts, inline values |

Token pills at 24px instead of 32px keep the sentence voice while fitting narrow
windows and reducing the Settings-vs-app size shock.

### Spacing, radius, motion

- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48. Page gutters: 40px desktop,
  24px below 760px — one rule for all pages. Card padding 20px. Row min-height 44px.
- Radius: 8 controls, 12 popovers/nav, 16 cards, 999 pill only. Retire 10/14/20.
- Motion: keep HUD 150-180ms ease-out; give the sidebar the same fade (not `NONE`)
  with `prefers-reduced-motion` / `gtk-enable-animations` off-switch already
  respected by the HUD.

## Specific layout changes (implementable)

1. One page scaffold. Give Home, History, Statistics, Settings, and Advanced the
   same scrolled body: 40px/24px gutters, 8px heading-to-description gap, 24px
   section rhythm. Implement by parameterizing `page()` (`desktop.py:506-517`)
   instead of maintaining `.page` / `.overview` / `.sentence-page` as rivals.
2. Restore or remove the Home status pill. Decide whether `status_button`
   (`desktop.py:684-698`) is dead code or a hidden feature; either delete it and
   let the top row be controls + shortcut, or show it with Ready/Listening/
   Processing/Paused/Stopped states so Home answers "is it on?" at a glance.
3. History toolbar: wrap on narrow. Put search on its own line below 680px with
   Export / Delete-all / Statistics as a second-line text-link row, matching the
   Settings footer adaptation (`desktop.py:1352-1358`). Replace the four-space
   metadata string (`desktop.py:2121-2127`) with three structured labels.
4. Statistics chart: rebuild as accent bars on `surface-2` with a 7-day axis, value
   labels in tabular 12px, and an explicit empty state ("No dictations in the last
   7 days"). Current foreground-color bars (`desktop.py:1005-1007`) should go.
5. Settings/Advanced bridge: give Advanced the same sentence-voice section titles
   and 24px token scale, or give main Settings one bordered card per sentence so
   the two pages share at least one container. Today they share only the footer.
6. Navigation: keep the sidebar; delete the duplicate header wordmark and let the
   collapsed state show only the toggle + window title. Replace "← Settings" /
   "Advanced →" labels with icon + translatable label buttons.
7. HUD-app link: use `recording` (accent green) for the live dot and waveform,
   keep white for idle labels, reserve the pink/red strictly for errors. Give
   success its own treatment (accent check) distinct from live recording.
8. Icons: redraw `gear` as arcs (matching `clock`), rebuild `sidebar-collapse` on
   the 24 grid at the shared 1.7 width, and ship 16/24/32px app-icon renders or
   verify the 40px SVG at 16px on HiDPI and loDPI.

## Prioritized recommendations

P0 — system integrity:

- [ ] Complete the token table above; remove all hardcoded hex from `desktop.css`
  and the `desktop.py:1861-1868` dark block. Merge border/divider.
- [ ] Switch focus outlines from muted to accent in both themes; verify contrast.
- [ ] Choose one recording color (green accent vs docs sky-blue) and apply to HUD,
  app recording states, and product-page doc.
- [ ] Resolve the hidden `status_button` (restore or delete).

P1 — consistency and hierarchy:

- [ ] Unify page gutters and section rhythm behind one scaffold.
- [ ] Collapse button languages: filled for dialogs/destructive, text-link for
  secondary, token at 24px for sentence choices, one inverted primary reserved
  for setup Finish/Continue.
- [ ] Rebuild the Statistics chart with axis, empty state, and accent bars.
- [ ] Wrap the History toolbar below 680px; structure card metadata.
- [ ] Standardize cards: one radius (16), one padding (20), one hairline (`line`).

P2 — polish:

- [ ] Tabular numerals for all metrics, timers, and calendar counts.
- [ ] Sidebar fade matching HUD timing; honor reduced motion.
- [ ] Redraw `gear` and `sidebar-collapse`; verify app icon at 16px.
- [ ] HUD: single optical center for capture/idle; ellipsis for long labels;
  make `high_contrast` affect stroke/text, not just fill alpha.
- [ ] Empty states for Recent, History (off vs empty are already distinguished in
  copy — keep that), Statistics, and usage calendar.

## Checks needed (must precede any 9+ claim)

- [ ] Runtime screenshots: Home/History/Statistics/Settings/Advanced/setup at
  480px, 900px, 1100px widths, in light, dark, and system-follows-desktop.
- [ ] Contrast ratios: ink/muted/accent/focus/error on page and surface, both
  themes; HUD grays and error pink on near-black; usage levels 1-4 text in both
  themes.
- [ ] GTK/Adwaita matrix: default Adwaita light/dark plus one third-party theme if
  supported; stock dialogs (update prompt, delete-all, file export) in both modes.
- [ ] Narrow-window pass: History toolbar, sentence wrapping with long mic/provider
  names, footer stacking, setup headlines at 480px.
- [ ] HUD capture on HiDPI and loDPI: waveform legibility, `MM:SS` past 10:00,
  longest-label overflow, dwell readability for unrefined/copied states.
- [ ] Icon pass: app icon at 16/24/32/48px, symbolic in a dark panel, nav glyphs
  at 22px against Adwaita symbolic weight.

## Blockers to 9-9.5

1. No runtime evidence in this review. A 9 requires the screenshot and contrast
   matrix above, not static reading.
2. Token coverage is partial by construction (hardcoded component colors).
3. Three page systems and three button languages must become one each.
4. Statistics chart and History toolbar need redesign, not tuning.
5. HUD/app recording color split (gray vs green vs docs blue) must be decided.
6. Focus visibility and narrow-window behavior are unverified.

## Source reference index

- App shell, nav, pages: `src/caelum/desktop.py:403-517,674-963`.
- Sentence Settings + Advanced: `src/caelum/desktop.py:1029-1177,1178-1276`.
- Theme tokens + dark overrides: `src/caelum/desktop.py:1836-1883`.
- Refresh/render + status pill: `src/caelum/desktop.py:1967-2116`.
- Stylesheet: `src/caelum/desktop.css:1-202` (duplicates at 8/162, 11/176, 40-41/179).
- HUD: `src/caelum/hud.py:63-83,119-218,234-312`.
- Setup: `src/caelum/onboarding_ui.py:32-103,140-192,245-275,335-415,579-599`.
- Icons: `src/caelum/icons/hicolor/scalable/apps/caelum.svg`,
  `caelum-symbolic.svg`; nav glyphs `src/caelum/desktop.py:548-651`.
- Competitor/product direction: `docs/product-page-design.md:7,69-76,80-82`.
- Theme tests: `tests/test_overview.py:87-116`, `tests/test_settings_ui.py:48-111`.
