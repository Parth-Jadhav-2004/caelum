import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from caelum.config import Config, load, save
from caelum.history import History


@pytest.fixture
def storage(tmp_path):
    config = Config()
    path = tmp_path / "config.toml"
    save(config, path)
    history = History(path, tmp_path / "data/history.sqlite3")
    return config, path, history


def record(storage, identifier="session", text="A few spoken words.", copied=False):
    config, _, history = storage
    history.record(
        identifier,
        text,
        {"capture_ms": 60000, "release_to_dispatch_ms": 1500},
        config,
        True,
        copied,
    )


def enable(storage, rate=0):
    config, path, _ = storage
    config.desktop.history_enabled = True
    config.desktop.stt_usd_per_hour = rate
    save(config, path)


def test_disabled_history_does_not_create_database(storage):
    record(storage)
    history = storage[2]
    assert not history.path.exists()
    assert history.read() == []
    assert history.summary()["sessions"] == 0
    assert not history.path.exists()


def test_private_permissions_deduplication_and_schema(storage):
    enable(storage, rate=3.6)
    record(storage)
    record(storage)
    history = storage[2]
    rows = history.read()
    assert len(rows) == 1
    assert history.path.stat().st_mode & 0o777 == 0o600
    assert history.path.parent.stat().st_mode & 0o777 == 0o700
    assert not {"raw_transcript", "audio", "source_app"} & rows[0].keys()
    assert rows[0]["estimated_stt_usd"] == pytest.approx(0.06)
    summary = history.summary()
    assert summary["today_words"] == summary["week_words"] == summary["words"] == 4
    assert summary["sessions"] == 1
    assert summary["wpm"] == 4
    assert summary["latency_ms"] == 1500
    assert sum(summary["daily"].values()) == 4


def test_search_literal_and_delete_recalculates(storage):
    enable(storage)
    record(storage, "one", "Literal 100% _ and 'quotes'")
    record(storage, "two", "Other words", copied=True)
    history = storage[2]
    assert len(history.read("100% _")) == 1
    assert len(history.read("' OR 1=1 --")) == 0
    assert history.summary()["unpriced_sessions"] == 2
    history.delete("one")
    assert history.summary()["words"] == 2
    history.delete()
    assert history.read() == []
    assert history.summary()["sessions"] == 0


def test_disabling_is_checked_at_write_time(storage):
    enable(storage)
    record(storage)
    config, path, history = storage
    config.desktop.history_enabled = False
    save(config, path)
    record(storage, "not-saved")
    assert len(history.read()) == 1


def test_retention_and_export(storage, tmp_path):
    enable(storage)
    record(storage, "old")
    record(storage, "new", "Sensitive new words")
    history = storage[2]
    with sqlite3.connect(history.path) as connection:
        connection.execute(
            "UPDATE dictations SET created_at = ? WHERE id = 'old'",
            ((datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),),
        )
    destination = tmp_path / "export.jsonl"
    history.export(destination)
    assert [json.loads(line)["id"] for line in destination.read_text().splitlines()] == ["new"]
    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        history.export(destination)
    assert history.summary()["sessions"] == 1


def test_rate_is_snapshotted_not_retroactive(storage):
    enable(storage, rate=3)
    record(storage, "first")
    enable(storage, rate=6)
    record(storage, "second")
    assert storage[2].summary()["estimated_stt_usd"] == pytest.approx(0.15)


def test_settings_roundtrip_and_failed_save_preserves_existing(storage):
    config, path, _ = storage
    config.app.microphone = 'USB "Microphone"'
    config.stt.vocabulary = "नमस्ते\nCaelum"
    config.desktop.theme = "dark"
    save(config, path)
    assert load(path) == config
    assert path.stat().st_mode & 0o777 == 0o600
    original = path.read_bytes()
    config.desktop.retention_days = 0
    with pytest.raises(ValueError):
        save(config, path)
    assert path.read_bytes() == original
    assert not list(path.parent.glob(".caelum-*"))
