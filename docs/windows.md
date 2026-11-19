# Windows x64 development build

The Windows app uses the same React application, design tokens, navigation,
onboarding, settings, history and model catalog as `dev`. The dictation
pipeline, JSON-lines contract, model validation and SQLite schema are shared.
Desktop integration lives in `python/caelum/windows_desktop.py`.

## Build on Windows

Install Node (see `.node-version`), Rust with the MSVC toolchain, Visual Studio
C++ Build Tools and Windows SDK, WebView2, Python 3.11+ and `uv`. From the
repository root in PowerShell:

```powershell
npm ci
python scripts/build_windows_runtime.py
src-tauri/windows-runtime/python.exe scripts/smoke_windows_engine.py
npx --no-install tauri build --bundles nsis
```

The current-user installer is in `src-tauri/target/release/bundle/nsis`.
Python, the microphone library and both local speech runtimes are bundled;
speech models are downloaded separately through setup as on Linux. For
interactive development after staging the runtime:

```powershell
uv sync --locked --python 3.12 --extra dev --extra whisper
npx --no-install tauri dev
```

The **Windows desktop** Actions workflow builds an installer, installs it to a
path with spaces, exercises the installed Python engine and checks WebView2
frontend startup. A successful run uploads `Caelum-Windows-x64`. This is a
development artifact; Authenticode signing and public release promotion require
the release owner's configuration. The stable update signer includes a Windows
installer when `caelum-<version>-windows-x64.exe` is present in the release
directory. Windows rechecks its signed manifest and hash before opening it.

## Desktop behavior to verify on a Windows machine

- Complete setup with a real microphone, once with an online provider and once
  with a downloaded model and the network disconnected.
- Focus a text field in Notepad. Use Ctrl + Win, the default for new setups, or your configured hold or toggle shortcut.
  The feedback pill should not take focus. Supported Windows Edit/RichEdit
  controls receive an addressed paste. For other controls or a focus change,
  use **Ctrl+V** in the intended field. A global synthetic Ctrl+V is never sent.
- Cancel with Escape, lock during capture, change input devices and test
  retry after a network interruption. Check tray hide/show and quit.
- Check light, dark and high-contrast appearances, the history calendar,
  export, dictionary, model switching, and Start Menu/startup shortcuts.

Config and setup metadata use `%APPDATA%\Caelum`; transcripts, models and the
update cache use `%LOCALAPPDATA%\Caelum`. Provider secrets are stored in Windows
Credential Manager. The GUI-owned service uses an in-process control channel;
Linux compositor, portal and Unix-socket CLI integrations are Linux-specific.
