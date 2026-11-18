# Caelum design

Caelum is a quiet place for your words. The desktop window is a library; recording happens through your shortcut and a small floating capsule.

## Surfaces and colour

Dark: canvas #121214, sidebar #0e0e10, raised #18181b, popover #1c1c20, hover #1f1f23, hairline #26262b, text #ededef, secondary text #96969f. Light: canvas #fbfbfa, sidebar/raised #f4f4f3, hover #eaeae8, hairline #e7e7e5, text #222226, secondary #606068. Primary actions are neutral. Caelum mint (#6ee7b7 dark / #237557 light) is the default accent. You can select Iris (#c4b5ed dark / #675394 light) or Ochre (#dec586 dark / #795a18 light); only the selected accent appears. The native pill stays neutral. Use the selected accent at most twice per screen: navigation and ready/listening state, or navigation and the selected Appearance swatch. Unselected swatches are neutral. Red means error, never recording or a routine destructive action.

No gradients, glow, decorative icon tiles or surface shadows. Popovers alone may use a shadow. Monochrome line icons. Soft rows replace bordered cards. Use a 10px surface radius and one-pixel borders. Controls and focus indicators have stronger contrast than surface hairlines.

## Typography and spacing

Five sizes: title 20/28 semibold; section 14/20 medium; body 14/20 regular; meta 12/16; display 28/32 medium. Counts use tabular numerals. Inter Variable with cv11/ss01, falling back to system sans. Never shrink hints below 12px.

Spacing uses 4, 8, 12, 16, 24, 32 and 48px. Page padding and section gaps are 32px. Settings rows are at least 48px; sidebar items 36px. Interactive targets are at least 24px, preferably 32px. Expanded sidebar is 240px; collapsed rail 48px.

## Voice and disclosure

Use the published waveform mark from website/mark.svg and the tightly set lowercase wordmark. Native app and tray icons share this mark. Light sidebar status uses #e7e7e5 as a distinct surface.

Everyday words, short labels, one clear action. No uppercase tracked eyebrows, filler subtitles or repeated facts. Settings show label left, control right, with useful help visible below the label. Tooltips name icon-only actions; they do not hide instructions, errors, or results. Accent previews are non-interactive; a labeled menu changes the accent. Show transcript metadata on request. Keep explicit upload consent and unencrypted-key warnings. Never imply that a saved key has passed a connection check.

## Accessibility and motion

Keep real headings, visible labels, named icon buttons, skip navigation, current-page state, live status and visible keyboard focus. Dialogs restore focus. Screen and pill fades last 160ms; sidebar resizing takes 200ms; honour system and explicit reduced motion. Recording uses neutral bars, never a red dot. Audit text contrast with `npm run check:themes` (4.5:1 minimum). The overlay never takes keyboard focus and is hidden at rest.
