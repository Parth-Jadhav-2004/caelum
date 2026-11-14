-- Schema extracted from v0.3.9:src/caelum/history.py; data is synthetic.
CREATE TABLE IF NOT EXISTS dictations (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, final_transcript TEXT NOT NULL,
            duration_ms REAL NOT NULL, word_count INTEGER NOT NULL,
            latency_ms REAL NOT NULL, stt_model TEXT NOT NULL, cleanup_model TEXT NOT NULL,
            refined INTEGER NOT NULL, copied INTEGER NOT NULL,
            estimated_stt_usd REAL, hourly_rate REAL NOT NULL
        );
CREATE INDEX IF NOT EXISTS history_date ON dictations(created_at);
CREATE TABLE IF NOT EXISTS usage_totals (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1), words INTEGER NOT NULL
        );
INSERT OR IGNORE INTO usage_totals
            SELECT 1, COALESCE(SUM(word_count), 0) FROM dictations;
INSERT INTO dictations VALUES ('legacy-session','2026-11-01T12:00:00+00:00','Example historical dictation',3000,3,250,'whisper-large-v3-turbo','',0,1,NULL,0);
UPDATE usage_totals SET words=3 WHERE singleton=1;
