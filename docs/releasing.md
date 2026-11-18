# Building and promoting Caelum releases

## Release channels: dev → testing → main

1. Commit a unique base version to `dev` (Python, npm, Rust, Tauri, locks and Arch recipe), with reviewed CHANGELOG notes. `Checks` runs on PRs and all three branches; `Linux candidate` builds on dev only. A push changing only website files needs a manual `gh workflow run release.yml --ref dev` if it is to be packaged. Each of five native packages must install, pass IPC, simulated audio and native WebKit bootstrap; inspect the smoke artifacts. These checks do not qualify physical desktops.
2. Optional manual development publication: `gh workflow run development.yml --ref dev -f candidate_run_id=RUN`. All preview installs share stable profile paths and replace the installed package. Back up settings/history or use a disposable account. Dev tags use `vVERSION-dev.RUN.ATTEMPT`.
3. Open a **dev → testing** PR only after the successful dev build; require source, native and promotion-route checks. Use a merge commit to retain the source SHA. The accepted tree must match the candidate exactly. Then `gh workflow run publish.yml --ref testing -f channel=testing -f candidate_run_id=RUN -f desktop_qualified=false`. This publishes `vVERSION-rc.RUN` without rebuilding. Verify all assets anonymously against SHA256SUMS. Rerunning the same dispatch resumes/verifies existing bytes.
4. On that RC, complete [manual acceptance](acceptance.md), including GNOME Wayland, Plasma Wayland, X11, physical capture with both engines, lifecycle and staged signed upgrade/recovery. Record SHA, run/attempt, package hash, environment, tester and outcomes. Failed checks require a new dev candidate. Do not open the **testing → main** promotion until this evidence is accepted. Require independent review of the qualification evidence. Merge only the tested tree.
5. After merge, dispatch `gh workflow run publish.yml --ref main -f channel=production -f candidate_run_id=RUN -f desktop_qualified=true`. The protected `release` environment requires maintainer approval; only this environment holds signing keys. Verification binds the successful dev build to the promotion tree and rehashes all published testing assets before signing. Production alone becomes Latest and enters stable updates. Pages deploys from main and regenerates the stable inventory.

Restrict development, testing and release environments to their respective **dev**, **testing** and **main** branch (no tags). Protect testing/main from direct pushes including administrator bypass, force pushes and deletions. Require `source`, `native`, `promotion-route` on both; require main PR approval. Do not authorize a production deployment to rehearse an upgrade. Artifacts and smoke logs last 14 days, but candidate eligibility expires after seven days. If the gate expires, build and qualify a fresh dev run.

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
