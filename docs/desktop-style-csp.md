# Can the desktop drop `style-src 'unsafe-inline'`?

**Keep the allowance for now.** In Caelum 0.5.0 (`1fbb27b`, [issue #55](https://github.com/Parth-Jadhav-2004/caelum/issues/55)), removing it blocks Sonner’s toast stylesheet in WebKitGTK. Select menus and modal scroll locking also load inline stylesheets. Changing the microphone and progress bars alone would not fix these dependencies.

## What the desktop uses

The distinction is **how CSS reaches the WebView**. The packaged Vite stylesheet is a local asset allowed by `'self'`. React’s client-side `style` props and direct assignments such as `element.style.width` set individual CSS properties; these do not by themselves require permission for inline stylesheets. A `<style>` element containing CSS text does, even when trusted local JavaScript creates it.

First-party property writes:

- **Levels and progress:** `src/features/microphone.tsx` sets the meter fill width, `src/features/dashboard.tsx` sets waveform bar heights and animates the activity chart height with Motion, and `src/components/ui/progress.tsx` translates the setup/model download indicator. The values can remain numeric; alternatives include native `<meter>` / `<progress>` values or SVG geometry for the bars. Preserve their accessible names and values if changing the rendering.
- **Sidebar:** `src/components/ui/sidebar.tsx` sets desktop, icon and mobile widths with custom properties. These constants can live in CSS on the provider and the portalled mobile sheet. The exported menu skeleton also chooses a random text width; it has no current app caller and could use a fixed class.
- **First paint and theme changes:** `public/theme-init.js` sets the root background and color scheme before React loads; `src/lib/theme.tsx` updates the scheme and removes the startup background. These can use the existing root class and an early local stylesheet if the saved appearance still applies on the first frame.
- **Toast palette:** `src/components/ui/sonner.tsx` sets color and radius variables. A stylesheet selector on the toaster can supply those values, but this only replaces the wrapper styles.

Dependency-owned styles in the locked frontend:

- **Sonner 2.0.8:** `__insertCSS` in `sonner/dist/index.mjs` appends a `<style>` to the head for positioning, stacking and animations. Sonner also sets per-toast properties for measurements and swipes. A migration needs to load the base rules from a local CSS asset **and** stop the runtime injection.
- **Radix Select 2.4.1:** `SelectViewport` emits a `<style>` with scrollbar rules when the device/settings menu opens. The viewport accepts a nonce, but `src/components/ui/select.tsx` supplies none. The rules are static candidates for extraction or an exact CSP hash.
- **Modal scroll lock:** Radix overlays use `react-remove-scroll-bar` (2.3.8), which injects rules through `react-style-singleton` (2.2.3). The CSS includes measured scrollbar gaps and body offsets; one fixed stylesheet hash cannot cover all layouts. Move the rules to a local stylesheet with measured values set as properties, or use a per-document nonce supported by the injector and the host policy.
- **Positioning and measurement:** Radix popups also set coordinates, transforms and size variables; `cmdk` writes `--cmdk-list-height` for the command palette. These property writes are distinct from the injected stylesheets above.

## Evidence and next verification

A Linux WebKitGTK 2.54.1 comparison used `npm ci` and `npm run build`. To repeat, serve `dist/frontend/` over loopback with the CSP from `src-tauri/tauri.conf.json` as an HTTP response header. Load `/`, wait for the app to render, then inspect the `<style>` whose text contains `[data-sonner-toaster]`. Append an `ol` with that data attribute to the body and inspect its computed `position`. Repeat in a fresh view with only `'unsafe-inline'` removed.

- **Configured policy:** the Sonner style had a `sheet`; the probe’s position was `fixed`.
- **`style-src 'self'`:** the same style element was present but its `sheet` was null, the position was `static`, and WebKit reported an inline `style-src-elem` violation.

This isolates the production frontend; it does not exercise Tauri IPC or qualify a packaged app. Revisit after the injectors can work under a narrower policy. Before shipping it, test release packages on Linux (WebKitGTK) and Windows (WebView2): cold-start into a saved theme, observe moving levels and download progress, resize/collapse the sidebar, open and keyboard-dismiss selects and dialogs, verify background scroll locks and restores, and trigger and dismiss a positioned toast. Record the candidate, WebView versions, observed appearance and interaction, and any style CSP violations.
