import importlib.util
import os
import subprocess
import sys
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


def test_repository_scan_handles_container_ownership_and_other_working_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(scanner.__file__).resolve())],
        cwd=tmp_path,
        env={**os.environ, "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Privacy scan passed" in result.stdout
