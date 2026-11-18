# Building and promoting Caelum releases

## Release channels

- **Development:** every successful main-branch candidate publishes
  `v<version>-dev.<candidate-run-id>.<attempt>` as a GitHub prerelease, never Latest.
  Use this for early feedback. Website-only pushes and PRs do not publish packages.
- **Testing:** maintainers select a successful main candidate in `publish.yml`,
  channel `testing`. It publishes `v<version>-rc.<candidate-run-id>` without
  rebuilding. These are explicit, manual package-manager installations.
- **Production:** `publish.yml`, channel `production`, requires the same candidate
  to exist as a complete published testing release, completed manual acceptance,
  and approval in the protected `release` environment. It signs metadata and
  publishes `v<version>` as Latest. Only production enters automatic updates.

Development and testing never receive the production signing key or publish
stable update metadata. All channels retain immutable packages, source/run/attempt
provenance, per-package SHA-256 hashes, and resumable draft uploads. Testing
versions must be higher than the current production version.

Preview package versions are the base version; source SHA and release tag identify
the exact build. Preview packages currently replace the same native package and
share its configuration/history paths. They are not side-by-side installations;
back up user data or use a separate test account/VM before testing upgrades.

## Checks and candidates

Pull requests and main pushes run `Checks`: Ruff, pytest, privacy scanning,
ESLint, component tests, strict TypeScript/Vite, generated-contract checks,
workflow linting, Rust formatting, Clippy, and Rust tests. Toolchains are declared
in `.node-version` and `rust-toolchain.toml`; CI pins uv and every external Action.
Dependabot proposes updates for Actions, npm, Cargo, and uv dependencies.
Rust caches are separated by target distro, architecture, toolchain and locks.
PRs and version tags do not build/publish a full release automatically.

`Linux candidate` runs on main pushes (except website-only
changes), or manually through `release.yml`. It first runs the checks, then builds
Ubuntu 24.04/26.04, Debian 12, Fedora 43, and Arch x86_64 packages in their target
containers. Each package is installed and checked through the CLI, JSONL IPC,
an isolated PulseAudio server, and a real WebKit/Xvfb launch. The frontend emits
an opt-in test marker only after its bootstrap/configuration loaded. A live
process or screenshot alone is not considered sufficient. Smoke screenshots
and logs are retained for 14 days, including on failure.
`Publish development release` starts only after that candidate succeeds. Its
separate workflow lets a failed publication resume without rebuilding packages
or changing the candidate's run attempt. The privileged workflow-run handler
verifies workflow identity, repository, main branch, source SHA and successful
conclusion before checking out the candidate or granting publication permissions.

The GUI check uses X11/software rendering and, only inside root smoke containers,
a process-scoped WebKit sandbox override. Normal application launches keep their
usual sandbox and graphics configuration. This does not qualify Wayland,
layer-shell placement, hardware, screen readers, or provider credentials.

The assembled `release-candidate` artifact contains exactly five packages,
per-target build provenance, and a checksum manifest tied to the workflow run,
attempt, source SHA, version, and lockfile hashes. Candidates are unsigned and
are never placed in the stable update feed. Python wheels are vendored, but the
host's Python minor version and native libraries remain package requirements.
Arch is rolling; its container/native libraries need current rebuild qualification.

## Release procedure

1. Choose a new stable `major.minor.patch` version. Update `pyproject.toml`,
   `package.json`/lockfile, `src-tauri/Cargo.toml`/lockfile, and
   `src-tauri/tauri.conf.json` together. Existing published versions cannot be reused.
2. Add a newest-first `## <version>` entry to [CHANGELOG.md](../CHANGELOG.md) using [release-template.md](release-template.md).
   Lead with actual user-visible changes. Include download/support, upgrade,
   known-limitations, test evidence, and full-changelog links. Remove placeholders.
3. Merge the release commit to the default branch. Its candidate/development build
   starts automatically. Inspect it, or start a fresh main candidate manually:

   ```sh
   gh workflow run release.yml --ref main
   gh run list --workflow release.yml
   gh run view <candidate-run-id>
   ```

4. Publish the candidate to testing:

   ```sh
   gh workflow run publish.yml --ref main -f channel=testing \
     -f candidate_run_id=<candidate-run-id> -f desktop_qualified=false
   ```

   Install the RC packages and inspect its provenance and smoke evidence. Complete
   [acceptance.md](acceptance.md) on actual supported desktops/providers. Test
   clean installation, upgrade/data preservation, and the signing/update path.
   Record the exact candidate run, SHA, distro/session and outcomes in the release
   environment approval record or a linked qualification issue. If release notes
   or code need changes, commit them and build a new candidate from that commit.
   Do not relabel unchecked platforms qualified.
5. Promote the same testing candidate to production from the default branch:

   ```sh
   gh workflow run publish.yml --ref main -f channel=production \
     -f candidate_run_id=<candidate-run-id> -f desktop_qualified=true
   ```

   The checkbox is a maintainer attestation, not an automated hardware test.
   The workflow verifies the run belongs to this repository's candidate workflow,
   originated on the default branch as a push/manual build, and completed successfully. A candidate
   older than seven days, from a different run attempt, or with mismatched
   source/locks/checksums is rejected.
6. The existing `release` environment is production's protected environment and
   holds `CAELUM_UPDATE_SIGNING_KEY` (Ed25519). The new `development` and `testing`
   environments allow only main-branch deployments and contain no signing key.
   Promotion checks out the candidate's exact source, downloads its exact bytes,
   verifies all files against the published RC, signs the existing update format, and attaches
   `SHA256SUMS`, provenance, and update metadata. It does not rebuild packages.
   The private key must match `python/caelum/update-public.pem`.
7. The publisher creates or reuses a draft, verifies every existing remote asset
   by downloading and hashing it, uploads only missing files, verifies the final
   set, and then publishes. A matching published release is a no-op. Different
   assets, unexpected uploads, tag movement, and stable-version rollback fail.

Set required `source` and `native` checks in branch protection, and protect the
`release` environment with the repository's maintainer review policy. These
GitHub repository settings are administrative configuration, separate from the
checked-in workflows. Keep signing access out of candidate and pull-request jobs.
Restrict all three environments to the main branch. Remove legacy `v*` tag
deployment permissions from `release`, so an old tag's workflow cannot bypass
the current testing-to-production gate. Keep the existing reviewers and signing
secret in `release`; no secret migration is needed.

## Reporting preview bugs

Use the GitHub bug-report form and choose Development, Testing, or Production.
Include the full release tag, package filename, source SHA, distro/session and
reproduction steps. The same package version may have multiple development builds;
the base version alone cannot identify a regression. Never attach keys, audio,
transcripts or unredacted provider responses. Fixes need a new commit/candidate;
never replace an existing release asset with repaired bytes.

## Interrupted releases and recovery

Rerun `Promote to testing or production` with the same channel and successful run ID. Signing uses the
candidate creation time, so update metadata and signatures are deterministic.
Identical uploaded assets are preserved; no upload uses `--clobber`.
For a failed development publication, rerun `Publish development release`, or
dispatch `development.yml` with the original `candidate_run_id`. Do not rebuild a
successful candidate merely to retry an upload.
If GitHub leaves a draft asset in an incomplete upload state, inspect it and
remove only that failed draft upload before retrying. Never delete/replace a
published stable asset or force a published tag. Ship a new patch instead.
When a candidate expires, build a fresh candidate with a new version if a draft
already contains different bytes; do not mutate the old version's assets.
Candidates must be promoted within seven days; GitHub artifacts/smoke evidence
are retained for fourteen days. Rerunning a candidate build changes its attempt
and can change bytes: use a new workflow run before publishing a new RC rather
than trying to reuse its old `-rc.<run-id>` tag.

On a failed release after tag creation, the tag still identifies the candidate
commit; its existence does not imply a published release. The updater follows
published stable releases, not candidate artifacts or draft tags.

A stable updater rollback is not automatic. Keep older immutable release assets
available for an explicit maintainer-guided package downgrade after checking
configuration/database compatibility. Never point the latest feed backward.

## Signing key rotation

`python/caelum/update-trust.json` is an installed, package-owned trust policy.
It supports up to four Ed25519 public keys, SHA-256 DER fingerprints, activation
and expiry timestamps, and explicit revocation. A missing policy preserves the
old pinned-key behavior; a present malformed or inactive policy fails closed.
No user/XDG file or downloaded public key can expand this trust.

Normal releases still sign with the original key. To prepare a rotation:

1. Generate/protect a replacement private key outside this repository. Keep its
   private value out of logs and source. Add only its public PEM to the policy:

   ```sh
   python3 scripts/manage_update_keys.py add /path/to/new-public.pem \
     --not-before <unix-time> --not-after <unix-time>
   ```

2. Ship a bridge package containing both public keys. Review the policy diff and
   validity window, build a new candidate, and sign this bridge with the existing
   release key. No production key was rotated by this refactor.
3. For subsequent releases, put the new primary private key in
   `CAELUM_UPDATE_SIGNING_KEY` and retain the original key in the optional
   `CAELUM_LEGACY_UPDATE_SIGNING_KEY` release-environment secret. The publisher
   emits a bounded `update-signatures.json` bundle plus the original 64-byte
   `update.json.sig`. Older clients continue verifying the original signature;
   newer clients select a signature matching an active installed key. Clients
   skipping the bridge can still verify/install the dual-signed package.
4. To revoke a key for newer clients, use
   `python3 scripts/manage_update_keys.py revoke <fingerprint>` and ship the
   reviewed policy in a package authenticated by another active key. The helper
   refuses to remove the last active key. It never edits an installed user's policy.

New manifests keep schema 1 and the same package hashes/90-day expiry. Staged
multi-signature bundles are reverified by the privileged installer against the
installed policy before invoking a package manager. Rotation without the original
compatibility signing key is refused by the publisher, rather than silently
breaking old updaters. Tests include the frozen v0.4.0 verifier.

If a key is compromised, disable promotion, revoke its CI secret and distribute
an incident notice and trusted recovery package. Old clients that only know that
compromised key require a trusted out-of-band update; dual signing cannot undo
trust already granted to a compromised key. Do not claim otherwise.

## Local verification

```sh
npm ci
npm run check
uv sync --locked --extra dev
uv run ruff check python tests scripts
uv run pytest -q
uv run python scripts/generate-contracts.py
cargo fmt --manifest-path src-tauri/Cargo.toml -- --check
cargo clippy --locked --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --locked --manifest-path src-tauri/Cargo.toml
bash scripts/check-workflows.sh
python3 scripts/build_package.py arch --output /tmp/caelum-packages
```

Run the package builder in the target distro for other packages. Never infer
all-distro qualification from a local Arch build. `tests/test_release_pipeline.py`
exercises checksum/origin/expiry checks and interrupted/immutable publication with
an in-memory GitHub implementation and temporary signing keys; it never publishes.
