# Signed releases and in-app updates

## User experience

Official x86-64 native packages built with a pinned update key check the latest
**stable** GitHub release when the desktop app opens. The Settings footer can also
check manually. Manual checks also look for testing releases, including newer
candidates with the same package version. A testing build gets a separate
**Download testing build** action opening its GitHub release page for explicit
package-manager installation. It is never staged as an unsigned automatic update.
Development builds stay in Actions. Testing uses numbered `vX.Y.Z-rc.N` prereleases.
Stable uses `vX.Y.Z`. Manual testing discovery checks up to 100 releases.
Use **View releases** to browse the full history. Maintainers promote identical
packages through the channels; see [releasing.md](releasing.md).
Official packages record the source commit and source date so the check can
recognize the installed build and avoid offering older testing builds.

Disable **Check for updates when Caelum opens** in Advanced settings
to stop automatic network checks; changes save automatically. The background dictation service never checks,
downloads, or opens authorization dialogs by itself.

Omarchy uses the Arch package target when its system Python minor version matches
the package. Other derivative distribution IDs are not automatically accepted.

Choose **Update & restart** when an update is available to approve the download.
**Later** leaves the application unchanged. Accepted downloads go to `$XDG_DATA_HOME/caelum/updates/pending`
(normally `~/.local/share/caelum/updates/pending`), not the installation directory.
After download and verification, Caelum requests administrator authorization through
polkit, installs the package, and restarts the desktop app automatically. Pending
settings edits are saved before restarting. Queued updates are also retried on the
next desktop app launch.

Installation stops an idle dictation service, takes its process lock, installs the
verified package with apt/dnf/pacman, then reloads the desktop and restarts dictation
if it had been running. Active recording, processing, unfinished work, or retryable
audio defers installation instead of losing speech. Finish or explicitly discard
that session and choose **Update & restart** to retry. Already queued hotkey requests are
blocked once the service has accepted the update shutdown.

Cancelled authorization or installation failure retains the pending download.
Use **Update & restart** to retry, or discard it in Advanced settings. The dictation service may need manually starting after
a failed installation. Source checkouts, pip installations, AUR source packages,
unsupported architectures, Python versions, and mismatched OS releases must use
their original installation method; the updater does not replace those installs.

Configuration, credentials, and history are not part of the package payload and
are not deleted by an update. Native package installation is not a filesystem
transaction: an interrupted package manager can need repair through that package
manager. There is no automatic rollback or silent privilege escalation.

## Verification and trust

- Only stable `major.minor.patch` versions newer than the installed version qualify.
- A detached Ed25519 signature authenticates the exact `update.json` bytes using
  the public key shipped in the installed package. A key downloaded beside an
  update is **never** trusted. TLS verification stays enabled, environment proxy
  overrides are disabled, and redirects to HTTP are rejected before sending them.
- Signed metadata binds each supported target to a package filename, byte length,
  and SHA-256 digest. Metadata is limited to 64 KiB, signatures to 64 bytes, and
  packages to 512 MiB. Compressed HTTP responses are rejected to keep these bounds.
- Metadata expires after at most 90 days. Bad signatures, unsupported targets,
  future/expired metadata, truncated downloads, wrong hashes, and downgrades fail
  closed. A wrong system clock can prevent updates. If a release has expired, use
  a new signed release or install through the native package manager yourself.
- Downloads are staged in a private directory and only made pending after full
  verification. The privileged helper is the **already installed** root-owned
  script, launched with Python isolated mode. It repeats signature, freshness,
  compatibility, version, and digest checks. It copies a regular, non-symlink
  package to a private root-owned directory before checking its hash and invoking
  a fixed package-manager command with a clean environment. User-writable package
  paths are never handed to the privileged package manager.
- Initial installation and the release signing key are trust roots. Protect the
  repository, build workflow, protected release environment, and signing key.
  These controls do not defend against a compromised maintainer signing key,
  compromised root account, or malicious code already installed as the same user.

## Maintainer bootstrap (required before publishing)

No production private key is generated or committed by this implementation.
Until a public key has been provisioned, builds keep in-app updates disabled and
tag publishing fails closed rather than producing unsigned updater metadata.

1. On a trusted maintainer machine, generate an **Ed25519** key outside the repo:

   ```sh
   umask 077
   openssl genpkey -algorithm ED25519 -out /secure/location/caelum-update-private.pem
   openssl pkey -in /secure/location/caelum-update-private.pem -pubout \
     -out python/caelum/update-public.pem
   ```

2. Review and commit **only** `python/caelum/update-public.pem`. It is deliberately
   exempted from the repo's PEM ignore rule and included in native package payloads.
   Never place a private key anywhere under `python/caelum`, which packaging copies.
3. The GitHub Actions **release** environment is the protected production signing
   environment. Keep required reviewers and restrict deployments to main only. Store the private PEM in its
   `CAELUM_UPDATE_SIGNING_KEY` environment secret using GitHub's secret UI. Do not
   paste it into chat, logs, build artifacts, or version control. Restrict who can
   alter release tags, workflow code, environment approvals, and secrets.
4. Bump all version manifests together to a new stable version. A main push builds
   a candidate artifact; `publish.yml` with channel `testing` publishes an RC.
   Test the exact candidate, then select `production` with manual acceptance completed.
   Tags are created by the publisher; do not push or move a release tag yourself.
5. CI builds Ubuntu 24.04/26.04, Debian 12, Arch, and Fedora 43 packages and smoke-installs
   them. Production requires that identical candidate to be published to testing.
   After release-environment approval, it verifies the testing assets, signs the
   native update manifest, checks that the private key matches the committed public
   key, uploads all files to a **draft**, then publishes it as latest stable.
   Development/testing jobs never receive the production signing key. PRs never publish.

`scripts/sign_release.py ASSET_DIRECTORY PRIVATE_KEY_PATH` reproduces manifest
signing locally. The CI secret is written to a temporary mode-600 file and removed
on exit. `scripts/build_package.py TARGET` records the installed version, target,
and Python minor version in the native package's `release.json`.

Existing 0.2.0 installations without this updater must install the first
updater-enabled package manually. Keep the same signing key for later releases.
Changing only the public key in a future package will strand older installations;
planned key rotation needs a separately designed old-key-authorized transition.
If a release job fails after draft creation, inspect the failure and remove that
unpublished draft before retrying. Never overwrite an already published version
with different package bytes; release a higher version instead.

## Validation and release acceptance

`pytest tests/test_updates.py tests/test_orchestrator.py` covers real Ed25519
sign/verify round trips, tampering, expiry, rollback rejection, download limits,
HTTPS downgrade blocking, offline failures, staging, cancellation, privileged
reverification, root-owned snapshots, and idle/busy daemon shutdown. No test
performs a real privileged package installation.

Before rollout, perform a two-version upgrade in clean VMs for every advertised
distribution: accept/later/download/discard, cancel polkit, resume on next launch,
defer during recording/retry, verify service restart, preserve config/history/keys,
and recover from an interrupted package manager. Real polkit agents and native
package-manager behavior require this acceptance testing; local mocked tests do
not certify them. Test the published GitHub release workflow after key provisioning.
