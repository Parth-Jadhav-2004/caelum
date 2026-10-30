"""Desktop entries point at the existing private-environment launcher."""

import os
import shutil
import tempfile
from pathlib import Path


def entry_path(autostart=False):
    root = (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        if autostart
        else (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")))
    )
    return root / ("autostart/caelum.desktop" if autostart else "applications/caelum.desktop")


def desktop_quote(value):
    if any(character in str(value) for character in "\n\r\0"):
        raise ValueError("Desktop entry paths cannot contain line breaks or NUL")
    return (
        '"'
        + str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("%", "%%")
        + '"'
    )


def install(config, autostart=False, enabled=True):
    destination = entry_path(autostart)
    if not enabled:
        destination.unlink(missing_ok=True)
        return destination
    launcher = Path(__file__).resolve().parents[2] / "scripts/run.sh"
    if not launcher.is_file():
        executable = shutil.which("caelum")
        if not executable:
            raise RuntimeError("Install Caelum or run it from a source checkout")
        launcher = Path(executable).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    arguments = [launcher, "--config", config, "serve" if autostart else "app"]
    text = "\n".join(
        (
            "[Desktop Entry]",
            "Type=Application",
            "Name=Caelum",
            "Comment=Dictation with native Hyprland paste or manual copy on other desktops",
            "Icon=audio-input-microphone",
            "Exec=" + " ".join(map(desktop_quote, arguments)),
            "Terminal=false",
            "Categories=Utility;",
            "StartupNotify=false",
            "",
        )
    )
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".caelum-")
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(text)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination
