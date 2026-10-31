import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "scan_privacy", Path(__file__).resolve().parents[1] / "scripts/scan_privacy.py"
)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def test_scan_rejects_runtime_files_and_secrets_without_echoing_values(tmp_path):
    database = tmp_path / "history.sqlite3"
    database.write_bytes(b"private transcript")
    key = "gsk_" + "A" * 50
    source = tmp_path / "unexpected.txt"
    source.write_text(key)
    issues = scanner.scan([database, source])
    assert len(issues) == 2
    assert key not in str(issues)
    assert "private transcript" not in str(issues)


def test_examples_and_public_key_are_allowed(tmp_path):
    example = tmp_path / "config.example.toml"
    example.write_text("[desktop]\nhistory_enabled = false")
    public = tmp_path / "update-public.pem"
    public.write_text("-----BEGIN PUBLIC KEY-----\npublic data")
    assert scanner.scan([example, public]) == []
