# Caelum desktop design

Tauri 2 / React / TypeScript / Tailwind 4 / shadcn/ui. Dark first, optional light
and system appearance. Neutral charcoal surfaces, pale mint recording accent,
muted secondary text, quiet borders, 12px base radius. System sans-serif text;
monospace only for shortcut tokens and recording duration.

Use installed shadcn primitives from src/components/ui. Project tokens are defined
in src/index.css. Sidebar navigation collapses to icons; content stays bounded at
wide sizes and stacks controls on narrow desktop windows. Native window decorations
retain compositor-standard controls. Motion is short and respects reduced motion.
Waveforms display real capture values and never animate fabricated speech energy.

21st search was run for shadcn transcription/dashboard inspiration. Its decorative
hero and glass results did not fit this utility; official shadcn registry primitives
were installed instead. No hosted generation or 21st assets were needed.
