# Caelum product page

A standalone, responsive static site. No build step or package installation is required.

Published at https://parth-jadhav-2004.github.io/caelum/ through GitHub Pages.
Changes to `website/` on `main` deploy automatically using `.github/workflows/website.yml`.

From the repository root:

```sh
python -m http.server 4173 --bind 0.0.0.0 --directory website
```

Open `http://localhost:4173`. To review on another Tailscale device, use this machine's Tailscale IP with port 4173. The computer and server must remain running.

The page includes an automatically looping illustrative dictation demo with pause/resume (no microphone access), an accessible product tour, distribution selection linking to the published v0.3.0 packages, and native FAQ disclosures. Product UI and statistics are explicitly labeled sample illustrations. Each distribution downloads its matching v0.3.0 asset; checksums stay on the release page.

The demo pauses when offscreen or in a background tab. Reduced-motion preferences show a completed transcript by default; playback can be started explicitly.

The design follows the component research in `docs/product-page-design.md`, implemented here in plain HTML/CSS/JavaScript. It does not bundle third-party 21st component source. DM Sans loads from Google Fonts with local system fallbacks.

Verified with headless Chromium at 320, 375, 390, 600, 768, 1280, and 1440 CSS pixels. Interaction checks cover navigation dismissal, tab selection and arrow keys, distribution selection, FAQ expansion, demo playback, and reduced motion.

Sections reveal once as they enter the viewport, with a small stagger between related elements. Tour options use an unboxed text treatment and animate content changes. Native smooth anchor scrolling preserves browser navigation; all entrance motion is disabled for reduced-motion preferences.
