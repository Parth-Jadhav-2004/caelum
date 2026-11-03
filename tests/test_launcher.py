import configparser
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from caelum import launcher


@pytest.fixture
def legacy_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    path = launcher.entry_path().with_name("caelum.desktop")
    path.parent.mkdir(parents=True)
    path.write_text(
        '[Desktop Entry]\nType=Application\nName=Caelum\n'
        'Comment=Dictation with native Hyprland paste or manual copy on other desktops\n'
        'Icon=audio-input-microphone\n'
        'Exec="/bin/true" "--config" "/custom config/100%%/config.toml" "app"\n'
        'Terminal=false\nCategories=Utility;\nStartupNotify=false\n'
        'X-Custom-Setting=keep\n'
    )
    return path


def read_entry(path):
    document = configparser.ConfigParser(interpolation=None)
    document.read(path)
    return document["Desktop Entry"]


def test_desktop_entry_matches_wayland_application_id(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    destination = launcher.install(tmp_path / "config.toml")
    assert destination.name == launcher.APP_ID + ".desktop"
    assert read_entry(destination)["StartupWMClass"] == launcher.APP_ID
    packaged = Path(__file__).resolve().parents[1] / "packaging" / destination.name
    assert packaged.is_file()
    assert read_entry(packaged)["StartupWMClass"] == launcher.APP_ID
    assert read_entry(packaged)["Icon"] == "caelum"


def test_upgrade_migrates_old_microphone_icon_without_losing_launch_arguments(legacy_entry):
    original = read_entry(legacy_entry)
    assert launcher.migrate_legacy_launcher()
    migrated = read_entry(launcher.entry_path())
    assert migrated["Exec"] == original["Exec"]
    assert migrated["X-Custom-Setting"] == "keep"
    assert migrated["Icon"] == str(launcher.icon_path())
    assert migrated["StartupWMClass"] == launcher.APP_ID
    assert "NoDisplay" not in migrated
    hidden = read_entry(legacy_entry)
    assert hidden["NoDisplay"] == "true"
    assert hidden["Icon"] == migrated["Icon"]
    assert hidden["Exec"] == migrated["Exec"]


def test_migration_is_idempotent(legacy_entry, monkeypatch):
    assert launcher.migrate_legacy_launcher()
    monkeypatch.setattr(launcher, "write_entry", lambda *_: pytest.fail("rewrote migrated entry"))
    assert launcher.migrate_legacy_launcher()


def test_migration_preserves_existing_canonical_entry_and_custom_icon(legacy_entry):
    destination = launcher.entry_path()
    destination.write_text("Existing user customization\n")
    legacy_entry.write_text(legacy_entry.read_text().replace(
        "Icon=audio-input-microphone", "Icon=my-custom-logo"
    ))
    assert launcher.migrate_legacy_launcher()
    assert destination.read_text() == "Existing user customization\n"
    assert read_entry(legacy_entry)["Icon"] == "my-custom-logo"


@pytest.mark.parametrize("text", ["invalid desktop entry", "[Desktop Entry]\nName=Another app\n"])
def test_migration_does_not_touch_unrecognized_entries(legacy_entry, text):
    legacy_entry.write_text(text)
    assert not launcher.migrate_legacy_launcher()
    assert legacy_entry.read_text() == text
    assert not launcher.entry_path().exists()


def test_migration_does_not_follow_legacy_symlinks(legacy_entry):
    target = legacy_entry.with_suffix(".backup")
    legacy_entry.rename(target)
    legacy_entry.symlink_to(target)
    assert not launcher.migrate_legacy_launcher()
    assert "audio-input-microphone" in target.read_text()


def test_migration_write_failure_does_not_block_app_startup(legacy_entry, monkeypatch):
    def denied(*_):
        raise PermissionError("read-only applications directory")

    monkeypatch.setattr(launcher, "write_entry", denied)
    assert not launcher.migrate_legacy_launcher()
    assert "audio-input-microphone" in legacy_entry.read_text()


def test_app_switcher_lookup_resolves_waveform_after_upgrade(legacy_entry):
    pytest.importorskip("gi")
    assert launcher.migrate_legacy_launcher()
    probe = '''
import json
from gi.repository import Gio
app = Gio.DesktopAppInfo.new("io.caelum.Dictation.desktop")
old = Gio.DesktopAppInfo.new("caelum.desktop")
assert app is not None and app.should_show()
assert old is not None and not old.should_show()
print(json.dumps({"id": app.get_id(), "icon": app.get_icon().to_string(),
                  "wm_class": app.get_startup_wm_class()}))
'''
    result = subprocess.run(
        [sys.executable, "-c", probe], env=os.environ.copy(),
        capture_output=True, text=True, timeout=10, check=True,
    )
    assert json.loads(result.stdout) == {
        "id": launcher.APP_ID + ".desktop",
        "icon": str(launcher.icon_path()),
        "wm_class": launcher.APP_ID,
    }
