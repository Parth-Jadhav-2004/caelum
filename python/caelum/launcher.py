"""Desktop entries point at the existing private-environment launcher."""

import configparser
import io
import os
import shutil
import tempfile
from pathlib import Path

APP_ID = "io.caelum.Dictation"
COMMENT = "Dictation with native Hyprland paste or manual copy on other desktops"


def entry_path(autostart=False):
    root = (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        if autostart
        else (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")))
    )
    return root / ("autostart/caelum.desktop" if autostart else f"applications/{APP_ID}.desktop")


def icon_path():
    return Path(__file__).resolve().parent / "icons/hicolor/scalable/apps/caelum.svg"


def write_entry(destination, text):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".caelum-")
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(text)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def migrate_legacy_launcher():
    destination = entry_path()
    legacy = destination.with_name("caelum.desktop")
    if legacy.is_symlink() or not legacy.is_file():
        return False
    try:
        original = legacy.read_text()
        document = configparser.ConfigParser(interpolation=None)
        document.optionxform = str
        document.read_string(original)
        entry = document["Desktop Entry"]
        if (entry.get("Name"), entry.get("Type"), entry.get("Comment")) != (
            "Caelum", "Application", COMMENT,
        ):
            return False
        if entry.get("Icon") in ("audio-input-microphone", "audio-input-microphone-symbolic"):
            entry["Icon"] = str(icon_path())
        entry["StartupWMClass"] = APP_ID
        if not destination.exists() and not destination.is_symlink():
            output = io.StringIO()
            document.write(output, space_around_delimiters=False)
            write_entry(destination, output.getvalue())
        entry["NoDisplay"] = "true"
        output = io.StringIO()
        document.write(output, space_around_delimiters=False)
        if output.getvalue() != original:
            write_entry(legacy, output.getvalue())
        return True
    except (OSError, ValueError, KeyError, configparser.Error):
        return False


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
    arguments = [launcher, "--config", config, "serve" if autostart else "app"]
    text = "\n".join(
        (
            "[Desktop Entry]",
            "Type=Application",
            "Name=Caelum",
            "Comment=" + COMMENT,
            "Icon=" + str(icon_path()),
            "StartupWMClass=" + APP_ID,
            "Exec=" + " ".join(map(desktop_quote, arguments)),
            "Terminal=false",
            "Categories=Utility;",
            "StartupNotify=false",
            "",
        )
    )
    write_entry(destination, text)
    if not autostart:
        migrate_legacy_launcher()
    return destination
