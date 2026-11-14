# Building and promoting Caelum releases

## Checks and candidates

Pull requests and main pushes run `Checks`: Ruff, pytest, privacy scanning,
ESLint, component tests, strict TypeScript/Vite, generated-contract checks,
workflow linting, Rust formatting, Clippy, and Rust tests. Toolchains are declared
in `.node-version` and `rust-toolchain.toml`; CI pins uv and every external Action.
Dependabot proposes updates for Actions, npm, Cargo, and uv dependencies.
Rust caches are separated by target distro, architecture, toolchain and locks.
PRs and version tags do not build/publish a full release automatically.

`Linux candidate` is a manual workflow. It first runs the checks, then builds
Ubuntu 24.04/26.04, Debian 12, Fedora 43, and Arch x86_64 packages in their target
containers. Each package is installed and checked through the CLI, JSONL IPC,
an isolated PulseAudio server, and a real WebKit/Xvfb launch. The frontend emits
an opt-in test marker only after its bootstrap/configuration loaded. A live
process or screenshot alone is not considered sufficient. Smoke screenshots
and logs are retained for 14 days, including on failure.

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
2. Write `docs/release-<version>.md` using [release-template.md](release-template.md).
   Lead with actual user-visible changes. Include download/support, upgrade,
   known-limitations, test evidence, and full-changelog links. Remove placeholders.
3. Merge the release commit to the default branch, then start a candidate:

   ```sh
   gh workflow run release.yml --ref main
   gh run list --workflow release.yml
   gh run view <candidate-run-id>
   ```

4. Download and inspect the candidate and its smoke evidence. Complete
   [acceptance.md](acceptance.md) on actual supported desktops/providers. Test
   clean installation, upgrade/data preservation, and the signing/update path.
   Record the exact candidate run, SHA, distro/session and outcomes in the release
   environment approval record or a linked qualification issue. If release notes
   or code need changes, commit them and build a new candidate from that commit.
   Do not relabel unchecked platforms qualified.
5. Promote the successful candidate from the default branch:

   ```sh
   gh workflow run publish.yml --ref main \
     -f candidate_run_id=<candidate-run-id> -f desktop_qualified=true
   ```

   The checkbox is a maintainer attestation, not an automated hardware test.
   The workflow verifies the run belongs to this repository's candidate workflow,
   originated on the default branch, and completed successfully. A candidate
   older than seven days, from a different run attempt, or with mismatched
   source/locks/checksums is rejected.
6. The `release` environment holds `CAELUM_UPDATE_SIGNING_KEY` (Ed25519).
   Promotion checks out the candidate's exact source, downloads its exact bytes,
   verifies all files, signs the existing update format, and attaches
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

## Public testing prereleases

When automated candidate checks pass but manual acceptance is incomplete, publish
only a clearly labeled GitHub prerelease (for example `v0.4.1-rc.1`) at the exact
candidate SHA. Download `release-candidate`, run `scripts/release_candidate.py verify`
with its source SHA/run/attempt, and attach those verified packages and provenance
unchanged, plus `SHA256SUMS`. Use `gh release create --prerelease --latest=false`
and the reviewed release notes. Do not run stable promotion, attest desktop
qualification, or attach signed stable updater metadata. Package versions remain
the candidate version; installing the prerelease is an explicit package-manager
action. Any later package/code change needs a new candidate and prerelease tag.

## Interrupted releases and recovery

Rerun `Promote Linux candidate` with the same successful run ID. Signing uses the
candidate creation time, so update metadata and signatures are deterministic.
Identical uploaded assets are preserved; no upload uses `--clobber`.
If GitHub leaves a draft asset in an incomplete upload state, inspect it and
remove only that failed draft upload before retrying. Never delete/replace a
published stable asset or force a published tag. Ship a new patch instead.
When a candidate expires, build a fresh candidate with a new version if a draft
already contains different bytes; do not mutate the old version's assets.

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
