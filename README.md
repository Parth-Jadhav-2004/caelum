# Caelum

Caelum turns speech into text you can insert or paste into your apps on Linux and Windows. Download a speech model once to dictate offline without an API key, or use your own online provider for transcription and optional text cleanup.

[Download for your desktop](https://parth-jadhav-2004.github.io/caelum/#download) · [Latest stable release and checksums](https://github.com/Parth-Jadhav-2004/caelum/releases/latest) · [Release notes](CHANGELOG.md) · [MIT license](LICENSE)

## Install Caelum

From the stable release, download **one** package for your operating system and `SHA256SUMS` into an empty folder. Open a terminal in that folder.

**Windows x64:** In PowerShell, run the command below. Compare the hash with the entry for your `.exe` in `SHA256SUMS`. If they match, open the installer. Windows SmartScreen may warn that the installer is unsigned. See [Windows setup](docs/windows.md) for details.

```powershell
Get-FileHash -Algorithm SHA256 .\caelum-*-x64-setup.exe
```

**Linux x86-64:** Choose the package for your exact distribution and version. Verify the download first:

```sh
sha256sum --check --ignore-missing SHA256SUMS
```

Once your package reports `OK`, run only the command for your download:

- **Ubuntu 24.04, Ubuntu 26.04, or Debian 12** (`.deb`): `sudo apt install ./caelum_*.deb`
- **Fedora 43** (`.rpm`): `sudo dnf install ./caelum-*.rpm`
- **Arch Linux** (`.pkg.tar.zst`): `sudo pacman -U ./caelum-*.pkg.tar.zst`
- **AppImage** (Ubuntu 24.04-compatible userspace with WebKitGTK 4.1 and PortAudio): `chmod +x ./caelum-*.AppImage`, then `./caelum-*.AppImage`. The native Hyprland overlay also needs GTK 4, gtk4-layer-shell, and their introspection typelibs.

## Dictate your first sentence

1. Open Caelum and choose **On this computer** or **Online**. For local dictation, pick a model for your language and download it. Local inference on x86-64 needs AVX2 and enough free memory for the model. For online dictation, enter your provider key.
2. Select your microphone and run the local mic test. Set your shortcut and try **Practice**. Online practice asks before uploading audio.
3. On **Home**, select **Record**, say “Meet me at the station at nine,” then select **Finish recording**. If Caelum shows **Copied**, paste into your editor. Otherwise, select **Copy transcript** on Home or copy the saved entry from History.

For hold-to-talk, focus a text field, hold your configured shortcut while speaking, then release. Native Hyprland can paste into the original window if it still has focus. Windows can insert directly into supported Edit and RichEdit fields. On GNOME and KDE, paste the result yourself; the Home controls also work if the desktop denies the shortcut.

## Where your words go

- **On this computer:** The downloaded model processes audio locally. Online fallback is off by default. If you enable it, Caelum can send audio to your provider when the model is missing or cannot load.
- **Online:** Your transcription provider receives audio and custom vocabulary. If you enable online cleanup, its provider also receives the transcript.
- **History and clipboard:** Caelum saves final transcripts by default, not recordings. The local history database is unencrypted. Turn off **Save dictation history** in **Settings → Privacy & data** to stop saving new entries. Clipboard managers and exports can keep separate copies. See the [privacy and retention guide](docs/privacy.md).

## Guides and development

- [Linux first-run help](docs/linux.md#first-run-help) and [Windows desktop behavior](docs/windows.md#desktop-behavior-to-verify-on-a-windows-machine): microphone, shortcut, and paste troubleshooting.
- [Vocabulary and spoken formatting](docs/desktop-reference.md#vocabulary-offline-transcription-and-cleanup-styles): dictate a list or add names the recognizer should know.
- [Local models](docs/desktop-reference.md#on-this-computer) and [optional NVIDIA setup](docs/nvidia.md): choose, verify, and run a model on your hardware.
- [Try the development app on Linux](docs/try-dev.md) or [build on Windows](docs/windows.md#build-on-windows). For checks and packaging, see the [desktop reference](docs/desktop-reference.md) and [contributing guide](CONTRIBUTING.md).
