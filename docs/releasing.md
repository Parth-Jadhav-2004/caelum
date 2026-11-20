# Building and promoting Caelum releases

## Branches and release channels

Develop on short-lived branches and integrate through pull requests to `dev`. Keep `main` stable. Before building an RC, bring any changes from `main` into `dev` so the release can fast-forward to the tested commit.

| Channel | GitHub release | Installation |
| --- | --- | --- |
| Testing | Prerelease such as `v0.5.0-rc.1`, then `v0.5.0-rc.2` | Explicit manual download |
| Stable | Latest, such as `v0.5.0` | Native package or signed stable updater |

Both channels use the same candidate package bytes. Development builds are Actions artifacts. The `testing` and `release` GitHub Environments control publication permissions. The `testing` environment accepts deployments from `dev` and `main`. The `release` environment accepts only `main` and holds the signing secrets and production approval.

## Build once

1. Set the package version in npm, Python, Rust, Tauri, their lockfiles and the Arch recipe. Add a `## X.Y.Z` section to CHANGELOG.md describing changes since the previous stable. Both release bodies use this section.
2. A push to dev or main builds a candidate. For a site-only commit, dispatch `gh workflow run release.yml --ref dev` (or `--ref main` for a candidate on stable) if packages are needed. Inspect the seven downloads and smoke evidence. Record the successful run ID, attempt and full source SHA. The candidate is eligible for seven days. Actions retains its artifacts for fourteen.
3. Choose the next unused RC number for this version, starting at 1. Run IDs from the previous convention do not reserve the new sequence.

## Publish a selected RC

Dispatch from the branch whose current tree matches the candidate. For example, after reviewing run `$RUN` and selecting RC number `$RC`:

```sh
gh workflow run publish.yml --ref dev -f channel=testing -f candidate_run_id="$RUN" -f rc_number="$RC" -f desktop_qualified=false
```

Use `--ref main` for a candidate on `main`. The publisher checks the run, attempt, tree, hashes and locks, then attaches the packages, `SHA256SUMS` and `provenance.zip`. The archive contains `candidate.json` and the five `build-info-*.json` records. Testers can check their download with `sha256sum --check --ignore-missing SHA256SUMS`. Back up settings and history or use a disposable profile. Include the tag, run, attempt, SHA, filename and hash with a bug report.

## Promote the accepted bytes to Stable

Complete [desktop acceptance](acceptance.md) on the selected RC and record the results with its commit, run and attempt. The [0.5.0 qualification issue](https://github.com/Parth-Jadhav-2004/caelum/issues/26) records the Linux desktop and signed-upgrade checklist. A change to the candidate bytes requires a new RC.

All pull requests target `dev`. After required checks and desktop acceptance pass, verify that the candidate SHA is still the tip of `dev` and that `main` is its ancestor. Fast-forward `main` to that exact SHA without a force push. Verify the remote commit matches the candidate, then dispatch from `main` with the same run and RC number.

```sh
gh workflow run publish.yml --ref main -f channel=production -f candidate_run_id="$RUN" -f rc_number="$RC" -f desktop_qualified=true
```

The release job downloads the candidate and verifies every public RC asset against it before signing update metadata. Only this job can mark the stable tag Latest. The stable updater reads signed metadata from Latest. Pages regenerates its download inventory from the published stable assets.

## Interrupted releases and recovery

Retry the same dispatch with the same run, attempt and RC number. Publication resumes a matching draft and checks an already-published release. Existing uploads must match exactly. For an incomplete draft upload, inspect the failed asset before removing it in GitHub. Rebuilding or rerunning the build can produce different bytes and requires a fresh RC number and acceptance.

Signing uses the candidate creation time. An expired candidate needs a fresh build, even if Actions still retains the artifact. A tag alone is insufficient evidence of publication. Keep older stable assets available for explicit, maintainer-guided recovery after checking data compatibility.

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
