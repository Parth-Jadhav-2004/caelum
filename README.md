# Caelum

Hold a shortcut, speak, and get the text back in the app you were using.

Caelum is dictation for Linux desktops. You bring a [Groq](https://console.groq.com) API key. Speech goes to that provider for transcription. Finished text is saved on your computer. The recording itself is not.

**Caelum 0.2.0 is a public preview** for x86-64 Linux. Download the package that matches your OS from [GitHub Releases](https://github.com/Parth-Jadhav-2004/caelum/releases). Install and compatibility details are in the [Linux guide](docs/linux.md).

## Install

Pick the package for your distribution. Check the `.sha256` file next to it before you install. Those checksums are integrity checks, not signed releases.

```sh
# Ubuntu 24.04. Debian users: pick the debian-12 or debian-13 package.
sudo apt install ./caelum_0.2.0-1_ubuntu-24.04_amd64.deb

# Arch
sudo pacman -U ./caelum-0.2.0-1-x86_64.pkg.tar.zst

# Fedora 43
sudo dnf install ./caelum-0.2.0-1.fedora43.x86_64.rpm
```

Packages are published for Ubuntu 24.04 and 26.04, Debian 12 and 13, Arch, and Fedora 43. Python libraries are bundled. GTK and audio libraries come from your distribution.

Open **Caelum** from the app launcher, or run `caelum app`. Installing the package does not start recording, enable autostart, or add a shortcut.

Uninstalling the package leaves `~/.config/caelum` and `~/.local/share/caelum` in place.

## Get a key and dictate

1. Open Caelum. First launch opens setup; Settings → **Open setup / Manage keys** reopens it.
2. Read the privacy explanation, choose a provider, and follow **Create a Groq API key**. Free usage has provider limits.
3. Enter the key and select **Save key**. Caelum uses the desktop keyring. If unavailable, it clearly reports an owner-only, unencrypted private-file fallback. Keys can be replaced or deleted here.
4. Continue to validate the key and every selected model, run the three-second **local-only** microphone test, then choose a shortcut. Desktop permission dialogs may appear when the service starts; portable desktops also offer manual recording.
5. Explicitly consent to upload a five-second practice sample. Practice text appears inside setup, with an optional Copy action; it is not pasted elsewhere or saved to history. A successful practice enables **Finish setup**. **Resume later** preserves your place; reopening rechecks provider access.
6. Choose **Start service**, then dictate:
   - **Hyprland:** hold **Super+Alt+V**, then release. Caelum pastes once into the original window.
   - **Other desktops:** choose **Record**, then **Finish recording**. Copy the completed text from Caelum and paste it yourself.

Existing environment keys and mode-600 `~/.config/caelum/environment` files remain supported. Keys saved in setup take precedence. Deleting a key in setup disables legacy environment fallback for that key until you save a replacement; edit shell/environment files separately to remove their copies.

Opening the window does not turn on the microphone. **Stop service** stops dictation and drops any audio still waiting. Closing the window leaves the service running. **Pause** ignores the shortcut until you resume.

A new install transcribes only. In Settings, the **Groq** preset turns on optional cleanup with the same key. **Transcription only** leaves the raw transcript. **Custom provider** is for another OpenAI-compatible endpoint. Put base URLs and model names under **Advanced**, then use **Check connection**. That check confirms the key can see the model list. It does not upload audio.

If cleanup is slow, unavailable, or not configured, you still get the transcript. Caelum labels that result as unrefined.

## What the app includes

- **Overview** shows whether dictation is stopped, ready, recording, processing, paused, or waiting to retry, plus the shortcut and recent results.
- **History** keeps completed transcripts, with search, copy, delete, and export. Audio, the raw provider transcript, and the source app are not stored.
- **Statistics** summarizes words, recording time, and how long release-to-paste took, using the history you still have.
- **Settings** covers the provider, shortcut, microphone, a three-second local microphone check, language, and how long history is kept. The microphone check stays on your machine.
- **Launcher and login** can be turned on from Settings. Neither is enabled by the installer.

History lives in `~/.local/share/caelum/history.sqlite3`. It is readable by your user and is not encrypted by Caelum. Delete an entry, or delete all of them, from History. The default retention period is 30 days and is applied the next time history is read or written.

## If something fails

- Press **Escape** during a Hyprland recording to cancel. On other desktops, use **Cancel** in Caelum.
- Presses shorter than 200 ms, and silence, insert nothing.
- If the network fails, the recording stays in memory for up to 60 seconds. Use **Retry** or **Cancel** in the notification, or:

  ```sh
  caelum control retry
  caelum control cancel
  caelum control status
  ```

- Switching apps while you are speaking copies the text and asks you to paste it. Caelum does not pull focus back to paste.
- Recordings stop at 120 seconds unless you raise that limit, up to 600 seconds.

`caelum doctor` checks the local setup. It does not record or upload audio.

## Privacy

Caelum keeps recorded audio out of saved files. Keys use the desktop keyring, with a private-file fallback when unavailable. The provider receives the audio and text you explicitly send.

| What | Where it goes |
| --- | --- |
| Microphone audio | Your transcription provider, only while a dictation or an explicit retry is in progress |
| Transcript text | Your refinement provider, when cleanup is turned on |
| Finished text | Local history, and the desktop clipboard so you can paste or recover it |
| API key | Desktop keyring; owner-only `credentials.json` fallback if unavailable. Legacy environment keys remain supported. |

The local microphone test does not upload, play back, or save audio. Clipboard managers can keep a copy after Caelum is done with it. Exports are separate files and stay after you delete history. Contributor-tier models, if you point cleanup at one, can use submitted text for training under that provider’s policy. The default setup does not use one.

Read the full [privacy notes](docs/privacy.md) before you dictate anything you would not want a provider, a clipboard manager, or an unlocked screen to hold.

## This preview

Qualified Hyprland sessions paste into the original window. Other desktops copy the text for you to paste. A package for your distribution does not mean every desktop on that distribution has been tested on real hardware.

Also outside this preview:

- A first-run setup wizard and in-app key storage
- A system tray icon
- Flatpak, Flathub, a published AUR package, and ARM builds
- Windows and macOS
- Offline speech recognition
- Encrypted history and automatic upgrades

GNOME and KDE hardware checks are still open. Portal shortcuts depend on the desktop. App-specific paste behavior varies.

## Build from source

Use this when you are changing Caelum. The packaged install above is the path for everyday use.

Python 3.11 or newer is required. Install GTK 4, PyGObject, Cairo, PortAudio, and [uv](https://docs.astral.sh/uv/), then:

```sh
./scripts/setup.sh
.venv/bin/caelum init
./scripts/run.sh app
```

`init` creates `~/.config/caelum/config.toml` and will not overwrite it. See [config.example.toml](config.example.toml). Manage keys in setup, or use the legacy environment file; never put them in TOML. `.env` is not loaded automatically.

```sh
.venv/bin/pytest -q
.venv/bin/ruff check src tests
```

Official native builds with a pinned signing key include **Settings → Updates**:
check GitHub for new versions, approve a verified download, and install on the
next app launch with administrator authorization. Source/AUR installations keep
using their package manager. [Updater behavior and release setup](docs/updates.md).

Further reading: [Linux installation](docs/linux.md), [privacy](docs/privacy.md), [architecture](docs/architecture.md), and [release notes for 0.2.0](docs/release-0.2.0.md).

## License

A license has not been added to this repository yet.
