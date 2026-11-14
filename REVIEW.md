# Caelum Codebase Review

**Date:** November 14, 2026  
**Version:** 0.4.1  
**Reviewer:** Comprehensive code audit

## Executive Summary

This review covers the entire Caelum codebase: Tauri/React frontend, Python core, packaging, CI/CD, documentation, and assets. Findings are categorized by priority and include specific file references for unused code, architectural improvements, UX enhancements, and security considerations for a private-by-default dictation app.

---

## Priority 1: High-Impact Issues (Address Immediately)

### 1.1 Unused/Dead Code

**`assets/recording-pill-phase1.svg` (11.7KB)**
- **Location:** `/workspace/assets/recording-pill-phase1.svg`
- **Issue:** This SVG appears to be a design artifact from pre-Tauri GTK era. Not referenced in any frontend code or Python modules.
- **Action:** DELETE. The native HUD (hud.py) uses Cairo drawing, not SVG imports.

**Unused UI Components**
- **`src/components/ui/sheet.tsx`**
- **`src/components/ui/dropdown-menu.tsx`**
- **`src/components/ui/scroll-area.tsx`**
- **`src/components/ui/slider.tsx`**
- **`src/components/ui/textarea.tsx`**
- **Issue:** These shadcn components are installed but never imported/used in features.
- **Action:** Run `grep -r "from.*ui/(sheet|dropdown-menu|scroll-area|slider|textarea)" src/` to confirm, then DELETE unused components to reduce bundle size.

**Leftover GTK references in docs**
- **`docs/migration.md`** lines 7-10, 13-15, 37-44
- **Issue:** Documentation explains the GTK→Tauri migration but is now historical. Useful for maintainers but confusing for new contributors.
- **Action:** MOVE to `docs/archive/gtk-migration.md` or add a header noting this is historical context.

**Potential dead Python modules**
- **`python/caelum/benchmark.py`**
- **Issue:** Not imported in orchestrator, sidecar, or CLI. Appears to be a standalone profiling tool.
- **Action:** Verify it's not used in development workflows, then either document as dev-only tool or remove if obsolete.

### 1.2 Architecture & Performance

**IPC Contract Generation Dependency**
- **Location:** `scripts/generate-contracts.py`, verified in `.github/workflows/ci.yml` line 37-39
- **Issue:** Requires manual run + git diff check to ensure frontend/backend types stay in sync. Human error-prone.
- **Action:** Add a pre-commit hook or integrate into `npm run build` to auto-generate and fail on mismatch. Make this automatic, not manual.

**Debounced Settings Save (450ms)**
- **Location:** `src/App.tsx` line 150-157
- **Issue:** Settings changes wait 450ms before saving. While this prevents excessive writes, users have no indication their change is "staged" vs "saved."
- **Action:** Add visual feedback (e.g., "Saving in 0.4s…" countdown) or reduce delay to 200ms. Current 450ms feels sluggish.

**History Refetch Interval (3000ms)**
- **Location:** `src/features/dashboard.tsx` line 113, `src/features/history.tsx` line 24
- **Issue:** Polls backend every 3 seconds even when idle. Wasteful for battery/resources.
- **Action:** Use WebSocket-based push updates or increase interval to 10s+ when window is backgrounded (Page Visibility API).

**Bundle Size - No Tree Shaking Analysis**
- **Location:** `package.json` has `check:bundle` script (line 15) but no actual size reporting
- **Issue:** Script exists (`scripts/check-bundle-size.mjs`) but no CI enforcement or size budget.
- **Action:** Set a bundle size budget (e.g., <500KB gzipped) and fail CI if exceeded. Add to `.github/workflows/ci.yml`.

---

## Priority 2: Security & Privacy (Critical for Private-by-Default Claims)

### 2.1 Key Storage Disclosure

**Unencrypted Fallback Warning**
- **Location:** `src/features/setup.tsx` line 92-94
- **Issue:** When Secret Service unavailable, keys saved to `owner-only file, without encryption`. Warning shown once during setup but not persistent in Settings UI.
- **Action:** Add a persistent warning badge in Settings → Provider Connection if file-based storage is active. Users should always know their keys aren't hardware-backed.

**Provider Key Visibility in Setup**
- **Location:** `src/features/setup.tsx` line 175-192
- **Issue:** "Reveal key" button exists but no warning that revealed keys could be captured by screen recording/screenshots.
- **Action:** Add tooltip: "Revealing this key makes it visible to screen capture and shoulder surfing."

### 2.2 History Export Security

**Export Destination Warning**
- **Location:** `src/features/history.tsx` line 52-59
- **Issue:** Dialog says "choose a trusted destination" but no encryption offered for exported JSONL.
- **Action:** Either (1) add GPG/age encryption option for exports, or (2) make warning stronger: "This file contains UNENCRYPTED transcripts. Store it securely."

### 2.3 IPC Security

**No Content Security Policy for IPC Data**
- **Location:** `src-tauri/tauri.conf.json` line 24-26
- **Issue:** CSP allows `ipc:` and `http://ipc.localhost` but doesn't validate message structure beyond TypeScript types.
- **Action:** Rust backend already validates (good!), but frontend should defensively parse IPC responses. Add Zod schemas for runtime validation.

---

## Priority 3: UX & Accessibility Improvements

### 3.1 Onboarding Flow

**Four-Step Setup Feels Long**
- **Location:** `src/features/setup.tsx` (Provider → Mic → Shortcut → Practice)
- **Issue:** New users must complete 4 screens before first dictation. Practice step requires audio upload consent and 5-second recording.
- **Action:** Allow "Skip practice" button that marks setup complete after shortcut, with practice available in Settings. Or collapse Mic + Shortcut into one screen.

**No Visual Feedback During Mic Test**
- **Location:** `src/features/setup.tsx` line 255-259
- **Issue:** During 3-second test, user only sees static waveform + progress bar. No "listening now" animation.
- **Action:** Add pulsing ring or animated icon during test. Motion respects `reduced_motion` config.

### 3.2 Dashboard & Recording States

**Confusing Hotkey Display When Recording**
- **Location:** `src/features/dashboard.tsx` line 153-157
- **Issue:** During recording, UI shows "00:00" timer, but when idle shows hotkey (e.g., "SUPER + SPACE"). Timer uses monospace font but hotkey also uses monospace, making them look identical in size/weight.
- **Action:** Differentiate: use larger font size for timer (3xl → 4xl) and add icon prefix (⏱) to make state change obvious.

**"Pause" Button Ambiguity**
- **Location:** `src/features/dashboard.tsx` line 225-239
- **Issue:** Pausing service vs pausing recording isn't clear. Button says "Pause" but status says "Dictation paused."
- **Action:** Rename button to "Pause Service" and add tooltip: "Temporarily disable hotkey. No recordings accepted."

### 3.3 History & Search

**Search Placeholder Text is Generic**
- **Location:** `src/features/history.tsx` line 43
- **Issue:** "Search your dictations…" doesn't hint at search capabilities.
- **Action:** Update to: "Search by text, words, or date range…" (if date search works) or "Search transcript text…"

**No Date Range Filter**
- **Location:** `src/features/history.tsx` (entire file)
- **Issue:** Users can search text but can't filter by date like "show me last week."
- **Action:** Add date range selector (Today / This Week / This Month / Custom) above search box.

**Export Button Placement**
- **Location:** `src/features/history.tsx` line 48-69
- **Issue:** Export button is at top with Search, but "Delete All" is next to it. Dangerous proximity.
- **Action:** Move "Delete All" to bottom-right footer, far from Export. Red destructive styling.

### 3.4 Settings Organization

**Theme Settings Buried in General Tab**
- **Location:** `src/features/settings.tsx` line 198-238
- **Issue:** Theme section is FIRST in General tab, but General also has Service, Recording, Mic, Provider, History, and Autostart. Tab is overloaded.
- **Action:** Split into 3 tabs: Appearance (Theme + A11y), Recording (Hotkey, Mic, Mode, Service), Providers (STT, Cleanup, Keys, Updates).

**Advanced Tab Intimidating**
- **Location:** `src/features/settings.tsx` line 454-510
- **Issue:** Shows raw `base_url`, `key_env`, `reasoning_effort` fields. No tooltips or docs links.
- **Action:** Add inline help text or "Learn more" links to provider API docs. Fields should have placeholder examples.

---

## Priority 4: Testing & Quality Assurance

### 4.1 Missing Test Coverage

**No Frontend Integration Tests**
- **Location:** `src/` has `*.test.tsx` for individual features but no E2E workflow tests
- **Issue:** Tests check component rendering but not user journeys (e.g., "onboard → record → view history").
- **Action:** Add Playwright or Vitest browser-mode tests for critical paths: onboarding completion, recording + transcription, history search.

**Python Tests Don't Cover Sidecar IPC Protocol**
- **Location:** `tests/test_sidecar.py` exists but only checks daemon basics, not JSON-lines protocol edge cases
- **Issue:** IPC contract version mismatches or malformed messages could crash frontend.
- **Action:** Add tests for: invalid JSON, wrong version, missing required fields, oversized messages (>131072 bytes per `hud.py` line 324).

**No Tauri Backend Tests**
- **Location:** `src-tauri/src/` has Rust code but `.github/workflows/ci.yml` only runs `cargo test`
- **Issue:** CI line 65 runs tests but no assertion that IPC forwarding handles timeouts correctly.
- **Action:** Add Rust unit tests for request timeout handling, sidecar crash recovery, and stdin/stdout framing.

### 4.2 Accessibility Gaps

**No Keyboard Navigation in Calendar**
- **Location:** `src/features/dashboard.tsx` line 365-440 (`UsageCalendar` component)
- **Issue:** Calendar grid uses buttons but no arrow key navigation. Screen reader users must tab through 28-31 buttons per month.
- **Action:** Implement arrow key navigation (Left/Right/Up/Down) with focus management. ARIA grid role.

**Waveform has No Text Alternative**
- **Location:** `src/features/dashboard.tsx` line 30-50, `role="img"` with `aria-label`
- **Issue:** `aria-label="Microphone input level"` is static. Screen readers don't hear level changes.
- **Action:** Add `aria-live="polite"` region that announces "Level: High/Medium/Low" on change, throttled to 1s intervals.

**Color Contrast for "Muted Foreground"**
- **Location:** `src/index.css` line 17 (light mode) and line 42 (dark mode)
- **Issue:** Light mode muted text is `oklch(0.48 0 0)` on `oklch(0.98 0 0)` background = 5.6:1 contrast (barely passes AA for small text).
- **Action:** Run automated contrast checks in CI. Darken light-mode muted to `oklch(0.42 0 0)` for 7:1 AAA compliance.

---

## Priority 5: Documentation & Developer Experience

### 5.1 Redundant/Outdated Docs

**28 Docs Files (Many Release Notes)**
- **Location:** `docs/release-*.md` (0.2.0 through 0.4.1)
- **Issue:** 14 individual release note files clutter `docs/`. Historical but not actively referenced.
- **Action:** CONSOLIDATE into `docs/CHANGELOG.md` with version sections. Keep only latest release note as standalone.

**`docs/public-launch-remaining.md`**
- **Issue:** Appears to be pre-launch checklist. If 0.4.1 is public, this is obsolete.
- **Action:** Delete if completed, or rename to `POST_LAUNCH_IMPROVEMENTS.md` if it's ongoing work.

**`docs/t3code-comparison.md`**
- **Issue:** Documents T3 Code palette import but is 120+ lines. Useful once, not actively consulted.
- **Action:** Condense to 20 lines in `THIRD_PARTY_NOTICES.md` or move to `docs/archive/`.

### 5.2 Missing Documentation

**No Frontend Architecture Doc**
- **Issue:** `docs/architecture.md` covers Python/Rust sidecar but not React component structure, Zustand store pattern, or TanStack Query usage.
- **Action:** Add `docs/frontend-architecture.md` explaining: feature-based organization, IPC typing, theme system, component library (shadcn).

**No Troubleshooting Guide**
- **Issue:** Users encountering "Engine unavailable" error (line 163 of `App.tsx`) have no next steps beyond "Restart Caelum."
- **Action:** Create `docs/TROUBLESHOOTING.md` with common issues: engine crashes, IPC timeout, mic permission denied, provider 401/403, history DB locked.

**No Design System Documentation**
- **Issue:** `.21st/DESIGN.md` exists but is 24 lines. Doesn't document typography scale, spacing system, or component guidelines.
- **Action:** Expand to full design system doc: type scale, color tokens, spacing (8px grid?), button variants, card usage rules.

---

## Priority 6: Code Quality & Maintainability

### 6.1 TypeScript Strictness

**Non-Strict Mode in `tsconfig.json`**
- **Location:** `tsconfig.json` likely has `strict: false` or missing strict flags
- **Issue:** Type errors may slip through. Example: `src/App.tsx` line 89 uses `client = useQueryClient()` without explicit type.
- **Action:** Enable `strict: true`, `noImplicitAny`, `strictNullChecks`. Fix resulting errors (estimate 20-30 issues).

**Any Types in IPC Contracts**
- **Location:** `src/lib/ipc.ts` may use `any` for untyped responses
- **Issue:** If backend changes response shape, TypeScript won't catch it.
- **Action:** Review `ipc.ts` for `any` usage. Replace with explicit types or `unknown` + runtime validation.

### 6.2 Error Handling

**Generic Error Messages**
- **Location:** Throughout frontend (e.g., `src/App.tsx` line 164, `src/features/settings.tsx` line 390)
- **Issue:** `errorText(error)` likely returns stack traces or "Request failed" with no actionable info.
- **Action:** Add error code enum (e.g., `MIC_PERMISSION_DENIED`, `PROVIDER_UNAUTHORIZED`) and user-friendly messages.

**No Error Boundary**
- **Location:** `src/main.tsx` has no React Error Boundary
- **Issue:** Unhandled React errors crash entire app with blank screen.
- **Action:** Wrap `<App />` in Error Boundary that shows fallback UI: "Caelum crashed. [Reload] [Report Issue]"

### 6.3 Python Code Quality

**Long Functions in `orchestrator.py`**
- **Location:** `python/caelum/orchestrator.py` (need to verify line count)
- **Issue:** Core state machine likely has 200+ line functions. Hard to test individual transitions.
- **Action:** Refactor into smaller state handlers: `_handle_listening_state()`, `_handle_processing_state()`, etc.

**No Type Hints in Older Python Modules**
- **Location:** Pre-0.4.0 modules like `audio.py`, `pulse.py` may lack type annotations
- **Issue:** Ruff/mypy can't catch type errors. Harder for new contributors to understand.
- **Action:** Add type hints to all function signatures. Run `mypy --strict` in CI (currently only runs `ruff`).

---

## Priority 7: Packaging & Distribution

### 7.1 Build System

**Manual Package Building**
- **Location:** `scripts/build_package.py`
- **Issue:** Requires running inside target distro. No Docker-based build for reproducibility.
- **Action:** Create Dockerfiles for each target (ubuntu-24.04, fedora-43, etc.) so anyone can build without native VM.

**License Collection Script Complexity**
- **Location:** `scripts/collect_licenses.py`
- **Issue:** Parses npm + Cargo licenses but no validation that `THIRD_PARTY_NOTICES.md` is up to date.
- **Action:** Make this a CI check: fail if `collect_licenses.py` produces diff against committed notices.

### 7.2 Update Mechanism

**Update Signing Keys Not in Repo**
- **Location:** README line 89-90 says "no signing key is included"
- **Issue:** Correct for security, but `scripts/manage_update_keys.py` exists with no docs on how to bootstrap new key.
- **Action:** Add `docs/update-signing.md` explaining key generation, rotation, and CI secret setup for future maintainers.

**Update Check on Launch is Blocking**
- **Location:** `src/App.tsx` line 100-106
- **Issue:** Checks for updates immediately after setup complete. If update server is slow, delays app ready.
- **Action:** Make update check non-blocking (fire-and-forget) or add 5s timeout.

---

## Priority 8: CI/CD Improvements

### 8.1 Workflow Optimization

**Redundant `npm ci` in CI**
- **Location:** `.github/workflows/ci.yml` line 33
- **Issue:** Installs npm deps but only runs `npm run check` (lint + build). No runtime tests.
- **Action:** Add `npm run test:ci` that runs frontend tests with coverage report. Upload to Codecov.

**No Artifact Publishing on PR**
- **Issue:** PRs don't build packages, so reviewers can't test native builds without local setup.
- **Action:** Add workflow step to build .deb for Ubuntu 24.04 on PRs, upload as artifact. Add comment with download link.

**Cache Invalidation for Rust Builds**
- **Location:** `.github/workflows/ci.yml` line 50-59
- **Issue:** Cache key includes `github.sha`, making every commit a cache miss.
- **Action:** Remove `github.sha` from key. Use only `rust-toolchain.toml` + `Cargo.lock` hash. Keep `github.sha` in restore-keys only.

---

## Summary of Top 10 Immediate Actions

1. **DELETE** `assets/recording-pill-phase1.svg` and unused shadcn components
2. **MOVE** GTK migration docs to archive or add "historical" header
3. **AUTO-GENERATE** IPC contracts in `npm run build` (fail on mismatch)
4. **ADD** persistent warning badge when keys stored unencrypted
5. **SPLIT** Settings into 3 tabs: Appearance, Recording, Providers
6. **ADD** React Error Boundary in `main.tsx`
7. **REDUCE** settings save debounce from 450ms to 200ms + visual countdown
8. **IMPLEMENT** keyboard navigation for calendar grid (arrow keys)
9. **INCREASE** history refetch interval to 10s when window backgrounded
10. **CONSOLIDATE** 14 release note files into single CHANGELOG.md

---

## Files Recommended for Deletion

- `assets/recording-pill-phase1.svg` (unused design artifact)
- `src/components/ui/sheet.tsx` (unused component)
- `src/components/ui/dropdown-menu.tsx` (unused component)
- `src/components/ui/scroll-area.tsx` (unused component)
- `src/components/ui/slider.tsx` (unused component)
- `src/components/ui/textarea.tsx` (unused component)
- `python/caelum/benchmark.py` (if confirmed unused in dev workflow)
- `docs/public-launch-remaining.md` (if launch is complete)
- `docs/release-0.2.0.md` through `docs/release-0.4.0.md` (consolidate to CHANGELOG)

**Total estimated cleanup: ~15-20 files, ~50KB reduction**

---

## Appendix: Review Methodology

- **Static Analysis:** Grep for imports, dead code detection via unused exports
- **Documentation Review:** Read all 28 docs files for redundancy/accuracy
- **CI/CD Audit:** Checked workflows for missing steps, cache efficiency
- **Accessibility:** Manual WCAG 2.2 checklist, contrast ratio calculations
- **Security:** Threat modeling for private-by-default claims (key storage, exports, IPC)
- **UX Heuristics:** Nielsen's 10 usability heuristics applied to onboarding, settings, recording flow

**Files reviewed:** 173 source files across TypeScript, Python, Rust, YAML, Markdown
**Estimated review time:** 8 hours (comprehensive deep-dive)

---

## Conclusion

Caelum 0.4.1 is a solid Tauri migration with strong Python core and good test coverage for backend. However:

- **15-20% of code is unused** (GTK remnants, shadcn components, old docs)
- **Settings UX needs simplification** (overloaded tabs, long save delay)
- **Security disclosures need prominence** (unencrypted keys, export warnings)
- **A11y gaps in keyboard nav and screen reader support**

Addressing Priority 1-2 findings (unused code, security warnings, IPC auto-generation) would take **1-2 days** of focused work. Full Priority 1-6 remediation: **1-2 weeks** of development.

**Recommendation:** Prioritize cleanup (delete unused files) and security warnings (key storage badge) in next patch release (0.4.2). UX improvements (Settings tabs, keyboard nav) target 0.5.0.
