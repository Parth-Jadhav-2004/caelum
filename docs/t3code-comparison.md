# Caelum and T3 Code: themes, architecture, and public release readiness

Review date: **13 November 2026**. T3 Code source reviewed at
[`f313d0a6cb843551fb60e57a454a71e71a3a8c04`](https://github.com/pingdotgg/t3code/tree/f313d0a6cb843551fb60e57a454a71e71a3a8c04).
Caelum baseline: `9c3949e6cd6170ed2a212cbfefa1c20048599f07` (published v0.4.0),
plus the local theme changes described below. Release inventories were checked
against GitHub's release API. This is a focused source and release review, not a
security audit or proof that either application is free of bugs.

## Assessment

Keep Caelum's Tauri frontend and existing Python engine. T3 Code offers useful
examples of semantic themes, runtime contracts, connection diagnosis, and staged
release publication. Its Electron, server, and remote agent architecture addresses
a much broader product; copying that architecture wholesale would add complexity
without improving local dictation.

The main public-release gaps are concrete: no project license is declared;
sidecar writes and overall shutdown lack complete deadline coverage; native
Wayland/audio/provider acceptance is incomplete; and release workflows need safer
candidate promotion and repeatable publication. Theme polish alone cannot close
these gaps. Existing v0.4.0 packages are already public; the recommendations below
are gates for expanding support and describing a build as broadly qualified.

## Themes: what upstream actually contains, and what changed here

Source: [shared palettes][t3-palettes], [web theme handling][t3-theme-runtime], and
[web CSS][t3-css]. There are **six finite built-in palette families**, each with
light and dark variants:

| Palette | Caelum setting | Implemented appearances |
| --- | --- | --- |
| T3 Code | `t3-code` | Light, dark, follows system |
| T3 Chat | `t3-chat` | Light, dark, follows system |
| Grove | `grove` | Light, dark, follows system |
| Ocean | `ocean` | Light, dark, follows system |
| Ember | `ember` | Light, dark, follows system |
| Iris | `iris` | Light, dark, follows system |
| Original Caelum mint | `caelum` | Light, dark, follows system |

T3 Code's default desktop palette is represented by its light/dark constants;
it is named `t3-code` in this import. Upstream also supports custom themes,
JSON/VS Code imports, and Open VSX search. Those are extensible user libraries,
not additional finite built-ins. **Custom imports and a theme editor have not
been added to Caelum.**

Implemented in this change:

- Settings → General has separate **Appearance** and **Color theme** shadcn
  Select controls. Palette changes apply immediately and use the existing
  serialized, debounced settings save. Restart restores the saved choice.
- The default is T3 Code. Existing `desktop.theme` values retain their meaning;
  `desktop.color_theme` is additive. Old TOML files without it default to T3 Code.
  Other settings and the SQLite schema are unchanged. Caelum mint remains selectable.
- A literal-only TypeScript AST importer maps upstream semantic colors to
  shadcn CSS variables. It does not execute upstream TypeScript. Generated CSS
  records the source commit. Default dark canvas is `#0a0a0a`, surface `#111111`,
  accent `#346bf1`; controls use an 8px base radius. Destructive buttons use
  error-colored text on a tinted surface, avoiding fixed white labels over
  palettes whose error text color is deliberately bright.
- Functional headings replace promotional copy: “Dictation”, “Settings”, and
  explicit recording/empty-state instructions, including task-based setup steps. Existing navigation, controls,
  waveform behavior, keyboard support, and reduced-motion preference remain.
- Full upstream MIT attribution is in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)
  and is copied into native package documentation. This grants no new license
  to Caelum's own code.

The mapping adapts color roles to Caelum's shadcn components; it is not a pixel
copy of the T3 application. High contrast remains a Caelum override. The isolated
GTK layer-shell recording HUD does **not** consume frontend CSS and retains its
native styling. System window decorations also follow the desktop/compositor.
The initial HTML is dark T3 Code until saved settings load; a saved light or
nondefault palette can briefly transition at startup. A safe, minimal preference
cache could address that later.

To regenerate intentionally from an inspected upstream checkout:

```bash
node scripts/import-t3-themes.mjs /path/to/t3code
npm run check
```

Review the generated diff and update attribution when changing the pinned source.
No upstream dependency or network access is needed at application runtime.

## Request handling and failure behavior

| Area | Caelum today | T3 Code example | Appropriate improvement |
| --- | --- | --- | --- |
| Request path | React → Tauri command → Rust JSONL child → Python → HTTPX/provider; local daemon socket for service controls | Electron IPC for native operations; typed RPC/WebSocket sessions for server/provider work | Retain the local path; document ownership of each long operation |
| Contracts | TS method map, generated configuration shape, Python envelope/settings validation; several results are `unknown` and Rust parses generic JSON | Effect RPC payload/success/error schemas with authorization middleware; tagged desktop IPC errors | Generate runtime request/result schemas and stable error codes across TS/Rust/Python |
| Trust boundary | Tauri capabilities/CSP, a local child pipe, validation, sanitized provider errors | Electron checks sender WebContents and main frame; remote scope authorization | Test the existing Tauri boundary; do not copy Electron sender APIs into Tauri |
| Lifecycle | Pending request IDs; child disconnect drains requests and emits an event; UI requests restart | Scoped IPC registrations, session lifecycle, stream failure handling, connection diagnosis | Bound writes, replies, cleanup, and restart; make recovery state visible |
| Retry | HTTPX/provider retry handling already exists; cleanup failure preserves raw transcription | Explicit transient vs authentication/configuration/permission failures | Keep provider retry policy; never blindly replay start/stop or paid transcription |
| Persistence | Atomic TOML save and SQLite history; frontend autosaves are serialized and quit flushes pending saves | Separate packages and service boundaries for a larger multi-client application | Keep these protections; test upgrade/recovery and concurrent edits |

Evidence: [Caelum IPC client](../src/lib/ipc.ts),
[Rust engine](../src-tauri/src/main.rs), [Python sidecar](../python/caelum/sidecar.py),
[providers](../python/caelum/providers.py), [frontend lifecycle](../src/hooks/use-engine.ts),
[T3 desktop IPC][t3-ipc], [T3 RPC contracts][t3-rpc],
[T3 connection errors][t3-errors], and [T3 RPC sessions][t3-session].

### Specific unresolved Caelum risks

These findings are from the current source; the theme change does not fix them.
The failure scenarios below should become regression tests alongside each fix.

| Priority | Finding | Failure scenario and acceptance criterion |
| --- | --- | --- |
| P1 | `Engine.call` waits for the stdin mutex and `write_all` before starting the 180s reply timeout | A child stops consuming stdin. The entire call, including lock/write, must finish within its deadline; remove pending entries on every exit path |
| P1 | `Engine.close` performs two ordinary calls before its 12s child wait | An unresponsive child can delay shutdown far beyond 12s. Use one overall shutdown budget, then terminate/reap the child and clean up recording resources |
| P1 | Rust checks the 16MiB line limit after `next_line` has allocated the line | A malformed child writes an enormous unterminated frame. Enforce a byte limit while reading and test bounded memory plus disconnect behavior |
| P1 | Rust pending requests have no admission cap; all methods share a long timeout | Saturate the pipe with concurrent calls. Add bounded admission/backpressure, operation deadlines, and cancellation semantics. Python already caps active response tasks at 64 and limits input frames to 1MiB; preserve those controls |
| P1 | Runtime replies are generic JSON; malformed/version-mismatched frames are skipped | A wrong-version child or malformed success leaves UI waiting. Fail deterministically with a protocol error, validate results, and distinguish retryable errors from blocked state |
| P1 | Recovery currently asks for restart | Kill the sidecar while recording, idle, and saving. Reconcile daemon ownership before any bounded restart; never create two captures or silently discard retryable audio |
| P2 | Status polling emits at 10Hz and updates Zustand each time; history/summary invalidation is already gated on state changes | Measure idle renders, IPC volume, CPU, and DB reads; suppress unchanged idle status and throttle capture meter updates independently |
| P2 | `App.tsx`, settings, and sidecar dispatch combine many concerns | Extract autosave/lifecycle services and feature dispatch modules when adding behavior. Test boundaries rather than splitting files solely to resemble upstream |

A cancellation request is not proof that an HTTP operation, native audio handle,
or daemon has stopped. Include cancellation acknowledgments and final state in
the contract. Keep transcript text and credentials out of diagnostic logs; use
request IDs, method, elapsed time, sanitized error code, and opt-in diagnostics.

## Code practices worth adopting

T3's [CI workflow][t3-ci] includes pinned action commits, timeouts, caching,
change-aware jobs, formatting/lint/type/unused-code checks, generated-file checks,
and desktop/release smoke paths. Its scale justifies this separation. Caelum's
single Linux workflow already runs Ruff, pytest, privacy scanning, frontend
lint/tests/build, contract regeneration, Rust tests in packaging jobs, and package
installation/backend/audio probes. Those are useful existing gates.

Improve Caelum incrementally:

1. Pin third-party Actions by SHA and automate updates. Pin/test the Rust and
   Node toolchains and explicitly document the rolling Arch/system-Python policy.
2. Run inexpensive Rust formatting/lint/tests before the full distribution matrix.
   Cache Rust and dependency builds with keys that include distro/toolchain/locks.
   Avoid rebuilding the same commit on main and tag without promotion controls.
3. Add transport fault tests (stalled pipe, invalid/oversized response, child
   termination, timeout cleanup) and upgrade tests that load actual older TOML
   and SQLite snapshots. Do not accept a type-only contract as runtime validation.
4. Add actual UI keyboard checks for dialogs/selects, focus return, narrow windows,
   and saving errors. Verify semantic contrast in every palette and appearance;
   changing colors does not prove WCAG conformance.
5. Retain real waveform energy and useful error/empty states. Avoid fake activity,
   giant welcome headlines, extra cards for every setting, and claims such as
   “seamless”, “production ready”, or “works on all Linux distributions” without
   a defined acceptance result.
6. Review the Vite entry chunk warning (about 627kB minified in this build) against
   measured startup and memory. Lazy loading already exists for some screens;
   split further only where measurement shows a benefit.

## Release management and actual downloads

Latest stable observed: **T3 Code v0.1.9**, published **11 November 2026 at
11:33:49 UTC** ([release][t3-release]). Caelum comparison: **v0.4.0**, published
**13 November 2026 at 14:40:55 UTC** ([release][caelum-release]).
These are release snapshots, not an assertion that every historical release
has the same assets.

| Platform / channel | T3 Code v0.1.9 / publishing source | Caelum v0.4.0 |
| --- | --- | --- |
| Linux desktop x86_64 | `.AppImage`, `amd64.deb` | Arch `.pkg.tar.zst`; separate Debian 12, Ubuntu 24.04 and 26.04 `.deb`; Fedora 43 `.rpm` |
| Linux desktop arm64 | `.AppImage`, `arm64.deb` | No published arm64 package |
| Arch repository | `t3code-bin` and `t3code-nightly-bin` AUR recipes repackage the official x86_64 AppImage; automated AUR workflow | Native Arch binary package attached to GitHub; no equivalent automated AUR publication in the reviewed workflow |
| Fedora / RPM | No RPM in the sampled stable release. AppImage is the available Linux format, subject to host compatibility | Dedicated Fedora 43 RPM |
| macOS | x64/arm64 DMG and ZIP, with blockmaps | Not targeted |
| Windows | x64/arm64 EXE, with blockmaps | Not targeted |
| CLI | Linux x64/arm64 tarballs, Windows x64/arm64 ZIPs, Darwin arm64 tarball in this sample | CLI included in native Linux packages |
| Update metadata | Platform YAML feeds and `SHA256SUMS`; blockmaps for applicable desktop assets | Signed `update.json` and detached signature containing package hashes |
| Trains | Stable, nightly, manual preview; preview stays draft and is excluded from normal updates | Stable version tags, with a draft until all package uploads finish |

Upstream evidence: [release orchestrator][t3-release-flow],
[desktop builds][t3-desktop-build], [AUR documentation][t3-aur],
[AUR workflow][t3-aur-flow]. Caelum evidence:
[release workflow](../.github/workflows/release.yml),
[package builder](../scripts/build_package.py), and [Linux notes](linux.md).
A format is not a distro support guarantee. Neither AppImage availability nor
installing a package in CI establishes working Wayland capture, overlay, tray,
or microphone access on every user's system.

Caelum vendors locked Python wheels, so users do not manually install pip
dependencies. It still uses **system Python** and native system libraries.
Packages constrain Python's minor version: Debian 12 uses 3.11, Ubuntu 24.04
3.12, and the current Ubuntu 26.04/Arch/Fedora 43 targets use 3.14. In particular,
rolling Arch Python upgrades need coordinated rebuilds. GTK4/GObject/layer-shell
remain requirements of the isolated HUD; the main UI uses WebKitGTK via Tauri.
Do not describe this as a single dependency-free binary.

### The messages upstream shows on GitHub

The sampled stable release opens with:

> **v0.1.9** · 198 changes from 31 contributors

One of its seven outcome-focused highlights is:

> **Send during uploads.** Send messages with attachments while they are still uploading.

It then says “Plus 164 more bug fixes and performance improvements.” and places
PR/author details in a collapsible **Full changelog**, with contributor and compare
links. The release page is the evidence for shipped wording; filenames above
come from the actual attached assets.

The [release-note generator][t3-notes] is **AI-assisted**. Its prompt limits notes
to seven bullets, each with a short feature label and a sentence of at most 20
words; it prohibits hype, implementation details, and PR numbers in highlights.
Concise writing comes from constraints and review, not an absence of AI tooling.
Caelum should apply the same editorial discipline while reviewing every statement
against the exact release contents and test evidence.

Caelum's current notes describe the architecture transition, preserved engine,
Wayland workaround, and limitations in paragraphs. Add a small download/support
table, upgrade notes, user-visible highlights, and a full changelog link. Use
[release-template.md](release-template.md) as a concrete starting point. Keep
known limitations prominent rather than burying them beneath marketing copy.

### Safer release workflow for Caelum

Upstream separates preview/nightly/stable and keeps releases draft until required
assets and metadata are ready. Caelum already waits for all five matrix builds
before publication and signs its update manifest; preserve both protections.
Its current `gh release create` step is not idempotent when a rerun finds an
existing draft, and main/tag runs can duplicate expensive builds.

Recommended sequence:

1. Build a candidate from an immutable commit through manual dispatch or an RC
   train. Record commit, toolchains, lock digests, target distro, and test evidence.
2. Install and launch each candidate on the target distro. Run IPC, simulated
   audio, update signature, native-window, and documented manual acceptance gates.
3. Promote the exact verified artifact set. Create/reuse a draft idempotently;
   upload all expected files, verify their sizes/hashes, and sign the final manifest.
4. Publish once the complete set is validated. Never move a published version tag
   or replace a stable asset under the same version. Ship a new patch for fixes.
5. Keep candidate builds out of the stable updater. Document signing key rotation,
   compromise recovery, and rollback/version policy. Checksums help integrity;
   signatures add a separate trust mechanism and should not be conflated.

## Public-release action list and acceptance gates

| Priority | Required work | Evidence needed before claiming completion |
| --- | --- | --- |
| P0 | Choose and add Caelum's project license; audit redistribution notices | Owner-approved license, consistent package metadata, license/notice inventory included in each package. No license was chosen automatically |
| P1 | Fix sidecar deadline, framing, admission, and failure contracts above | Repeatable failure-injection tests with bounded memory, time, and process count |
| P1 | Qualify supported Linux sessions | Real microphone/provider tests; hold/toggle shortcuts on Hyprland and portal fallback; overlay placement/input; tray/background close/reopen; MPRIS pause/resume; device removal; lock/suspend/resume; NVIDIA startup/resize; cancellation/retry and credential failures |
| P1 | Qualify install/upgrade/update per distro | Clean install, GUI launch, simulated and physical audio, upgrade from an existing install, retained config/history, valid/invalid manifest signatures, uninstall behavior. CI backend smoke is one part of this gate |
| P1 | Stage and promote immutable releases | Candidate-to-stable drill; interrupted-upload rerun; no partial update feed or tag movement |
| P2 | Publish an honest support matrix | Explicit qualified vs best-effort distro/version/architecture/session rows; Python ABI and native dependency requirements |
| P2 | Make maintenance and reporting possible | CONTRIBUTING, SECURITY policy, issue templates with sanitized diagnostics; no automatic upload of transcripts or keys |
| P2 | Complete appearance/accessibility qualification | Keyboard navigation, focus, contrast, 100–200% scaling, narrow windows, high contrast, reduced motion, startup preference behavior across palettes |

The missing license is an owner decision. Physical/provider and compositor
qualification cannot be inferred from this machine's unit tests. Existing
[acceptance](acceptance.md), [verification](verification.md), and
[privacy](privacy.md) documents remain relevant. Do not promise “no bugs”; publish
what was tested, limitations, and how failures can be reported and reproduced.

## Verification of this change

- Frontend ESLint, strict TypeScript/Vite build, and **16 component/integration
  tests** passed. Includes palette selection, settings.save persistence/reload,
  independent appearance, legacy/default handling, and live system preference
  change/listener cleanup. jsdom pointer API stubs support testing real Radix
  Select interactions; these are not a native keyboard/accessibility audit.
- Ruff and **310 pytest tests** passed; **4 tests skipped** for physical/session
  requirements. Added legacy TOML and 21 palette/appearance roundtrips, plus
  invalid value rejection.
- **3 Rust tests** passed. Native Tauri release build passed.
- Local Arch package built with locked Python wheels; its documentation includes
  `THIRD_PARTY_NOTICES.md`. No new package was installed into the user's system.
- `21st review` found four informational hardcoded-color notices in high-contrast
  token definitions. These intentional accessibility override tokens were retained;
  no hardcoded component colors or decorative gallery were added. A second review of the
  shared Button identified broad transitions and disabled pointer handling.
  Transitions now target colors/borders/shadows only; the conventional shadcn
  disabled pointer behavior was retained.
- All **14 palette/appearance combinations** launched as native WebKit windows
  from an extracted local Arch package in isolated Xvfb/D-Bus sessions. The
  screenshots were visually inspected as a contact sheet. This checks rendering
  and configuration loading, not Wayland behavior or interactive accessibility.
- Privacy scan, generated-contract check, Rust formatting, and changed-source
  formatting checks passed. Physical microphone, provider, and all-distro
  qualification were not performed for this theme change.

## Source index

Pinned links keep this review reproducible even when upstream moves.

[t3-palettes]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/packages/shared/src/themePalettes.ts
[t3-theme-runtime]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/apps/web/src/themePalette.ts
[t3-css]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/apps/web/src/index.css
[t3-ipc]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/apps/desktop/src/ipc/DesktopIpc.ts
[t3-rpc]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/packages/contracts/src/rpc.ts
[t3-errors]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/packages/client-runtime/src/connection/errors.ts
[t3-session]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/packages/client-runtime/src/rpc/session.ts
[t3-ci]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/.github/workflows/ci.yml
[t3-release]: https://github.com/pingdotgg/t3code/releases/tag/v0.1.9
[caelum-release]: https://github.com/Parth-Jadhav-2004/caelum/releases/tag/v0.4.0
[t3-release-flow]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/.github/workflows/release.yml
[t3-desktop-build]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/.github/workflows/release-desktop.yml
[t3-aur]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/packaging/aur/README.md
[t3-aur-flow]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/.github/workflows/publish-aur.yml
[t3-notes]: https://github.com/pingdotgg/t3code/blob/f313d0a6cb843551fb60e57a454a71e71a3a8c04/scripts/generate-release-notes.ts
