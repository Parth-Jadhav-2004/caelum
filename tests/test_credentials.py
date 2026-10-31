import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from caelum import credentials


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
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
    assert "key missing" in credentials.describe("GROQ_API_KEY")


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
