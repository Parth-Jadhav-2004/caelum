# Caelum product page: component direction

Research date: October 30, 2026. This is a design recommendation, not an implemented website.

## Recommended direction

A quiet, native-feeling Linux product page with a working explanation of dictation at its center. Use Caelum's black and charcoal application surfaces, a white primary download button, and a muted sky-blue recording indicator. The memorable element should be the small recording pill transforming speech into text inside a Linux desktop scene.

Suggested headline: **Speak. Keep your flow.**

Supporting copy: **Voice dictation for your Linux desktop. Hold a shortcut to speak on Hyprland, or record and copy on other desktops.**

Primary action: **Download for Linux**. Secondary action: **Watch the demo**. Nearby supporting text: **Cross-distro preview · Bring your own provider keys**.

The page should make the benefit legible before discussing providers, models, or configuration.

## Components to combine

### Navigation: Navbar 1 by preetsuthar17

[21st component](https://21st.dev/@preetsuthar17/components/navbar-1) · demo ID 2046 · source inspected.

Use its compact responsive navigation structure, with Caelum on the left and How it works, Linux support, GitHub, and Download. Rework its white floating pill into a restrained header matching the page. Remove the gradient logo, shadows, and per-link entrance/hover scaling. Source uses React, `motion/react`, and `lucide-react`; imported packages need checking because the registry dependency metadata was empty. Add an accessible name and expanded state to the mobile toggle, plus focus management and Escape dismissal.

### Hero: Hero With Video by jahed

[21st component](https://21st.dev/@jahed/components/hero-with-video) · demo ID 2532 · public preview inspected; source not retrieved.

Use the heading, actions, and broad media frame composition. Replace the stock Earth video with a short real Linux capture: hold shortcut, recording pill appears, release, text reaches an application. Remove the email capture, login, and sales navigation. Use a static poster and explicit play control; captions and a text explanation should communicate the same workflow. Keep the actual recording pill legible in the capture.

### Signature demo: Waveform by ElevenLabs

[21st component](https://21st.dev/@ElevenLabs/components/waveform) · demo ID 8607 · source and public preview inspected. Search currently returns the older `ElevenLabs-crawled` author URL, which redirects to ElevenLabs.

Use only its small waveform primitive within a pill resembling Caelum's existing HUD. The source includes static, scrolling, microphone, and scrubber variants. For the marketing page, prefer a deterministic simulated sequence with a visible Demo label. No microphone permission is needed. Show Ready, Listening, Processing, and Done with words as well as visuals. Replay should be deliberate, and reduced motion should show the completed result. The source includes continuous animation and microphone access in some variants, so do not import the whole experience without review.

### Product tour: Feature 108 by shadcnblockscom

[21st component](https://21st.dev/@shadcnblockscom/components/shadcnblocks-com-feature108) · demo ID 607 · public interactive preview inspected; source retrieval was quota-blocked.

Use its three-tab structure for History, Statistics, and Settings. Replace generic copy and imagery with actual app captures and concise descriptions. History: find and copy previous dictations. Statistics: review retained word totals and recording time. Settings: choose shortcut, microphone, and providers. Keep tabs user-controlled, preserve keyboard navigation, and stack cleanly on small screens. This serves Caelum better than a large grid of equally weighted feature cards.

### FAQ: Accordion by wensity

[21st component](https://21st.dev/@wensity/components/accordion) · demo ID 31351 · catalog metadata/thumbnail reviewed; source and interactive behavior not inspected.

Its Base UI foundation is a promising accessible starting point. Use a plain divided list and remove unnecessary spring effects. Questions: Which Linux desktops work? Does audio stay on my machine? Do I need API keys? Is history saved? Does it paste automatically? Verify keyboard behavior and reduced motion during implementation.

### Optional alternative: Bento Grid by designali-in

[21st component](https://21st.dev/@designali-in/components/bento-grid) · demo ID 4517 · catalog metadata/thumbnail reviewed only.

Use instead of the tabbed tour if the available screenshots work better as a static overview. Limit to three unequal panels with actual product content. Avoid combining a full bento section and a full tabbed tour: they would repeat the same story.

## Page order

1. Compact navigation.
2. Hero, Linux download action, and desktop dictation demonstration.
3. A short Hold → Speak → Release explanation, explicitly marked as the native Hyprland workflow. Explain Record → Finish → Copy for other desktops alongside it.
4. Tabbed product tour: History / Statistics / Settings.
5. Plain-language privacy and provider section: audio goes to the configured transcription provider; optional cleanup sends text to the cleanup provider; final history is stored locally; audio is not saved to history.
6. Linux downloads: choose distro and exact version, then link to a verified release asset and installation guide. Separate package availability from desktop behavior and hardware qualification.
7. FAQ and a final download action; footer with source, releases, installation guide, and privacy details.

Avoid adding pricing tiers, testimonials, customer logos, benchmark numbers, or integrations without real supporting material.

## Proposed visual system

- Base: black `#000000`; app surfaces: charcoal `#171717`; dividers: `#303030`; primary text: `#F5F5F5`; secondary text: `#B3B3B3`; recording accent: sky `#87BFEA`.
- Typography: Adwaita Sans where available, with an explicit bundled webfont decision before implementation and a system sans fallback. Use monospace only for shortcuts and commands.
- Layout: approximately 1120px maximum width, left-aligned supporting sections, generous space around one central media composition. Avoid wrapping every section in a card.
- Radius: smaller on controls and media frames; fully rounded only on the recording pill.
- Motion: the demo carries the motion budget. Keep navigation, tabs, and FAQ quiet and honor reduced motion.
- Mobile: stack hero content and media, keep download accessible, allow tabs to wrap or scroll without clipping, and show a readable media poster.

This dark palette follows the existing native app rather than inventing a different identity. Avoid atmospheric gradients, particle backgrounds, logo marquees, glowing borders, and decorative audio effects.

## Web references

[Wispr Flow](https://wisprflow.ai/) was browsed for its immediate benefit statement, primary download action, and speech-to-writing demonstration. Borrow the clarity; give Caelum its own typography, desktop scene, and copy.

[Superwhisper](https://superwhisper.com/) was browsed for its concise product promise and explicit platform downloads. Caelum should similarly foreground its actual Linux workflows and installation choices.

21st's public pages for Hero With Video, Feature 108, and Waveform were inspected visually. The six catalog searches returned 30 component entries; the shortlist above is curated from those results.

## Implementation and research status

The repository currently contains the Python/GTK application, not a web frontend. These components target a future React/Tailwind site; they cannot be dropped into the GTK application. No frontend framework or component packages were installed.

A raw streamable HTTP MCP connection to `https://21st.dev/api/mcp` successfully initialized as server `21st` version `0.1.1`, and `tools/list` verified `search`, `get_component`, `get_theme`, and other tools. Six searches succeeded. Navbar and Waveform source retrievals succeeded; Feature 108 retrieval returned the free-tier limit. The free allowance reported two retrievals per day, zero remaining, resetting at 2026-10-31 00:00 UTC. No paid upgrade was initiated. This was a session connection, not a persistent MCP client installation.

Before building: check selected component licenses and exact dependencies, use real application media, and verify live release assets. The local docs describe Ubuntu, Debian, Arch, and Fedora packages, but the release contents were not checked during this design research. Do not advertise offline processing, fully local AI, encrypted history, identical automatic paste on every Linux desktop, or speed/accuracy claims without evidence.

Product facts were checked against README.md, docs/linux.md, and docs/privacy.md in the working tree. The docs distinguish native Hyprland integration from the portable preview and state that completed transcripts are saved automatically.
