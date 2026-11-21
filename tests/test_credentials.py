import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from caelum import credentials


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(credentials, "_secret", Mock(return_value=None))


def test_fallback_replace_delete_and_environment_tombstone(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "old-environment-key")
    assert credentials.get("GROQ_API_KEY") == "old-environment-key"
    assert credentials.store("GROQ_API_KEY", "new-key") == "file"
    path = credentials._path()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert credentials.get("GROQ_API_KEY") == "new-key"
    credentials.store("GROQ_API_KEY", "replacement")
    assert credentials.get("GROQ_API_KEY") == "replacement"
    credentials.delete("GROQ_API_KEY")
    monkeypatch.setenv("GROQ_API_KEY", "old-environment-key")
    assert credentials.get("GROQ_API_KEY") is None
    assert "replacement" not in path.read_text()
    assert "key missing" in credentials.describe("GROQ_API_KEY")["description"]


def test_keyring_never_writes_secret_to_metadata(monkeypatch):
    secret = Mock(return_value=SimpleNamespace(returncode=0, stdout="test-key\n"))
    monkeypatch.setattr(credentials, "_secret", secret)
    assert credentials.store("GROQ_API_KEY", "test-key") == "keyring"
    assert "test-key" not in credentials._path().read_text()
    assert credentials.get("GROQ_API_KEY") == "test-key"
    secret.assert_called_with("lookup", "GROQ_API_KEY")
    credentials.delete("GROQ_API_KEY")
    assert credentials.get("GROQ_API_KEY") is None


def test_locked_keyring_cannot_claim_deletion(monkeypatch):
    monkeypatch.setattr(credentials, "_secret", Mock(return_value=SimpleNamespace(returncode=0)))
    credentials.store("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(credentials, "_secret", Mock(return_value=None))
    with pytest.raises(RuntimeError, match="Unlock"):
        credentials.delete("GROQ_API_KEY")
    assert json.loads(credentials._path().read_text())["GROQ_API_KEY"]["storage"] == "keyring"


def test_keyring_copy_tracked_when_replacing_during_outage(monkeypatch):
    monkeypatch.setattr(credentials, "_secret", Mock(return_value=SimpleNamespace(returncode=0)))
    credentials.store("GROQ_API_KEY", "first")
    monkeypatch.setattr(credentials, "_secret", Mock(return_value=None))
    credentials.store("GROQ_API_KEY", "second")
    assert credentials.get("GROQ_API_KEY") == "second"
    with pytest.raises(RuntimeError, match="Unlock"):
        credentials.delete("GROQ_API_KEY")


def test_insecure_file_is_rejected():
    credentials.store("GROQ_API_KEY", "test-key")
    os.chmod(credentials._path(), 0o644)
    with pytest.raises(RuntimeError, match="mode 600"):
        credentials.get("GROQ_API_KEY")


@pytest.mark.parametrize("value", ["", "key\nsecret", "key with spaces"])
def test_invalid_key_not_saved(value):
    with pytest.raises(ValueError):
        credentials.store("GROQ_API_KEY", value)
    assert not credentials._path().exists()


async def test_saved_key_is_used_by_provider_without_environment(monkeypatch):
    import httpx
    from caelum.config import Config
    from caelum.providers import Providers

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    credentials.store("GROQ_API_KEY", "managed-test-key")

    def respond(request):
        assert request.headers["Authorization"] == "Bearer managed-test-key"
        return httpx.Response(200, json={"text": "hello"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (await Providers(Config(), client).stt(b"\0" * 100)).text == "hello"


@pytest.mark.parametrize("storage", ["file", "keyring"])
def test_describes_storage_without_secrets(storage, monkeypatch):
    if storage == "keyring":
        monkeypatch.setattr(credentials, "_secret", Mock(return_value=SimpleNamespace(returncode=0)))
    credentials.store("GROQ_API_KEY", "private-test-key")
    description = credentials.describe("GROQ_API_KEY")
    assert description["storage"] == storage
    assert "private-test-key" not in json.dumps(description)


def test_windows_upgrades_old_file_keys_without_losing_vault_copy_or_tombstone(monkeypatch):
    monkeypatch.setattr(credentials, "_WINDOWS", False)
    credentials.store("ONE", "synthetic-first")
    data = credentials._read()
    data["ONE"]["keyring_copy"] = True
    data["TWO"] = {"storage": "file", "value": "synthetic-second"}
    data["REMOVED"] = {"storage": "deleted"}
    credentials._write(data)
    monkeypatch.setenv("REMOVED", "synthetic-environment")
    monkeypatch.setattr(credentials, "_WINDOWS", True)
    blobs = {b"synthetic-first": b"blob1", b"synthetic-second": b"blob2"}
    crypt = SimpleNamespace(
        CryptProtectData=lambda plain, **kw: blobs[plain],
        CryptUnprotectData=lambda blob, **kw: ("", next(k for k, v in blobs.items() if v == blob)),
    )
    monkeypatch.setitem(sys.modules, "pywintypes", SimpleNamespace(error=OSError))
    monkeypatch.setitem(sys.modules, "win32crypt", crypt)
    assert credentials.describe("ONE")["storage"] == "dpapi"
    assert "synthetic-" not in credentials._path().read_text()
    assert credentials.get("ONE") == "synthetic-first"
    assert credentials.get("TWO") == "synthetic-second"
    assert credentials.get("REMOVED") is None
    with pytest.raises(RuntimeError, match="Credential Manager"):
        credentials.delete("ONE")
    credentials.delete("TWO")
    assert credentials.get("TWO") is None


def test_windows_fails_closed_without_data_protection(monkeypatch):
    monkeypatch.setattr(credentials, "_WINDOWS", False)
    credentials.store("OLD", "synthetic-legacy")
    original = credentials._path().read_bytes()
    monkeypatch.setattr(credentials, "_WINDOWS", True)
    monkeypatch.setitem(sys.modules, "win32crypt", None)
    with pytest.raises(RuntimeError, match="data protection"):
        credentials.store("NEW", "synthetic-new")
    with pytest.raises(RuntimeError, match="still unencrypted"):
        credentials.get("OLD")
    assert credentials.describe("OLD")["storage"] == "unavailable"
    assert credentials._path().read_bytes() == original
    assert not list(credentials._path().parent.glob(".credentials-*"))


def test_windows_unreadable_dpapi_key_does_not_fall_back_to_environment(monkeypatch):
    credentials._write({"ONE": {"storage": "dpapi", "value": "not-base64!"}})
    monkeypatch.setattr(credentials, "_WINDOWS", True)
    monkeypatch.setitem(sys.modules, "pywintypes", SimpleNamespace(error=OSError))
    monkeypatch.setitem(sys.modules, "win32crypt", SimpleNamespace())
    monkeypatch.setenv("ONE", "synthetic-env")
    with pytest.raises(RuntimeError, match="Cannot unlock"):
        credentials.get("ONE")
