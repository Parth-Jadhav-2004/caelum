# Phase 1 qualification checklist

Implementation is complete enough to run locally; production/release acceptance is intentionally separate from mocked tests. No unchecked item below is claimed as passed.

## Automated evidence available

- [x] Lossless PCM/WAV encoding, bounded capture, quiet-audio retention, hysteresis.
- [x] Multipart Groq contract, sample offsets, bounded rate-limit retries, sanitized failures.
- [x] Cleanup timeout/raw fallback, number/URL/repetition validation, no false refining state when disabled.
- [x] Timestamp seam matching, spoken repetition retention, missing/conflicting seam repair.
- [x] Single final dispatch, no transcript in HUD messages, cancellation, retry expiry, retry blocking.
- [x] Focus/PID safety and distinct clipboard fallback.
- [x] Native layer-shell overlay, keyboard NONE, exclusive zone 0, empty region protocol request.
- [x] Compact 280×96 native surface containing the 232×48 pill; pinned output; unchanged active-window identity across state replay.
- [x] Reversible native hotkey registration and context cancellation enable/disable.
- [x] Real microphone start and cancellation with no cloud upload.
- [x] Actual visible synthetic-text insertion into a disposable native GTK entry.

## Manual/device/provider qualification still required

- [ ] Credential-authenticated Groq and GPT-6 Luna requests; account-specific model access.
- [ ] Paired real-provider corpus benchmark and release-to-visible-insertion p50/p90/p95.
- [ ] Short/long/noisy/quiet/multilingual utterances, punctuation commands, identifiers and code.
- [ ] Physical push/release in both modifier orders, autorepeat, rapid start/cancel/restart, modifier conflicts.
- [ ] Pointer click/scroll/touch through pill **and shadow** to a controlled underlying app (empty input region is verified at protocol level; physical delivery is separate).
- [ ] Browser/editor/chat/terminal/office caret focus, paste, closing target, changing focus/workspaces, fullscreen.
- [ ] Screen reader announcements, high contrast, reduced motion, toolkit text scaling, visual comparison with SVG.
- [ ] 100/125/150/200% scale, mixed monitors, small work areas, bottom dock reservations and output unplug.
- [ ] Physical lock/suspend during capture/finalization; no post-unlock microphone restart or late insertion.
- [ ] HUD crash, daemon hard kill, config reload, device unplug, actual network/rate-limit failures, notification recovery actions.
- [ ] Physical key-down to first visible feedback ≤100 ms warm; cold-start measurement reported separately.

Run native tests only in an interactive Omarchy login with the repository daemon stopped. The insertion fixture temporarily focuses its own test window, restores the previous active window, and preserves a text clipboard in memory. Test clipboard data is never logged; non-text clipboard formats are outside this fixture's preservation guarantee.

## Phase 2 desktop evidence

- [x] Atomic settings round-trip, private permissions, failed-save preservation.
- [x] Opt-in persistence creates no database while disabled; final-only schema; deduplicated session IDs.
- [x] Literal search, deletion, retention, sensitive export, rate snapshots, retained-data aggregate math.
- [x] Pause/cancel/resume and completion hook after final insertion; storage-hook failure never retries insertion.
- [x] Idle settings reload, microphone changes, shortcut-conflict rollback, active-session rejection.
- [x] Native GTK smoke check mounts all four pages and applies both themes with isolated storage.
- [ ] Physical shortcut recorder and conflicting-shortcut apply/recovery through the complete UI.
- [ ] Physical device selection/disconnect and local input-meter test across USB/Bluetooth hardware.
- [ ] Real dictation saved through the daemon, then searched/copied/exported/deleted through the UI.
- [ ] App-launcher discovery and actual next-login autostart with credentials.
- [ ] Screen-reader navigation, large fonts, mixed-DPI monitors, packaging/upgrade and crash-recovery qualification.

System tray, other operating systems, and encrypted database support remain future work, not passed acceptance items.
