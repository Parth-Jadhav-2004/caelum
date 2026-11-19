# Caelum product page

Standalone HTML, CSS, and JavaScript, deployed at
https://parth-jadhav-2004.github.io/caelum/ by `.github/workflows/website.yml`.
No application build or package installation is needed to serve it.

From the repository root:

```sh
python -m http.server 4173 --bind 127.0.0.1 --directory website
```

Open `http://localhost:4173`. Serve over HTTP: ES modules and the release manifest
are not designed to load from a `file://` URL.

## Releases and downloads

`release.json` is the only source of the version, supported distributions, and
package filenames. The checked-in manifest describes **0.4.2**: Ubuntu 24.04,
Ubuntu 26.04, Debian 12, Arch Linux, and Fedora 43, all x86-64. Debian 13 and ARM
are not offered. The page derives download URLs, install commands, labels, and
the checksum link from this manifest. JavaScript or manifest failure leaves a
safe link to the stable release page and hides package installation commands.

Refresh from GitHub's latest stable release:

```sh
python scripts/update-website-release.py
node --test website/release-check.mjs
uv run pytest tests/test_website_release.py -q
```

The generator reads published assets, requires SHA256SUMS and signed-update
metadata, checks that each package is listed in SHA256SUMS, and verifies each
package URL with HTTP HEAD. Missing targets and packages returning 404 are omitted;
other verification failures abort publication. It does not download or
cryptographically authenticate the packages itself; the user verifies the
checksum, and the app verifies signed update metadata during an update.

Pages runs this generator before deployment on website changes, a published
release, or a successful **Promote to testing or production** workflow (needed because
releases created using GITHUB_TOKEN do not trigger release workflows). It checks
out `main` for the site and updates the deployment artifact without committing
back to the repository. The workflow can also be run manually. A generation
failure prevents publication rather than inventing download links.

## Product and design

The design follows [`DESIGN.md`](../DESIGN.md): near-black canvas, a 240px desktop
sidebar, neutral recording capsule, soft rows, and no gradients, glow, or surface
shadows. The hero shows the installed Ubuntu 24.04 package from [candidate run 44309773651](https://github.com/Parth-Jadhav-2004/caelum/actions/runs/44309773651), artifact `smoke-ubuntu-24.04/native-smoke.png`, cropped to the 1100×780 window. This is real setup in WebKit/Xvfb, not a GNOME session or a recording. The social card uses that screenshot. The portable walkthrough uses native keyboard-operable disclosures with sample text; the product tour uses illustrative data. Neither records audio or touches the clipboard. Inter Variable is self-hosted under the SIL Open Font License in `fonts/`.

## Publication and qualification

The selector and no-JavaScript link lead to published stable packages. Keep testing releases separately labeled. Product copy distinguishes 0.4.2’s online-only transcription from the 0.5.0 candidate’s local and online modes. Never infer stable availability from a branch or draft. A website-only PR can land on main during the application hold. Include `website/`, the manifest generator, its Python tests and the Pages workflow. Verify the deployment and every download after promotion. Site checks are not desktop qualification.
