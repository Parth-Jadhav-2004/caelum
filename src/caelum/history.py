"""Opt-in final transcripts only. No audio, raw text, source app, or credentials."""

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import load


def data_path():
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "caelum"
    return root / "history.sqlite3"


class History:
    def __init__(self, config_path=None, path=None):
        self.config_path = config_path
        self.path = Path(path) if path else data_path()

    def connect(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self.path.chmod(0o600)
        connection = sqlite3.connect(self.path, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("""CREATE TABLE IF NOT EXISTS dictations (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, final_transcript TEXT NOT NULL,
            duration_ms REAL NOT NULL, word_count INTEGER NOT NULL,
            latency_ms REAL NOT NULL, stt_model TEXT NOT NULL, cleanup_model TEXT NOT NULL,
            refined INTEGER NOT NULL, copied INTEGER NOT NULL,
            estimated_stt_usd REAL, hourly_rate REAL NOT NULL
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS history_date ON dictations(created_at)")
        return connection

    def prune(self, connection):
        preferences = load(self.config_path).desktop
        cutoff = datetime.now(timezone.utc) - timedelta(days=preferences.retention_days)
        connection.execute("DELETE FROM dictations WHERE created_at < ?", (cutoff.isoformat(),))

    def record(self, session, text, metrics, config, refined, copied):
        if not load(self.config_path).desktop.history_enabled:
            return
        duration = max(0, metrics.get("capture_ms", 0))
        rate = load(self.config_path).desktop.stt_usd_per_hour
        with closing(self.connect()) as connection, connection:
            self.prune(connection)
            connection.execute(
                "INSERT OR IGNORE INTO dictations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session,
                    datetime.now(timezone.utc).isoformat(),
                    text,
                    duration,
                    len(text.split()),
                    max(0, metrics.get("release_to_dispatch_ms", 0)),
                    config.stt.model,
                    config.cleanup.model,
                    int(refined),
                    int(copied),
                    duration / 3_600_000 * rate if rate else None,
                    rate,
                ),
            )

    def read(self, query="", limit=200):
        if not self.path.exists():
            return []
        with closing(self.connect()) as connection, connection:
            self.prune(connection)
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM dictations WHERE instr(lower(final_transcript), lower(?)) > 0 "
                    "ORDER BY created_at DESC LIMIT ?",
                    (query, limit),
                )
            ]

    def delete(self, identifier=None):
        if not self.path.exists():
            return
        with closing(self.connect()) as connection, connection:
            if identifier is None:
                connection.execute("DELETE FROM dictations")
            else:
                connection.execute("DELETE FROM dictations WHERE id = ?", (identifier,))
        with closing(self.connect()) as connection:
            connection.execute("VACUUM")

    def summary(self):
        today = datetime.now().astimezone().date()
        daily = {str(today - timedelta(days=offset)): 0 for offset in reversed(range(7))}
        result = dict(
            words=0,
            duration_ms=0,
            sessions=0,
            today_words=0,
            week_words=0,
            month_words=0,
            latency_ms=0,
            estimated_stt_usd=0,
            unpriced_sessions=0,
            daily=daily,
        )
        if not self.path.exists():
            result["wpm"] = 0
            return result
        with closing(self.connect()) as connection, connection:
            self.prune(connection)
            totals = connection.execute("""SELECT COUNT(*) AS sessions,
                COALESCE(SUM(word_count), 0) AS words,
                COALESCE(SUM(duration_ms), 0) AS duration_ms,
                COALESCE(AVG(latency_ms), 0) AS latency_ms,
                COALESCE(SUM(estimated_stt_usd), 0) AS estimated_stt_usd,
                COALESCE(SUM(estimated_stt_usd IS NULL), 0) AS unpriced_sessions
                FROM dictations""").fetchone()
            result.update(dict(totals))
            days = connection.execute("""SELECT date(created_at, 'localtime') AS day,
                SUM(word_count) AS words FROM dictations GROUP BY day""").fetchall()
        for row in days:
            day = datetime.fromisoformat(row["day"]).date()
            if day == today:
                result["today_words"] += row["words"]
            if today - timedelta(days=6) <= day <= today:
                result["week_words"] += row["words"]
                daily[str(day)] += row["words"]
            if day.year == today.year and day.month == today.month:
                result["month_words"] += row["words"]
        result["wpm"] = (
            result["words"] / (result["duration_ms"] / 60000) if result["duration_ms"] else 0
        )
        return result

    def export(self, destination):
        if not self.path.exists():
            raise ValueError("There are no saved dictations to export")
        with closing(self.connect()) as connection, connection:
            self.prune(connection)
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "w") as output:
                    for row in connection.execute("SELECT * FROM dictations ORDER BY created_at"):
                        output.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            except BaseException:
                Path(destination).unlink(missing_ok=True)
                raise
