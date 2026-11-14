# Caelum Black UI Design Specification

**Version:** 1.0 (Proposal)  
**Date:** November 14, 2026  
**Designer:** Design proposal for pure black redesign

---

## Design Philosophy

**Principle:** Deliberate, utilitarian, keyboard-first desktop tool. Not a web app, not a consumer product. A professional dictation instrument.

**Anti-patterns to avoid:**
- ❌ Glassmorphism, frosted glass, blur effects
- ❌ Glows, shadows, ambient lighting
- ❌ Emoji icons (🎙️, ✨, 🚀)
- ❌ Generic hero cards with abstract illustrations
- ❌ Rounded-everything card grids
- ❌ Purple/blue gradients, gradient text
- ❌ Sparkles, particle effects, animated blobs
- ❌ Marketing slogans ("Your voice, amplified!")
- ❌ Grey backgrounds, grey borders, grey text

**Design goals:**
- ✅ Pure black (#000000) as the ONLY background/surface
- ✅ White text (#FFFFFF) for primary content
- ✅ Single accent color (vibrant green #00FF00) used ONLY for state indication
- ✅ Hierarchy through typography, spacing, and thin white/accent lines
- ✅ Monospace for data (hotkeys, timers, word counts)
- ✅ No shades of grey — only #000000, #FFFFFF, #00FF00, and destructive red #FF0000

---

## Color Palette

### Core Colors (Only 4 total)

```css
/* Backgrounds & Surfaces */
--black: #000000;           /* Pure black - ALL backgrounds */

/* Typography */
--white: #FFFFFF;           /* Primary text, headings, body copy */

/* State & Interaction */
--accent: #00FF00;          /* Recording active, success, primary actions */
--destructive: #FF0000;     /* Errors, destructive actions (delete, quit) */
```

### NO intermediate grays. NO opacity variants (except for disabled states at 40% opacity).

### State Color Usage

| State | Color | Usage |
|-------|-------|-------|
| **Idle/Default** | White on Black | Navigation, inactive controls |
| **Active/Recording** | Accent (#00FF00) | Recording pill, active hotkey, "Finish" button |
| **Success** | Accent (#00FF00) | Checkmarks, confirmation states |
| **Error/Warning** | Destructive (#FF0000) | Error messages, delete buttons, quit warnings |
| **Disabled** | White at 40% opacity | Disabled buttons, inactive fields |

---

## Typography

### Font Stack

```css
/* Body & UI */
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;

/* Data & Monospace */
font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
```

### Type Scale (8px base)

```css
/* Headings */
--text-5xl: 48px / 56px;    /* Page titles (rare, only onboarding) */
--text-4xl: 36px / 40px;    /* Feature headers */
--text-3xl: 30px / 36px;    /* Section headers */
--text-2xl: 24px / 32px;    /* Subheadings */
--text-xl:  20px / 28px;    /* Card headers */
--text-lg:  18px / 28px;    /* Navigation items */

/* Body */
--text-base: 16px / 24px;   /* Body copy, form labels */
--text-sm:   14px / 20px;   /* Helper text, metadata */
--text-xs:   12px / 16px;   /* Captions, timestamps */

/* Monospace */
--mono-2xl: 24px / 32px;    /* Timer during recording */
--mono-base: 14px / 20px;   /* Hotkey display, word counts */
--mono-xs:   12px / 16px;   /* Timestamps in mono format */
```

### Font Weights

- **Regular (400):** Body copy, form fields
- **Medium (500):** Navigation, card headers, button text
- **Bold (700):** Page titles, critical actions (NEVER use in body text)

### Typographic Rules

1. **NO all-caps except for hotkeys** (e.g., "SUPER + SPACE")
2. **NO centered headings** unless in empty states
3. **Line height = 1.5 for body copy**, tighter for headings
4. **Letter spacing = 0 for body**, -0.02em for large headings

---

## Spacing & Layout

### Spacing Scale (8px base unit)

```css
--space-1: 8px;
--space-2: 16px;
--space-3: 24px;
--space-4: 32px;
--space-5: 40px;
--space-6: 48px;
--space-8: 64px;
--space-10: 80px;
```

### Layout Rules

- **Page margins:** 80px top/bottom on desktop, 48px on sides
- **Card padding:** 32px internal padding for all cards
- **Section spacing:** 48px between major sections
- **Form field spacing:** 24px between label and next field
- **Line spacing:** 1px white lines for dividers

### Grid System

- **Max content width:** 1200px centered
- **Sidebar width:** 240px (collapsed: 64px icon-only)
- **Two-column forms:** 50/50 split with 32px gap
- **Card grids:** 16px gap, no more than 3 columns

---

## Components

### Buttons

```css
/* Primary Button (Accent) */
background: #00FF00;
color: #000000;
border: none;
padding: 12px 24px;
font-size: 16px;
font-weight: 500;
border-radius: 0;  /* NO ROUNDING */
cursor: pointer;

/* Hover: Invert */
background: #000000;
color: #00FF00;
border: 1px solid #00FF00;

/* Disabled */
background: #00FF00;
color: #000000;
opacity: 0.4;
```

```css
/* Secondary Button (Outline) */
background: transparent;
color: #FFFFFF;
border: 1px solid #FFFFFF;
padding: 12px 24px;
border-radius: 0;

/* Hover: Fill */
background: #FFFFFF;
color: #000000;
```

```css
/* Destructive Button */
background: #FF0000;
color: #FFFFFF;
border: none;
padding: 12px 24px;
border-radius: 0;

/* Hover */
background: #000000;
color: #FF0000;
border: 1px solid #FF0000;
```

### Forms & Inputs

```css
/* Text Input */
background: #000000;
color: #FFFFFF;
border: 1px solid #FFFFFF;
padding: 12px 16px;
font-size: 16px;
border-radius: 0;

/* Focus */
border: 2px solid #00FF00;
outline: none;

/* Disabled */
border-color: rgba(255, 255, 255, 0.4);
color: rgba(255, 255, 255, 0.4);
```

```css
/* Checkbox/Switch */
/* Unchecked: 1px white square, hollow */
/* Checked: Fill with #00FF00, white checkmark */
```

### Cards & Surfaces

```css
/* Card */
background: #000000;  /* Same as page background! */
border: 1px solid #FFFFFF;
padding: 32px;
border-radius: 0;

/* NO drop shadows */
/* NO hover elevation */
/* Cards defined by thin white border ONLY */
```

### Dividers

```css
/* Horizontal Rule */
width: 100%;
height: 1px;
background: #FFFFFF;
margin: 48px 0;
```

### Navigation (Sidebar)

```css
/* Sidebar Background */
background: #000000;  /* Same as page! */
border-right: 1px solid #FFFFFF;
width: 240px;

/* Nav Item (Inactive) */
color: #FFFFFF;
padding: 12px 16px;
font-size: 16px;
font-weight: 500;
background: transparent;

/* Nav Item (Active) */
color: #00FF00;
border-left: 2px solid #00FF00;
background: transparent;

/* NO background color change on hover */
/* ONLY underline on hover: */
text-decoration: underline;
```

---

## Screen Layouts

### 1. Dashboard / Home

```
┌─────────────────────────────────────────────────────┐
│ [Sidebar]           DICTATION                       │
│ ▸ Home             ─────────────────────────────    │
│   Statistics       RECORDING STATUS                 │
│   History          ┌──────────────────────────────┐ │
│   Settings         │ ● LISTENING                  │ │
│                    │ [Waveform: 17 bars]          │ │
│                    │ SUPER + SPACE               │ │
│ ────────────       │                              │ │
│ ● Service Ready    │ [■ Finish]  [✕ Cancel]      │ │
│ SUPER + SPACE      └──────────────────────────────┘ │
│                                                      │
│                    STATISTICS                       │
│                    ─────────────────────────────    │
│                    [Words dictated: 12,847]         │
│                    [Recording minutes: 142.5]       │
│                                                      │
│                    RECENT DICTATIONS                │
│                    ─────────────────────────────    │
│                    [Transcript card 1]              │
│                    [Transcript card 2]              │
│                    [Transcript card 3]              │
└─────────────────────────────────────────────────────┘
```

**Key design elements:**
- Page title "DICTATION" in 36px bold, left-aligned
- Recording status card: white border, 32px padding
- Waveform: 17 vertical bars, 8px apart, animated height (green when active)
- Timer/Hotkey: 24px monospace, centered
- Action buttons: Primary (green) + outline destructive
- Stats: Two-column grid, 16px gap
- Recent cards: Stacked, 16px spacing

### 2. History

```
┌─────────────────────────────────────────────────────┐
│ [Sidebar]           HISTORY                         │
│   Home             ─────────────────────────────    │
│   Statistics       Completed dictations, never      │
│ ▸ History          microphone audio.                │
│   Settings                                          │
│                    [Search: ____________] [Export]  │
│                    ─────────────────────────────    │
│                    ┌──────────────────────────────┐ │
│                    │ 2026-11-14 13:47 · 127 words │ │
│                    │ · 12.3s                  [⎘] │ │
│                    │                              │ │
│                    │ "A little less typing, a     │ │
│                    │  little more room to think." │ │
│                    └──────────────────────────────┘ │
│                    [More transcript cards...]       │
│                                                      │
│                    [Delete All] (bottom right)      │
└─────────────────────────────────────────────────────┘
```

**Key design elements:**
- Search input: Full-width, white border, left icon
- Export button: Secondary (outline white)
- Transcript cards: White border, 32px padding, metadata in 12px mono
- Copy button: Minimal icon button (no background)
- Delete All: Bottom-right, red text, separated by space

### 3. Settings

```
┌─────────────────────────────────────────────────────┐
│ [Sidebar]           SETTINGS                        │
│   Home             ─────────────────────────────    │
│   Statistics       Configure recording and          │
│   History          transcription.                   │
│ ▸ Settings                                          │
│                    [ APPEARANCE ] [ RECORDING ]     │
│                    [ PROVIDERS ]                    │
│                    ─────────────────────────────    │
│                    THEME                            │
│                    ─────────────────────────────    │
│                    Color theme                      │
│                    [Black ▾] (dropdown)             │
│                                                      │
│                    ─────────────────────────────    │
│                    RECORDING                        │
│                    ─────────────────────────────    │
│                    Recording shortcut               │
│                    [SUPER + SPACE]                  │
│                                                      │
│                    Recording mode                   │
│                    [Hold to talk ▾]                 │
└─────────────────────────────────────────────────────┘
```

**Key design elements:**
- Tabs: Inline, white text, active = underline (NO background color)
- Section headers: 18px uppercase, thin white underline below
- Two-column layout: Label left, control right
- Dropdowns: White border, chevron icon
- Dividers: 1px white lines between sections

### 4. Onboarding (Setup)

```
┌─────────────────────────────────────────────────────┐
│                     STEP 1 OF 4                     │
│                     ───────────                     │
│                 SET UP YOUR PROVIDER                │
│                                                      │
│  [Progress: ████░░░░]                               │
│   Provider  Microphone  Shortcut  Practice          │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │ Credential to edit                             │ │
│  │ [GROQ_API_KEY ▾]                               │ │
│  │                                                │ │
│  │ Provider API key                               │ │
│  │ [________________________] [👁]                │ │
│  │                                                │ │
│  │ ☑ I allow audio to be sent to the provider.   │ │
│  │                                                │ │
│  │ [← Back]                    [Continue →]       │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**Key design elements:**
- Centered layout, max-width 600px
- Progress: 4 segments, active = white fill, inactive = 40% opacity
- Step labels: 12px uppercase, below progress bar
- Card: White border, centered on page
- Checkbox: White square, green checkmark when checked
- Navigation buttons: Secondary back, Primary continue

---

## Animation & Motion

### Principles

1. **Reduced motion by default** (respect user config)
2. **No decorative animation** (no wobbles, bounces, springs)
3. **Only functional transitions** (page nav, state changes)

### Allowed Animations

```css
/* Page transition */
opacity: 0 → 1
transform: translateY(4px) → translateY(0)
duration: 150ms
easing: ease-out

/* Button hover */
background-color: 100ms ease-out
border-color: 100ms ease-out

/* Waveform bars (recording) */
height: 75ms linear

/* Focus ring */
border-width: 0ms (instant)
```

### Forbidden Animations

- ❌ Fade-in on scroll
- ❌ Parallax effects
- ❌ Confetti, particles, emojis
- ❌ Gradient sweeps
- ❌ Skeleton loaders with shimmer (use static black/white blocks)

---

## Accessibility

### Keyboard Navigation

- **Tab order:** Logical left-to-right, top-to-bottom
- **Focus indicators:** 2px white outline on interactive elements
- **Skip links:** "Skip to content" at top of page
- **Arrow keys:** Calendar grid navigation (Up/Down/Left/Right)

### Screen Readers

- **All images:** `alt` text or `role="presentation"`
- **Interactive icons:** `aria-label` on icon-only buttons
- **Status updates:** `aria-live="polite"` for recording state changes
- **Waveform:** `role="img"` with dynamic `aria-label` for level

### Contrast

- **White on Black:** 21:1 (AAA)
- **Accent on Black:** #00FF00 on #000000 = 15.3:1 (AAA)
- **Red on Black:** #FF0000 on #000000 = 5.25:1 (AA)

---

## Implementation Notes

### CSS Variables (Replace current theme system)

```css
:root {
  --color-black: #000000;
  --color-white: #FFFFFF;
  --color-accent: #00FF00;
  --color-destructive: #FF0000;
  
  --font-sans: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  
  --space-1: 8px;
  --space-2: 16px;
  --space-3: 24px;
  --space-4: 32px;
  --space-6: 48px;
  --space-8: 64px;
  --space-10: 80px;
  
  --text-xs: 12px;
  --text-sm: 14px;
  --text-base: 16px;
  --text-lg: 18px;
  --text-xl: 20px;
  --text-2xl: 24px;
  --text-3xl: 30px;
  --text-4xl: 36px;
  
  --border-width: 1px;
  --radius: 0px;  /* NO ROUNDING */
}
```

### Tailwind Config Changes

```js
// tailwind.config.js
module.exports = {
  theme: {
    colors: {
      black: '#000000',
      white: '#FFFFFF',
      accent: '#00FF00',
      destructive: '#FF0000',
      transparent: 'transparent',
    },
    fontFamily: {
      sans: ['Inter', 'system-ui', 'sans-serif'],
      mono: ['JetBrains Mono', 'monospace'],
    },
    borderRadius: {
      DEFAULT: '0',
      none: '0',
    },
    boxShadow: {
      none: 'none',
    },
  },
};
```

### Component Library Changes

**Replace ALL shadcn component styles:**

- Button: Remove rounded corners, shadows, gradients
- Card: Remove shadow, set border-radius: 0
- Input: Remove rounded corners, set white border
- Select: Remove rounded corners, use custom chevron icon
- Switch: Square toggle, no pill shape

---

## Dark/Light Mode?

**NO.** This design is **black only**. No light mode, no system theme toggle. The entire app is pure black (#000000) background, always.

**Rationale:** A light mode would require greys for contrast, violating the core design constraint. This is a deliberate choice for a utilitarian, terminal-like aesthetic.

---

## Before/After Comparison

### Current Design (0.4.1)

- Uses oklch() color space with varying lightness (0.145 → 0.98)
- Multiple grey shades for muted text, borders, secondary surfaces
- 8px border radius on cards, buttons, inputs
- Sidebar has distinct background color
- T3 Code theme with teal/mint accent
- Drop shadows on cards (even if subtle)

### Proposed Black Design

- Pure #000000 for ALL backgrounds (page, cards, sidebar, inputs)
- Only #FFFFFF, #00FF00, #FF0000 for content
- 0px border radius (sharp corners everywhere)
- Sidebar indistinguishable from page except for thin white border
- Single accent green for state only
- No shadows, no depth simulation

**Visual Impact:** Stark, high-contrast, brutalist aesthetic. Think terminal UI, not web app.

---

## Mockup Checklist

### Screens to Design

1. **Dashboard (Idle)** - Service ready, no recording
2. **Dashboard (Recording)** - Active waveform, timer, green accent
3. **Dashboard (Processing)** - "Processing…" state
4. **Dashboard (Error)** - Red error message
5. **Statistics** - Bar chart, word counts, calendar
6. **History** - Search, transcript cards, empty state
7. **Settings (Appearance)** - Theme selector
8. **Settings (Recording)** - Hotkey config, mic dropdown
9. **Settings (Providers)** - URL/model fields, advanced
10. **Onboarding (Step 1)** - Provider key setup
11. **Onboarding (Step 2)** - Microphone test with waveform
12. **Onboarding (Step 3)** - Shortcut capture
13. **Onboarding (Step 4)** - Practice recording

### States to Capture

- ✅ Idle (service ready)
- ✅ Recording (green accent)
- ✅ Processing (no green)
- ✅ Error (red text)
- ✅ Success (green checkmark)
- ✅ Empty state (no history)
- ✅ Form validation (red border on invalid input)
- ✅ Disabled controls (40% opacity)

---

## Design Rationale

**Why pure black?**

- Reduces eye strain in dark environments (no grey "glow")
- Maximizes OLED battery life (true black pixels = off)
- Creates deliberate, high-impact visual hierarchy
- Avoids "designed by AI" homogeneity (every app has greys)

**Why no gradients?**

- Gradients are trendy, not timeless
- Difficult to maintain contrast ratios
- Add unnecessary visual noise
- Slow rendering performance

**Why square corners?**

- Rounded corners add visual softness that conflicts with utilitarian goal
- Square = precise, deliberate, professional
- Easier to align content in dense layouts

**Why single accent color?**

- Multiple accents create confusion (is purple or blue primary?)
- Single green = unambiguous state indication
- Green = "go/active/recording" universal meaning

**Why monospace for data?**

- Tabular alignment for numbers (word counts, timers)
- Reinforces "tool" aesthetic over "app"
- Improves scannability of hotkey sequences

---

## Success Metrics

**This design succeeds if:**

1. Users describe it as "terminal-like," "minimalist," or "brutalist" (positive)
2. Zero resemblance to consumer AI apps (ChatGPT, Notion AI, etc.)
3. Faster time-to-action (less visual clutter → faster task completion)
4. Higher perceived professionalism ("looks like a pro tool, not a toy")
5. Distinctive enough to be recognizable from a screenshot

**This design fails if:**

1. Users say "it's too dark, I can't see anything" (contrast failure)
2. Described as "unfinished" or "broken" (not deliberate enough)
3. Accessibility scores drop (contrast, keyboard nav must stay AAA)
4. Slower performance (black should be faster, not slower)

---

## Next Steps (Implementation)

1. Update `src/index.css` with new CSS variables
2. Replace Tailwind config with black-only palette
3. Remove ALL oklch() colors, replace with hex
4. Update shadcn components: remove rounded corners, shadows
5. Redesign Dashboard, History, Settings, Setup components
6. Remove theme selector (always black)
7. Add green accent for recording states
8. Test with WCAG contrast analyzer
9. Capture screenshots for PR comparison

**Estimated effort:** 2-3 days of focused frontend work.

---

## Approval Checklist

- [ ] Pure black (#000000) background everywhere
- [ ] No greys, only white/green/red on black
- [ ] No gradients, no shadows, no blur
- [ ] 0px border radius (square everything)
- [ ] Monospace for data (hotkeys, timers, counts)
- [ ] Single accent color (green) for state only
- [ ] AAA contrast ratios maintained
- [ ] No AI-slop patterns (glassmorphism, sparkles, etc.)

**If any item is unchecked, the design is not approved.**
