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

Keep offline backups and restricted access to the release key. Manifest expiry
remains 90 days, so an old manifest cannot be treated as indefinitely current.
If the key is lost or compromised, disable promotion/signing, revoke its CI
secret, publish an incident notice without secrets, and distribute a reviewed
package containing a replacement trusted public key through a trusted channel.
The current updater pins one public key: uploading a newly signed manifest alone
cannot rotate that trust. Seamless in-app key rotation would require a separate,
reviewed transition design; it is not claimed by this implementation.

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
