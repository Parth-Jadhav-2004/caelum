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
release, or a successful **Promote Linux candidate** workflow (needed because
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

Validated in headless Chromium at 320, 375, 390, 600, 768, 1280, and 1440 CSS pixels:
no horizontal overflow across all five tour panels, no WCAG A/AA violations from
axe, no JavaScript errors, and no third-party resource requests. Interaction checks
cover menu dismissal/focus, tour arrows/Home/End, all five package commands,
compatibility disclosure, reduced motion, demo start/cancel, manifest failure,
and JavaScript-disabled download fallback. The 21st review reports no errors;
its color-token notices refer to the intentional DESIGN.md palette.

## Publication hold and deferred work

Parth has authorized committing and pushing these changes on feature branches.
Opening a PR, publishing a release, changing repository settings, or deploying
still requires authorization. The portfolio card is updated separately in the
[portfolio repository](https://github.com/Parth-Jadhav-2004/portfolio), in
`src/data/portfolioData.js` (Tauri 2, React, Tailwind, shortcut, and the GitHub
Pages product link); it needs its own review and deployment.

The repository homepage remains a manual follow-up after authorization:

```sh
gh repo edit Parth-Jadhav-2004/caelum --homepage "https://parth-jadhav-2004.github.io/caelum/"
```

**Do not ship local-model claims yet.** At implementation time, published remote
`main` was `8890b43` and the stable release was 0.4.2. The checkout contains
unmerged local-transcription work; neither that nor a local `main` ref proves
publication. Keep the website's Online/Groq copy until the feature is merged
into published `main` and available in the release offered by the site.

Then update hero, privacy, download copy, and the offline/API-key FAQs together:
Online/Groq remains the default; “On this computer” downloads an optional model;
Parakeet v3, Parakeet 110M, Cohere Transcribe (8 GB+ RAM), and Whisper turbo are
the planned choices. Hindi stays Online, local audio is not uploaded, and Online
fallback is off unless enabled. Avoid a blanket “fully offline” claim. Keep the
update-check disclosure, no-audio-in-history policy, and unencrypted-history note.
Re-check the model catalog and defaults before publishing that follow-up.
