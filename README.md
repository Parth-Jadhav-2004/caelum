# Caelum Linux invite-only beta

**[Download Caelum 0.5.0 testing candidate](https://github.com/Parth-Jadhav-2004/caelum/releases/tag/v0.5.0-rc.44462311027)** · `v0.5.0-rc.44462311027`

[Candidate run 44462311027, attempt 1](https://github.com/Parth-Jadhav-2004/caelum/actions/runs/44462311027) built commit `b7fd32a60c9f81cf5f11a89ff4e195f26ac5817a`. These packages are for invited testers on x86-64 Linux. Use a disposable login or back up your existing Caelum settings and history.

## Verify and install

1. Download your package below and [SHA256SUMS](https://github.com/Parth-Jadhav-2004/caelum/releases/download/v0.5.0-rc.44462311027/SHA256SUMS) into a fresh directory.
2. In that directory run `sha256sum --check --ignore-missing SHA256SUMS`. Confirm the exact downloaded package filename says **OK**.
3. Run the install command in its row, then open Caelum from your application launcher.

| Distribution | Testing package | Install command |
| --- | --- | --- |
| Ubuntu 24.04 | [caelum_0.5.0-1_ubuntu-24.04_amd64.deb](https://github.com/Parth-Jadhav-2004/caelum/releases/download/v0.5.0-rc.44462311027/caelum_0.5.0-1_ubuntu-24.04_amd64.deb) | `sudo apt install ./caelum_0.5.0-1_ubuntu-24.04_amd64.deb` |
| Ubuntu 26.04 | [caelum_0.5.0-1_ubuntu-26.04_amd64.deb](https://github.com/Parth-Jadhav-2004/caelum/releases/download/v0.5.0-rc.44462311027/caelum_0.5.0-1_ubuntu-26.04_amd64.deb) | `sudo apt install ./caelum_0.5.0-1_ubuntu-26.04_amd64.deb` |
| Debian 12 | [caelum_0.5.0-1_debian-12_amd64.deb](https://github.com/Parth-Jadhav-2004/caelum/releases/download/v0.5.0-rc.44462311027/caelum_0.5.0-1_debian-12_amd64.deb) | `sudo apt install ./caelum_0.5.0-1_debian-12_amd64.deb` |
| Fedora 43 | [caelum-0.5.0-1.fedora43.x86_64.rpm](https://github.com/Parth-Jadhav-2004/caelum/releases/download/v0.5.0-rc.44462311027/caelum-0.5.0-1.fedora43.x86_64.rpm) | `sudo dnf install ./caelum-0.5.0-1.fedora43.x86_64.rpm` |
| Arch Linux | [caelum-0.5.0-1-x86_64.pkg.tar.zst](https://github.com/Parth-Jadhav-2004/caelum/releases/download/v0.5.0-rc.44462311027/caelum-0.5.0-1-x86_64.pkg.tar.zst) | `sudo pacman -U ./caelum-0.5.0-1-x86_64.pkg.tar.zst` |

## Choose how to transcribe

- **Online** uses your provider API key. Check the provider and model in setup, then consent to send practice audio. Optional online cleanup also sends text to the configured provider.
- **On this computer** runs speech recognition locally. Pick a model compatible with your language and available RAM, download it once, then disconnect and practice. No API key is required.

## Try a first paste

1. Open Caelum, choose your mode, test your microphone and choose **Record practice**. Say “Meet me at noon.”
2. On GNOME, KDE or X11 with portable controls, open Home, select **Record**, speak and select **Finish recording**. You can use the controls even if global shortcut permission is denied.
3. With history on, copy the completed transcript from History. With history off, the completed text goes to the clipboard. Switch to a text editor and paste.
4. On Hyprland, start from the editor using the shortcut shown on Home. Check that the transcript appears in the intended window.

Record your release tag, package hash, desktop session, microphone type, speech mode and first-paste result against the [acceptance checklist](https://github.com/Parth-Jadhav-2004/caelum/issues/26). Keep recordings, private transcripts and credentials out of reports.
