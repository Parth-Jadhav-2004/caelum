# Contributing to Caelum

Open short-lived branches against `main`. While [#26](https://github.com/Parth-Jadhav-2004/caelum/issues/26) holds main, send application changes to `dev` and keep website-only changes independent. After acceptance, main can fast-forward to the tested commit and development can return to trunk.

Stable is GitHub Latest (`vX.Y.Z`). Testing releases use `vX.Y.Z-rc.N`. Ordinary builds stay in Actions. Include user-visible changes in the next version’s CHANGELOG section.

Use the pinned Node/Rust toolchains, locked npm/Python/Cargo dependencies, and the
commands in [README.md](README.md) and [docs/releasing.md](docs/releasing.md).
Run relevant tests before opening a change. For IPC changes, regenerate both
contracts and add a failure-path test; see [docs/ipc.md](docs/ipc.md).

Keep capture/provider/history logic in Python and UI components in React/shadcn.
Use semantic theme tokens, real recording state, accessible labels, keyboard
controls, and reduced motion. Keep release notes factual and user-facing.
Do not add fabricated waveform activity, transcript telemetry, or credentials
in logs, screenshots, fixtures, issue reports, or build artifacts.

Use temporary XDG directories for tests. Hardware/provider/compositor tests require
explicit local setup; skipped tests do not establish platform compatibility.
Document the distro, desktop session, device class and provider tested without
including audio, API keys or private transcripts.

Report reproducible bugs with the issue template. For security concerns follow
[SECURITY.md](SECURITY.md). Caelum is MIT-licensed; preserve the project license and third-party notices.
