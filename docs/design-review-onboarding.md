# Design review: onboarding flow

Scope: full first-run flow (progress, provider/key entry, privacy/consent, mic
test, shortcut, practice, continue/back/resume, loading/errors, first
dictation). Traced `src/caelum/onboarding_ui.py`, `src/caelum/onboarding.py`,
host functions in `src/caelum/desktop.py`, `desktop.css`, credentials/config/
providers helpers, and `tests/test_desktop.py` + `tests/test_onboarding.py`.
Static review only: no live GTK run, no real provider/keyring/hardware. No
launch-readiness claim is made here.

Evidence convention: **verified** = read in source; **inferred** = follows
from code but not executed; **subjective** = design judgment.

## Scores (honest, uninflated)

| Area | Score | One-line reason |
| --- | --- | --- |
| Progress / resume | 4/10 | Saved stage is write-only; resume always restarts at 1 |
| Provider + API key entry | 6/10 | Real validation, transparent storage; invalid keys persist, retry trap |
| Privacy / consent | 4/10 | Gates enforced, but full privacy text never renders in the UI |
| Microphone test | 7/10 | Local-only with live meter; best-built step |
| Shortcut selection | 5/10 | Capture + conflict check work; dead-ends on backend errors |
| Practice / first success | 5/10 | Genuine gated E2E test; dead UI during record + upload |
| Loading / errors | 5/10 | Good worker-thread discipline; misleading generic fallback |
| Visual cohesion | 6/10 | Distinctive sentence UI; color-only progress, no step labels |
| **Overall** | **5.5/10** | Solid, well-tested foundations with real logic and copy gaps |

Confidence: high on logic findings (all traced to exact lines); medium on
visual/a11y findings (CSS + widget code read, not rendered); directional only
on competitor comparison (below).

## Directional benchmark (Wispr Flow, Superwhisper)

No competitor onboarding screens were observed for this review, and none are
claimed. The only in-repo evidence is `docs/product-page-design.md:80-82`,
which browsed both marketing sites for benefit clarity and download actions —
not their setup flows. Directional, subjective inference only: both competitors
lead with immediate speak-to-text value and minimal upfront configuration,
while Caelum front-loads four gated steps (key + validation, mic test,
shortcut, consented practice) before any success moment. That is a defensible
trade for a BYOK Linux app, but it raises the cost of every friction point
below: each unclear step multiplies drop-off because there is no early win.
Do not read this as a feature-parity requirement.

## Verified logic flaws (ranked)

1. **Resume does not restore the stage.** `Setup.__init__` hard-codes
   `self.stage = 1` (`onboarding_ui.py:40`), and `render()` immediately
   overwrites the saved value (`onboarding_ui.py:598-599`). The saved
   `Progress.stage` is write-only. README ("Resume later preserves your
   place") and `docs/public-launch-remaining.md` ("resumable") overclaim:
   what is preserved is config text, not position. Either restore the stage
   (keeping provider revalidation) or reword to "resume restarts at key
   check."
2. **The full privacy explanation never appears in the UI.** `PRIVACY`
   (`onboarding.py:16-23`) is rendered only on `serve` stderr
   (`cli.py:202-205`). The setup provider page shows one checkbox sentence
   (`onboarding_ui.py:167-177`) and no history/clipboard/encryption/limits
   text; my search of `src/caelum` finds no privacy notice in Settings
   either. This contradicts README ("Read the privacy explanation"),
   `docs/privacy.md:26-34` ("Setup explains this data flow"), and
   `public-launch-remaining.md:183-184`. The consent gate is enforced, but
   users consent to a sentence, not the documented explanation.
3. **Invalid keys are stored before validation, then the entry is cleared.**
   `advance()` clears the entry first (`onboarding_ui.py:499-500`);
   `verify_and_save` stores, then validates (`onboarding_ui.py:520-529`).
   On failure the notice shows an error with an empty entry — yet the bad
   key is now in the keyring/file, so pressing Continue again re-fails
   against the stored key. Users must guess they need to paste a replacement.
4. **Abandoning setup persists unvalidated drafts.** `finish_setup` saves
   `self.config` whenever not busy (`onboarding_ui.py:605-624`), reached via
   Resume later, sidebar navigate (`desktop.py:529-534`), and Custom-provider
   detour (`onboarding_ui.py:241-244`). Combined with `change_provider`
   overwriting custom endpoints when touching Groq presets
   (`onboarding_ui.py:208-226`, via `apply_provider_preset`), a user can
   destroy a working custom endpoint by opening setup, tapping a preset, and
   clicking Resume later — with no validation and no warning.
5. **Shortcut dead-ends.** The Hyprland-Lua error says "use portable mode"
   (`onboarding.py:73`) but setup has no backend selector (Advanced-only),
   so there is no in-flow path forward. Modifiers-only combos are accepted
   by capture (`onboarding_ui.py:381-390`) and config
   (`config.py:126-129`), then rejected on portable
   (`portable.py:47-54`) — validate earlier with a per-backend hint.
   Capture can also stall silently (single modifier + release leaves
   "Press keys…" with no guidance; focus loss mid-capture is unhandled).
6. **Practice runs with dead UI.** The 5 s record passes no level callback
   (`onboarding_ui.py:452-457`) and upload adds unbounded network time; the
   only feedback is a static notice. Cancel is Esc-only
   (`onboarding_ui.py:420-423`) and undiscoverable (the page copy never
   mentions it); the only visible out is Resume later, which destroys the
   page. Mic test (live meter, `onboarding_ui.py:296-303`) shows the
   established pattern — practice should reuse it plus a Cancel button.
7. **Misleading generic error fallback.** `Setup.work` maps any
   non-Value/Runtime error to "Check the microphone, keyring, or network"
   (`onboarding_ui.py:122-125`) — wrong guidance for shortcut/serialization/
   IPC-shape failures (e.g. unexpected `hypr_json` shape raising KeyError).
   Pass through a per-stage fallback instead.
8. **Two notice areas compete.** Host-global `message()` (`desktop.py:544`)
   and setup-local `notice` are both visible during setup (e.g. file-fallback
   notice goes global at `onboarding_ui.py:506`, validation errors local).
   Route all setup messaging to the local notice.
9. **Consent is framed as a choice but is mandatory.** The provider checkbox
   must be ticked to continue (`onboarding_ui.py:585-592`), which is honest
   framing only if copy says the app cannot work without processing —
   currently it reads as an optional permission. Same for the Contributor
   switch, which also resets to off on every preset change
   (`onboarding_ui.py:224`).
10. **Progress is color-only and unlabeled.** Four 36×4 bars
    (`onboarding_ui.py:52-58`, `desktop.css:124-125`) with no "Step N of 4"
    text and no current-step programmatic state (a11y labels are static
    "Step N"). Fails colorblind/low-vision use; add text + `aria-current`
    equivalent.

## Design observations (subjective, verified locations)

- No welcome/orientation: setup opens directly at key entry
  (`desktop.py:495-498`). One compact header ("4 steps, ~2 min, key first")
  would set expectations; the no-welcome choice is fine only with step labels.
- Stage 2's Continue doubles as "Test microphone"
  (`onboarding_ui.py:585-588`): acceptable, but after a failed test the same
  button re-tests with no "skip" — correct for gating, but copy should say
  the test is required.
- Preset labels differ between setup ("Groq · transcription only",
  `onboarding_ui.py:145`) and Settings (`PRESETS`, `desktop.py:100`).
  Unify.
- `practice_pressed` matches the live hotkey chord
  (`onboarding_ui.py:417-430`); SUPER-based chords may be intercepted by the
  compositor (inferred, not tested) — the click-to-record fallback covers
  this, keep it primary in copy.
- Hidden `Gtk.Entry` as shortcut state holder (`onboarding_ui.py:337`,
  never appended) works but is fragile; a plain string field is clearer.
- Duplicate mic names collapse (`devices_loaded`,
  `onboarding_ui.py:276-287`) — already tracked as A08 in
  `public-launch-remaining.md`.

## Proposed cohesive flow

Keep 4 stages and all gates; fix information and feedback, not structure:

1. **Before you start** (header on stage 1, not a new stage): "4 steps ·
   ~2 minutes · you'll need a free Groq key." Render the real `PRIVACY`
   text in a disclosed expander above the consent checkbox; reword consent
   to acknowledgment ("I understand audio is processed by my providers").
2. **Key:** validate-then-store (swap order in `verify_and_save`); keep the
   entry populated on failure; say "paste a replacement key" in the error.
   Confirm destructive preset switches away from Custom.
3. **Microphone:** unchanged (the reference step). Add text result state
   usable by screen readers.
4. **Shortcut:** show backend-aware requirements inline ("needs a letter,
   number, or function key on this desktop"); turn the Lua error into a
   button that opens Advanced with backend highlighted; add capture
   instructions and a Cancel-capture affordance.
5. **Practice:** reuse the mic meter + elapsed indicator during the 5 s
   record, a determinate "uploading/transcribing" state after, and a visible
   Cancel (wired to existing `cancelled`). Mention Esc as secondary.
6. **Finish:** on success, show where the text went and the single next
   action per backend ("Hold SUPER+ALT+V in any app" vs "Use Record, then
   paste"). Resume restores the furthest validated stage, re-running key
   validation silently when stored keys exist.
7. Global: one notice area in setup; per-stage error fallbacks; "Step N of
   4" text plus progress bars; never persist drafts on abandon — persist
   only on validated Continue (Resume later keeps only the last validated
   snapshot).

## Checks needed (not done here)

- Live GTK run of all four stages incl. Back/Resume/reopen paths.
- Real Groq key: valid, invalid, quota/rate-limit responses through setup.
- Real keyring accept/deny/locked dialogs; private-file fallback visibility.
- Screen reader + keyboard-only pass; 200% text scaling; small windows.
- Hyprland real conflict + Lua-missing session; GNOME/KDE portal permission
  dialogs and manual fallback; SUPER-chord hold in practice.
- Interruption: lock/suspend, mic unplug, and service busy during mic test
  and practice; cancel mid-upload.

## Blockers to 9–9.5

1. Render the documented privacy explanation in setup (fix #2) and align
   README/docs or code on resume (fix #1).
2. Validate-then-store keys with in-place retry (fix #3); stop persisting
   unvalidated drafts on exit (fix #4).
3. Give practice live feedback + visible cancel (fix #6) and shortcut errors
   in-flow recovery (fix #5).
4. Per-stage error copy, single notice area, labeled progress (fixes
   #7, #8, #10).
5. Live-provider, keyring, screen-reader, and multi-desktop acceptance
   evidence from the checks list.
