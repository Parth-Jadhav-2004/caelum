import ctypes
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from caelum import hardware
from caelum.config import Config, load, save
from caelum.models import INDIAN_LANGUAGES, recommend

if sys.platform == "win32":
    import pywintypes
    import win32api
else:
    pytest.skip("Windows hardware probes", allow_module_level=True)


@pytest.mark.parametrize("language", INDIAN_LANGUAGES)
def test_auto_language_guidance(monkeypatch, tmp_path, language):
    def user_locale(buffer, size):
        buffer.value = f"{language}-IN"
        return len(buffer.value) + 1

    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultLocaleName", user_locale)
    monkeypatch.setattr(ctypes.windll.kernel32, "IsProcessorFeaturePresent", lambda _: 1)
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    detected = hardware.detect(Config(), tmp_path)
    assert detected.language == language
    guidance = recommend(detected)
    assert guidance["id"] is None and guidance["reason_code"] == "indian_language"
    assert INDIAN_LANGUAGES[language] in guidance["reason_text"]
    assert "Online" in guidance["reason_text"]


async def test_setup_language_preview_overrides_saved_choice(monkeypatch, tmp_path):
    from caelum.sidecar import Backend

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = tmp_path / "config.toml"
    config = Config()
    config.stt.language = "en"
    save(config, path)
    locale = Mock(return_value="pa-Guru-IN")
    monkeypatch.setattr(hardware, "_windows_locale", locale)
    backend = Backend(path)
    monkeypatch.setattr(backend, "status", AsyncMock(return_value={}))
    for params, expected in [({}, "en"), ({"language": "mr-IN"}, "mr"), ({"language": ""}, "pa")]:
        result = await backend.dispatch("models.list", params)
        assert result["hardware"]["language"] == expected
    locale.assert_called_once_with()
    assert load(path).stt.language == "en"


def test_unavailable_locale_and_gpu(monkeypatch, tmp_path):
    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultLocaleName", lambda *_: 0)
    monkeypatch.setattr(win32api, "EnumDisplayDevices", Mock(side_effect=pywintypes.error()))
    detected = hardware.detect(directory=tmp_path)
    assert detected.language == "en" and not detected.nvidia


@pytest.mark.parametrize("vendor,nvidia", [("10de", True), ("1002", False)])
def test_gpu_guidance_checks_secondary_adapter(monkeypatch, tmp_path, vendor, nvidia):
    enumerate_devices = Mock(side_effect=[
        SimpleNamespace(DeviceID=r"PCI\VEN_8086&DEV_1111"),
        SimpleNamespace(DeviceID=rf"PCI\VEN_{vendor}&DEV_2222"),
        pywintypes.error(),
    ])
    monkeypatch.setattr(win32api, "EnumDisplayDevices", enumerate_devices)
    monkeypatch.setattr(ctypes.windll.kernel32, "IsProcessorFeaturePresent", lambda _: 1)
    config = Config()
    config.stt.language = "ja"  # Multilingual model with a GPU-dependent speed hint.
    detected = hardware.detect(config, tmp_path)
    assert detected.nvidia is nvidia
    detected.mem_total_mb = 4096
    guidance = recommend(detected)
    assert guidance["id"] == "whisper-turbo"
    assert ("slower" in guidance["reason_text"]) is not nvidia
