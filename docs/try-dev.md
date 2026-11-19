# Try the native development app on this Linux PC

Quit the existing Caelum app **and service** from the tray first. Do not interrupt an active recording. The commands below create a new sibling checkout without changing the parent repo, and launch native Tauri (not just Vite). Use the distro build dependencies in [linux.md](linux.md), Node 24+, Rust with the pinned toolchain, and uv.

```bash
checkout=$(mktemp -d "$HOME/caelum-dev-test.XXXXXXXX")
git clone --branch dev --single-branch https://github.com/Parth-Jadhav-2004/caelum.git "$checkout"
cd "$checkout"
git rev-parse HEAD
uv sync --locked --extra dev --extra local --python /usr/bin/python3
npm ci
bash scripts/try-portable.sh
```

The launcher prints the new test profile path. It sets the backend to portable **even on Hyprland**, uses a separate test key name, disables launch-time update checks, and leaves the real session bus, audio and clipboard available. It does not alter your normal app settings/history. Models go in the test profile; allow disk space for a separate download. If testing Online, use your own consenting provider account in setup and remove the test key in the app afterward. Each invocation creates a fresh profile. Stop the dev process and quit the app before relaunching. No system package installation is needed.

1. **Local:** on a fresh profile choose **On this computer**. Download a compatible model (Parakeet 110M is a small English option). Disconnect the network after it is ready. Run practice, then Record → speak → Finish recording. No online fallback, key or upload consent should be needed.
2. **Online:** launch another fresh profile. Choose **Online**, enter your own key and review the consent. Repeat with cleanup off/on. Speak “Start Caelum test number forty two and finish here.” Check both boundary words, name and number; try silence. Do not post the transcript or key.
3. **Portable:** deny a global shortcut and use the on-screen controls. With history on, copy the result and paste in an editor. Turn history off, repeat and paste directly; confirm no new history row. Cancel once and quit/reopen. Note desktop/session, mic, SHA and result. A Hyprland portable run is useful but does not certify GNOME, KDE or X11. For a release decision use the actual RC package and [complete acceptance procedure](acceptance.md).
