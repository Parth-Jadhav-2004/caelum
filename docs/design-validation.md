# Interface redesign validation — 2026-11-07

The first independent Muse Spark 1.3 Contributor reviews scored visual design
5.8/10, onboarding 5.5/10, and interactions/accessibility 6/10. These were static
source reviews, not observed competitor-app comparisons. Their reports are
`design-review-visual.md`, `design-review-onboarding.md`, and
`design-review-interactions.md` in this directory. They describe the pre-redesign
checkout; source line references there are historical.

## Implemented direction

Keep the quiet green identity and sentence-style settings. Consolidate typography,
page gutters, surface radii, focus color, theme-aware component colors, and the
HUD's recording accent. Make navigation compact below 760px without removing
page labels from accessible names. Give History a search-first wrapping toolbar
and confirmed deletions. Use theme-colored activity bars with gridlines, empty
state guidance, and a screen-reader text summary.

Setup now labels its four steps, explains privacy, validates candidate keys in
memory before storing them, keeps failed entries editable, and discards unvalidated
provider drafts when leaving. Distinct custom-provider keys are collected in memory
until all selected providers validate. Practice reports recording/transcription
phases and offers a visible cancel action. Key removal asks for confirmation.
Reopening intentionally rechecks providers and microphone; README now says so
rather than promising restoration to an already-passed step.

Service state, Start/Stop, and pause menu are visible in Home. Provider errors keep
Manage keys available. Separate status/history workers keep controls updating during
history failures. Retry/Cancel suppress duplicate requests while in flight. Single
deletes, key removal, and stopping/quitting with retryable audio have confirmations.
Notices announce to assistive technology where the installed GTK supports it.

## Evidence and repeatable checks

- `GDK_BACKEND=x11 CAELUM_DESKTOP_TESTS=1 .venv/bin/pytest -q`:
  **261 passed, 4 skipped**, including the native GTK tests, after the functional
  redesign. The skipped checks are opt-in native target integration tests.
- `.venv/bin/ruff check src tests scripts/capture_design.py`: passed.
- `scripts/capture_design.py` creates seeded GTK screenshots with isolated temporary
  configuration/history and mocked credentials, device enumeration, and service.
  It does not record or send audio or query real credentials. Setup stage screenshots
  deliberately set the stage for layout inspection; they do not demonstrate provider
  validation or microphone success. Native setup tests separately exercise gates.
- Captured both themes for Home, History, Statistics, Settings, Advanced, and all four
  setup stages at **1100 × 760** and **480 × 640**. Local review captures are under
  `/tmp/caelum-design-wide` and `/tmp/caelum-design-narrow`. Regenerate with:

```sh
.venv/bin/python scripts/capture_design.py --output /tmp/caelum-design-wide
.venv/bin/python scripts/capture_design.py --width 480 --height 640 --output /tmp/caelum-design-narrow
```

Snapshots use a temporary modal window containing the actual native widgets at a
controlled size, without editing desktop window rules. These captures omit the
main window's header bar. They are seeded layout evidence, not real-user data.

## Market direction and limits

Public pages fetched on 2026-11-07: [Wispr Flow](https://wisprflow.ai/) emphasizes
speech becoming polished writing across apps, with a prominent download action
and transformation examples. [Superwhisper](https://superwhisper.com/) presents a
shortcut-led demo and configurable modes. Caelum can match that clarity with an
obvious recording state, explicit setup actions, and a clear first-result loop.
This research inspected public page content, not installed competitor interfaces;
there is no defensible numerical competitor ranking from it.

A design score is subjective. Passing automated tests and rendered screenshots do
not certify zero bugs or public-launch readiness. Real provider/keyring acceptance,
Orca, physical keyboard/HUD input behavior, text scaling, microphone hot-unplug,
lock/suspend, GNOME/KDE portal behavior, clean distro installs and signed updates
remain acceptance work. Historical core-engine/release findings in
`public-launch-remaining.md` are outside this interface pass unless explicitly
addressed above (A05's history/status coupling is repaired and regression-tested).

## Second implementation pass

The first rendered re-review scored visuals 8.2/10, onboarding appearance 8.5/10,
onboarding flow 7.5/10, and interactions 8.0/10. These ratings describe the first
pass, before the corrections below. The next independent reports scored rendered visuals 9.0, onboarding appearance 9.0 / flow 8.8, and interactions 8.6; these scores precede the final corrections listed below.

Corrected pointer/search focus colors, grouped the provider status dot with its
label, removed detached punctuation, suppressed zero-value chart labels, themed
all checkboxes, added a real empty-practice placeholder, and reduced display type
to 24/26px while keeping 15px body text. Notices now have a dismiss action.

Provider setup now exposes a credential selector when two keys are required.
Clearing an entry drops its in-memory override; switching credentials preserves
editable candidates. Validation can be cancelled without saving keys. The
Contributor requirement is reflected in the Continue state. Shortcut capture
ends before advancing. Practice errors reset their instructions, microphone
steps focus the primary action, and progress labels expose current/completed/
upcoming states.

Status reads recover after malformed JSON, history reads handle unexpected errors,
and a third worker provides room for control requests beside status/history.
Pause uses the duplicate-input guard. Active recording/processing Stop and Quit
ask for confirmation; idle stop messages no longer claim discarded audio. Dialogs
restore invoking focus where it remains mapped; history rebuilds park focus on a
stable control and remove feedback timers. Autosave failures reach the notice
announcement path. Regression checks cover malformed replies, active-recording
confirmation, cleared bad keys, repairing the first custom key, and validation
cancellation. The setup-test readiness wait now really retries before assertions.

Fresh normal-size captures are in the wide/narrow directories above. Additional
captures are in `/tmp/caelum-design-scaled`, made with `--width 480 --height 640
--font-scale 1.5`. This is a controlled font-size stress test, not an OS scaling
certification. Main pages remain 480px wide; setup respects its larger minimum
width (515–555px) at that text size. Captures show scrolling content with fixed actions. A reviewer identified a visually ambiguous setup1 scroll/footer boundary at 150%; the final pass adds an opaque footer, padding, and separator. Controls below the fold require scrolling. Exact 480px setup at 150%
and 200% text, actual desktop scaling, and assistive technology remain open.

## Final corrections and evidence

Addressed the last review's concrete findings: Delete-all now uses shared dialog
focus restoration; Dismiss parks focus before hiding; disappearing Cancel restores
focus; malformed status replies preserve the last known service state and expose a
retry notice. Stop/Quit fetch fresh state in a worker before deciding whether to
confirm. Pause shows its busy state. Error notices have a danger border and a
single pending-message slot so an informational message cannot erase an error.
The announcement gate resets on hide (this already happened through message("");
the review's contrary D-6 scenario did not reproduce by source inspection).

Setup errors name the Transcription/Refinement credential role; the Contributor
switch preserves consent only for the same provider/model scope. Practice announces
the first detected speech, restores full instructions after errors, and parks
Cancel focus before hiding. Setup uses the same preset names as Settings, links
explain that Advanced restarts setup, and the footer has an opaque background and
separator. HUD Done/Unrefined now use a neutral check/label, distinct from green
live recording; runtime HUD qualification remains open.

Final automated run: **261 passed, 4 skipped**; ruff and diff whitespace checks
pass. Added checks cover role-attributed provider errors, shortcut-capture advance,
error-notice retention/dismissal, disappearing Cancel focus, and fresh active status
when the cached state was idle. Normal captures were regenerated after this pass.

Computed sRGB contrast ratios from the actual theme tokens (foreground/background,
without antialiasing): light body 15.81:1, muted 6.05:1, token 5.00:1, primary 5.95:1,
danger 6.52:1; dark body 17.58:1, muted 7.05:1, token 8.04:1, primary 10.80:1,
danger 8.73:1. These are core text-pair measurements, not an exhaustive rendered
contrast audit or certification of every widget/disabled/focus state.

## Independent acceptance result

Muse Spark 1.3 Contributor's overall acceptance review is complete:
**9.1/10 — accepted for design**. Category scores: application visuals 9.2,
onboarding appearance 9.2, onboarding flow 9.1, interactions/accessibility logic
9.1. See `design-acceptance.md` for method, current-source verification,
rejected unsupported findings, and non-blocking polish. This meets the requested
9–9.5 design target. It does not close the separate live hardware, provider,
assistive-technology, or public-release qualification gates described above.
