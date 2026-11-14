# Caelum desktop design

Tauri 2 / React / TypeScript / Tailwind 4 / shadcn/ui. Dark first, optional light
and system appearance. T3 Code neutral palette by default, with T3 Chat, Grove, Ocean, Ember, Iris,
and the original Caelum mint available independently of light/dark/system appearance.
Quiet semantic borders and 8px base radius. System sans-serif text;
monospace only for shortcut tokens and recording duration.

Use installed shadcn primitives from src/components/ui. Project tokens are defined
in src/index.css. Sidebar navigation collapses to icons; content stays bounded at
wide sizes and stacks controls on narrow desktop windows. Native window decorations
retain compositor-standard controls. Motion is short and respects reduced motion.
Waveforms display real capture values and never animate fabricated speech energy.

21st search was run for shadcn transcription/dashboard inspiration. Its decorative
hero and glass results did not fit this utility; official shadcn registry primitives
were installed instead. No hosted generation or 21st assets were needed.

T3 palettes are imported from pinned upstream literals, with MIT attribution in
THIRD_PARTY_NOTICES.md. Use the existing shadcn Select for palette choice; avoid
decorative theme cards. Page headings describe tasks, without marketing slogans.

Settings → General starts with a dedicated Theme section containing the palette
and appearance selectors. Keep these preferences visible before service settings.
