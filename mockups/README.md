# Caelum Black UI Mockups

This directory contains HTML/CSS mockups of the proposed pure black UI redesign.

## Files

### HTML Mockups (Static)
- `base.css` - Core design system styles
- `dashboard-idle.html` - Dashboard in idle/ready state
- `dashboard-recording.html` - Dashboard during active recording
- `history.html` - History page with transcript search
- `settings.html` - Settings page (Recording tab)
- `onboarding.html` - Setup/onboarding flow (Step 1)

### Screenshots (PNG)
All screenshots are 1400x900px at 2x DPI (high resolution).

- `new-dashboard-idle.png` - Dashboard idle state
- `new-dashboard-recording.png` - Dashboard recording state
- `new-history.png` - History page
- `new-settings.png` - Settings page
- `new-onboarding.png` - Onboarding/setup

## Design System Summary

### Colors (Only 4)
- **Black:** #000000 (all backgrounds, cards, surfaces)
- **White:** #FFFFFF (primary text, borders, lines)
- **Accent:** #00FF00 (recording active, success states)
- **Destructive:** #FF0000 (errors, delete actions)

### Typography
- **Body:** Inter, system-ui
- **Mono:** SF Mono, JetBrains Mono (for hotkeys, timers, data)

### Key Principles
- NO greys, NO gradients, NO rounded corners
- NO glassmorphism, NO glows, NO shadows
- Pure black backgrounds only
- Hierarchy through typography, spacing, thin white lines
- Monospace for data (hotkeys, word counts, timestamps)
- Single accent color (green) for state indication only

## Viewing Mockups

Open any HTML file in a web browser:
```bash
# From this directory
firefox dashboard-idle.html
# or
chromium dashboard-idle.html
```

## Generating Screenshots

The `capture-screenshots.js` script uses Playwright to render and screenshot each mockup:

```bash
npm install playwright
npx playwright install chromium
node capture-screenshots.js
```

Screenshots are saved to `/opt/cursor/artifacts/` for PR attachment.

## Current UI Screenshots

**Note:** Current UI screenshots (before redesign) were not captured because the app is not running in this environment. For comparison, refer to the existing Tauri app screenshots in `docs/` or build and run the current 0.4.1 version locally.

The current design uses:
- Multiple grey shades (oklch color space)
- 8px border radius on cards/buttons
- T3 Code mint/teal accent colors
- Subtle shadows on cards
- Variable lightness backgrounds

This proposed redesign eliminates all of those in favor of pure black/white/green only.

## Implementation Path

To implement this design in the actual app:

1. Replace `src/index.css` color tokens with pure black/white/green
2. Update Tailwind config to remove grey shades and border radius
3. Remove all shadcn component rounded corners and shadows
4. Update `src/features/*.tsx` to use new color system
5. Replace `ThemeProvider` to always use black (no theme toggle)
6. Add green accent to recording states in `dashboard.tsx`

See `DESIGN_SPEC.md` for complete implementation guide.
