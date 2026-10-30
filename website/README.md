# Caelum product page draft

A standalone, responsive static site. No build step or package installation is required.

From the repository root:

```sh
python -m http.server 4173 --bind 0.0.0.0 --directory website
```

Open `http://localhost:4173`. To review on another Tailscale device, use this machine's Tailscale IP with port 4173. The computer and server must remain running.

The page includes an illustrative dictation demo (no microphone access), an accessible product tour, distribution selection linking to GitHub Releases, and native FAQ disclosures. Product UI and statistics are explicitly labeled sample illustrations. Download links lead to the releases page, not unverified individual assets.

The design follows the component research in `docs/product-page-design.md`, implemented here in plain HTML/CSS/JavaScript. It does not bundle third-party 21st component source. DM Sans loads from Google Fonts with local system fallbacks.

Verified with headless Chromium at 320, 375, 390, 600, 768, 1280, and 1440 CSS pixels. Interaction checks cover navigation dismissal, tab selection and arrow keys, distribution selection, FAQ expansion, demo playback, and reduced motion.
