"""Load actual release-era formats; never use a developer's configuration/history."""

import shutil
import sqlite3
from pathlib import Path

import pytest
from caelum.config import load, save
from caelum.history import History
from caelum.sidecar import Backend

FIXTURES = Path(__file__).with_name("fixtures") / "upgrades"


@pytest.mark.parametrize("release", ["v0.3.9", "v0.4.0"])
async def test_release_upgrade_preserves_config_history_and_lifetime_totals(tmp_path, release):
    root = FIXTURES / release
    config = tmp_path / "config.toml"
    database = tmp_path / "history.sqlite3"
    shutil.copy2(root / "settings.toml", config)
    with sqlite3.connect(database) as connection:
        connection.executescript((root / "history.sql").read_text())
        original = connection.execute("SELECT * FROM dictations").fetchall()
        schema = connection.execute("PRAGMA table_info(dictations)").fetchall()
    before = config.read_bytes()
    settings = load(config)
    assert config.read_bytes() == before
    assert settings.desktop.color_theme == "t3-code"
    backend = Backend(config)
    backend.history = History(config, database)
    bootstrap = await backend.dispatch("bootstrap", {})
    assert bootstrap["config"]["app"]["hotkey"] == settings.app.hotkey
    assert (await backend.dispatch("history", {}))[0][
        "final_transcript"
    ] == "Example historical dictation"
    assert (await backend.dispatch("summary", {}))["total_words"] == 3
    await backend.dispatch("settings.save", {"config": {"desktop": {"color_theme": "ocean"}}})
    assert load(config).stt == settings.stt
    assert load(config).app == settings.app
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM dictations").fetchall() == original
        assert connection.execute("PRAGMA table_info(dictations)").fetchall() == schema
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("release", ["v0.3.9", "v0.4.0"])
def test_failed_upgrade_settings_write_keeps_old_file(tmp_path, monkeypatch, release):
    path = tmp_path / "config.toml"
    shutil.copy2(FIXTURES / release / "settings.toml", path)
    previous = path.read_bytes()
    settings = load(path)
    settings.desktop.color_theme = "iris"

    def interrupted(*args):
        raise OSError("simulated power loss before atomic rename")

    monkeypatch.setattr("caelum.config.os.replace", interrupted)
    with pytest.raises(OSError):
        save(settings, path)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".caelum-*"))
