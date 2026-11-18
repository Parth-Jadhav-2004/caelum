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
shadows. The previews recreate the app and are explicitly labeled sample content;
they are not screenshots or live microphone capture. Inter Variable is self-hosted
in `fonts/`, with its SIL Open Font License in `fonts/OFL.txt` and system fallbacks.
No third-party resources load when visiting the page. The 1200×630 `og.png` uses
the same recreated UI with a sample-content caption.

The demo shows Recording → Processing → Saved with final text only. It pauses
when offscreen or in a background tab. Reduced motion shows a completed transcript
without autoplay; playback can still be started explicitly. Escape ends the demo.
The product tour uses keyboard-accessible tabs; navigation, skip links, visible
focus, and native FAQ disclosures are preserved.

The earlier website-refresh branch was validated in headless Chromium at 320, 375, 390, 600, 768, 1280, and 1440 CSS pixels:
no horizontal overflow across all five tour panels, no WCAG A/AA violations from
axe, no JavaScript errors, and no third-party resource requests. Interaction checks
cover menu dismissal/focus, tour arrows/Home/End, all five package commands,
compatibility disclosure, reduced motion, demo start/cancel, manifest failure,
and JavaScript-disabled download fallback. The 21st review reports no errors;
its color-token notices refer to the intentional DESIGN.md palette.

## Publication and qualification

The selector and no-JavaScript link lead to published stable packages. Keep testing releases separately labeled. Product copy distinguishes 0.4.2’s online-only transcription from the 0.5.0 candidate’s local and online modes. Never infer stable availability from a branch or draft. Pages deploys from main under [the protected promotion process](../docs/releasing.md). Verify the deployment and every download after promotion. Historical UI checks above are not desktop qualification of a new candidate.
