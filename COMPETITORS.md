# Competitive research: Caelum vs dictation apps

Researched 14 November 2026. Caelum claims are from `origin/main` at
`6325b9a` (0.4.1). Competitor claims are only from each product's own site,
docs or README (sources at the end). Cells marked **P** are partial; notes
follow the table.

---

## What Caelum has today

Caelum is a Linux-first push-to-talk dictation app: Tauri desktop UI + Python
engine. Documented capabilities on main:

### Capture and control
- Hold-to-talk and press-to-toggle (`config.example.toml`, `python/caelum/config.py`)
- Configurable global hotkey, including modifier-only combos (`config.example.toml`)
- Hyprland backend: Lua binds, Escape cancel, target window captured at press,
  paste aimed at that window (`python/caelum/linux.py`)
- Portable backend: optional XDG GlobalShortcuts portal, `wl-copy` /
  `xclip` clipboard, `notify-send` status, Record/Finish in the UI
  (`python/caelum/portable.py`, `src/features/dashboard.tsx`)
- In-app Record / Finish / Cancel / Retry / Pause service
  (`src/features/dashboard.tsx`, `python/caelum/orchestrator.py`)
- CLI: `caelum control` (`start|stop|toggle|cancel|retry|pause|resume|…`),
  `doctor`, `devices`, `models`, `serve`, `app` (`python/caelum/cli.py`)

### Transcription and refinement
- Any OpenAI-compatible STT endpoint; Groq Whisper default
  (`config.example.toml`, `python/caelum/providers.py`)
- Optional LLM cleanup with off / light / thorough (`src/features/settings.tsx`,
  `python/caelum/providers.py`, `python/caelum/quality.py`)
- Language field (blank = auto-detect) and vocabulary string sent as Whisper
  `prompt` — config only; vocabulary has no Settings UI
  (`config.example.toml` lines 21–22, `python/caelum/providers.py` 131–134)
- Experimental chunked strategy (`config.example.toml`,
  `python/caelum/segmenter.py`, `python/caelum/orchestrator.py`)
- Bounded in-memory PCM; max duration; silence floor; never writes recordings
  (`python/caelum/audio.py`, README)
- Explicit retry of failed uploads from held PCM until expiry
  (`python/caelum/orchestrator.py`)

### Desktop UX
- Tauri app: Home, Statistics, History, Settings, command palette (Ctrl+K)
  (`src/App.tsx`, `src/features/*`)
- Four-step onboarding: provider key + consent → mic test → shortcut →
  consented practice (`src/features/setup.tsx`, `python/caelum/onboarding.py`)
- Themes: dark / light / system + color palettes (`src/lib/themes.ts`,
  `src/features/settings.tsx`)
- Searchable history (200), export JSONL, delete, retention days, optional
  disable (`src/features/history.tsx`, `python/caelum/history.py`)
- Stats: lifetime / today / month words, WPM, 7-day chart, calendar
  (`src/features/dashboard.tsx`, `python/caelum/history.py`)
- Tray with open / pause / resume / quit; hide-to-tray only if
  StatusNotifierWatcher present (`src-tauri/src/main.rs`)
- Native GTK4 layer-shell recording pill: no keyboard focus, empty input
  region, real energy bars (`python/caelum/hud.py`)

### Privacy, safety, packaging
- Keys via Secret Service, else owner-only mode-600 file with disclosure
  (`python/caelum/credentials.py`, setup UI)
- Contributor-model training consent gate (`python/caelum/onboarding.py`,
  `python/caelum/providers.py`)
- MPRIS pause/resume while recording (`python/caelum/media.py`)
- Lock/suspend cancels capture; single-instance daemon lock; UID-checked
  Unix socket (`python/caelum/service.py`)
- Signed native-package updates (Ed25519), check / stage / apply, no silent
  auto-download (`python/caelum/updates.py`, `src/features/settings.tsx`)
- Distro packages with vendored wheels (`scripts/build_package.py`, README)

### Explicitly not present on main
- No local/offline STT engine (cloud HTTP only)
- No snippets / smart-replace UI
- No named cleanup styles or per-app mode switching
- No command mode over selected text
- No file/meeting transcription
- No start/stop audio cue
- No vocabulary editor in the UI (backend field only)

---

## Feature comparison

| Feature | Caelum | Wispr Flow | Superwhisper | MacWhisper | Aqua Voice | VoiceInk | Willow | Handy | Whispering | nerd-dictation | Talon |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Linux desktop | **Y** (Wayland + Hyprland) | – | – | – | – | – | – | Y (Wayland limited) | P | Y | P (X11 only; Wayland not planned) |
| Push-to-talk / toggle | Y | Y | Y | – | Y | Y | Y | Y | P (toggle) | P (begin/end) | – |
| Paste into focused app | Y | Y | Y | Y | Y | Y | Y | Y | – | Y | Y |
| Floating recording UI | Y (focus-safe pill) | – | Y | – | – | – | – | P (off by default on Linux) | – | – | – |
| Cloud STT | Y | Y | Y | Y (Pro) | Y | Y | Y | – | Y | – | – |
| Local / offline STT | – | – | Y | Y | – | Y | Y | Y | Y | Y | Y |
| AI cleanup / polish | Y | Y | Y | Y (Pro) | Y | Y | Y | P | P (transformations) | – | – |
| Styles / modes / tone | – | Y | Y | – | Y | Y | Y | – | Y | – | – |
| Auto-switch by app | – | Y | Y | – | – | Y | – | – | – | – | Y |
| Custom vocabulary | P (TOML only) | Y | Y | – | Y | Y | Y | Y | – | P | Y |
| Snippets / replacements | – | Y | – | – | – | Y | Y | P (hook) | – | P | Y |
| Command mode (edit selection) | – | Y | – | – | Y (Max) | Y | – | – | – | – | Y |
| Language + auto-detect | P (Advanced field) | Y | Y | Y | Y | Y | Y | Y | – | P | P |
| Searchable history | Y | – | Y | Y | Y | – | – | Y | Y | – | – |
| Privacy / local retention control | Y | – | – | Y | Y | Y | Y | Y | Y | Y | Y |
| Pause media while recording | Y | – | Y | – | – | Y | – | – | – | – | – |
| Retry without re-speaking | Y | – | – | – | – | – | – | – | – | – | – |
| Audio start/stop cue | – | – | – | – | – | – | – | Y | – | – | – |
| CLI / scriptable | Y | – | – | Y (Pro) | Y | – | – | Y | – | Y | Y |
| File transcription | – | – | Y | Y | – | – | – | – | – | – | – |
| Usage statistics | Y | Y | – | – | – | – | – | – | – | – | – |

**Partial notes**
- Caelum vocabulary: `stt.vocabulary` is sent as Whisper `prompt`
  (`providers.py`); no editor in `src/features/settings.tsx`.
- Caelum language: editable under Settings → Advanced as free text; blank =
  auto (`config.example.toml`, settings Advanced tab).
- Handy overlay: README says overlay is off by default on Linux because it can
  steal focus and break paste.
- Talon: official docs require X11; Wayland support is not planned.
- Whispering: Tauri desktop build docs center on macOS; Linux desktop not
  claimed as a first-class product surface.
- nerd-dictation: offline VOSK; begin/end CLI rather than hold-to-talk UI.

---

## Missing features (prioritized)

Only features verified in at least one competitor source, and absent or only
partial in Caelum.

### High

1. **Custom vocabulary in Settings** — S  
   Have it: Wispr Flow, Superwhisper, Aqua, VoiceInk, Willow, Handy, Talon.  
   Why: Linux power users dictate code identifiers, window-manager names and
   product jargon; wrong spellings force keyboard fixes and kill the
   private-by-default “speak and move on” loop. Caelum already sends the field.  
   Where: `src/features/settings.tsx` (new Vocabulary row/section); existing
   `Config.stt.vocabulary` / `python/caelum/providers.py` 133–134.

2. **Local / offline transcription path** — L  
   Have it: Superwhisper, MacWhisper, VoiceInk, Willow, Handy, Whispering,
   nerd-dictation, Talon.  
   Why: Private-by-default is incomplete while every utterance must hit a
   network provider. Offline also helps Omarchy/Hyprland users on flaky
   networks. The OpenAI-compatible `base_url` can talk to a local server
   today, but there is no first-class local engine, download UX or offline
   default.  
   Where: new local backend beside `python/caelum/providers.py` (or document +
   preset for a local OpenAI-compatible Whisper server in Settings →
   Advanced / Transcription); packaging under `scripts/build_package.py`.

3. **Named cleanup styles (not just off/light/thorough)** — M  
   Have it: Wispr Styles, Superwhisper Modes, VoiceInk Modes, Aqua writing
   style, Willow style-matching, Whispering transformations.  
   Why: One global cleanup strength is too coarse for Slack vs commit messages
   vs code comments. Styles stay local policy over text after STT; they do not
   require screen capture.  
   Where: extend `Config.cleanup` in `python/caelum/config.py`; apply in
   `providers.py` cleanup prompt; UI in `src/features/settings.tsx`.

### Medium

4. **Per-app / per-window style rules** — M  
   Have it: Wispr, Superwhisper auto-activation, VoiceInk Power Mode (app/URL),
   Talon per-app commands.  
   Why: Hyprland already exposes window class/address at press time
   (`python/caelum/linux.py` `target_at_press`). Matching that to a style makes
   Linux feel as smart as Mac competitors without reading screen pixels.  
   Where: new map in config; resolve style in `orchestrator.py` using
   `linux.Target`; Settings UI for class → style.

5. **Snippets / smart text replacements** — M  
   Have it: Wispr Snippets, VoiceInk Smart Replace, Willow Shortcuts; Handy
   via post-paste hook; nerd-dictation via Python config.  
   Why: Deterministic expansions (“meeting link” → URL) need no cloud model and
   fit a privacy-first Linux tool.  
   Where: post-STT / post-cleanup pass in `orchestrator.py` or `quality.py`;
   editor in Settings; store beside config under XDG.

6. **Language picker with explicit Auto** — S  
   Have it: Wispr, Superwhisper, MacWhisper, Aqua, VoiceInk, Willow, Handy
   (Parakeet auto-detect).  
   Why: Field exists but is buried as Advanced free text; users who switch
   languages need a visible control.  
   Where: `src/features/settings.tsx` General (or Transcription) select bound
   to `config.stt.language`.

7. **Start/stop audio cue (optional)** — S  
   Have it: Handy (Audio Feedback when overlay is off).  
   Why: On GNOME/KDE portable mode Caelum has no layer-shell pill—only
   notifications. A short cue confirms capture without a window.  
   Where: play via `canberra-gtk-play` / `pw-play` from `orchestrator.py`
   state transitions; toggle under Settings → Recording.

### Low

8. **Command mode (edit selection by voice)** — L  
   Have it: Wispr Flow Command Mode, Aqua Voice Commands (Max), VoiceInk
   rewrite selection, Talon command mode.  
   Why: Powerful, but Wayland selection capture is hard and sending existing
   buffer text to a model expands the privacy surface. Ship after styles and
   only as opt-in.  
   Where: second shortcut in `linux.py` / `portable.py`; new IPC action;
   Settings → Experimental.

9. **File / batch transcription** — L  
   Have it: Superwhisper, MacWhisper.  
   Why: Useful, but outside push-to-talk into the focused app—the core Caelum
   job.  
   Where: new History or Tools flow; reuse `providers.stt` on file PCM from
   `audio.read_wav`.

10. **Shared / team dictionaries** — L  
    Have it: Wispr shared dictionary, Aqua Business shared dictionaries.  
    Why: Conflicts with private-by-default single-user positioning on Omarchy.  
    Where: skip unless multi-user demand appears.

---

## What Caelum already does well

Relative to this set, Caelum is strongest as a **Wayland/Hyprland-native,
privacy-hard dictation daemon**: focus-safe layer-shell HUD, target-addressed
paste, lock/suspend safety, MPRIS pause, in-memory retry without re-speaking,
UID-checked socket + CLI, and OpenAI-compatible providers with explicit
consent—capabilities Mac-centric apps either skip or document as broken on
Linux.

---

## Sources

### Caelum (code on `origin/main`)
- `config.example.toml`
- `python/caelum/{audio,cli,config,credentials,history,hud,linux,media,onboarding,orchestrator,portable,providers,quality,segmenter,service,updates}.py`
- `src/features/{dashboard,history,settings,setup}.tsx`, `src/App.tsx`
- `src-tauri/src/main.rs`
- `README.md`

### Competitors
- Wispr Flow features: https://wisprflow.ai/features
- Wispr Flow Command Mode: https://docs.wisprflow.ai/articles/4816967992-how-to-use-command-mode
- Superwhisper: https://superwhisper.com
- Superwhisper modes: https://superwhisper.com/docs/modes/modes
- MacWhisper: https://goodsnooze.gumroad.com/l/macwhisper
- Aqua Voice: https://withaqua.com
- VoiceInk README: https://github.com/Beingpax/VoiceInk
- VoiceInk site: https://tryvoiceink.com
- Willow Voice: https://willowvoice.com
- Handy README: https://github.com/cjpais/Handy
- Whispering README: https://github.com/epicenter-so/epicenter/blob/main/apps/whispering/README.md
- nerd-dictation: https://github.com/ideasman42/nerd-dictation
- Talon getting started (platforms / Wayland): https://talonvoice.com/docs/reference/official.html
- Talon 1.0 changelog: https://talonvoice.com/dl/latest/changelog.html
