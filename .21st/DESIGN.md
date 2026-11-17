# Caelum desktop design

Use DESIGN.md as the current product design reference. The app uses Tauri 2,
React, TypeScript, Tailwind 4, and the installed shadcn primitives.

Tokens live in src/index.css. Caelum has light, dark, and system appearance,
with independent Mint, Iris, and Ochre accents. Earlier palette names migrate
to Caelum. Use Inter Variable, neutral controls, and 10px surface radii.

Use the published waveform logo in website/mark.svg. Native and web icons share
its path. The sidebar is 240px expanded and a 48px icon rail when collapsed;
its saved state and appearance apply at startup. Keep useful help, errors,
and check results visible. Only icon action names belong in tooltips.

Home shows the shortcut, recording feedback, daily totals, and three recent
entries. History is a searchable archive grouped by day, with a separate detail
panel. Setup keeps its footer stable while long step content scrolls.

Screen and native pill fades last 160ms; sidebar resizing lasts 200ms. Respect
system and explicit reduced motion. Focus moves to each destination screen,
and dialogs return focus. Waveforms only use real microphone levels.

21st search was checked for sidebar inspiration; decorative results were
rejected in favor of existing project primitives. No hosted generation needed.
