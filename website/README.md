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
package filenames. Pages regenerates it from Latest. Each published package carries its SHA256SUMS
digest. The Windows installer and AppImage links appear when their release assets
are available. The page highlights the visitor’s OS when detected and keeps the
package selector available for other platforms. If the manifest cannot load,
visitors can still open the stable release page.

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

The demo is an HTML notebook with a looping shortcut, listening, and insertion sequence. The clock pauses offscreen or in a background tab and resumes at the same point. Visitors can pause it; reduced-motion visitors start with the completed note.

“At your desk” uses native radio controls and a paper crossfade to switch examples. The FAQ starts with grouped native disclosures and enhances them with keyboard-operable buttons and panels that expand and contract together. Download buttons and the package label come from the shared desktop shadcn components via `website/tools/render-controls.tsx`.

## Publication and qualification

The selector and no-JavaScript link lead to the published stable release. Pages regenerates its inventory from Latest after publication. Check the deployed version, download buttons and checksums before updating the checked-in manifest.
