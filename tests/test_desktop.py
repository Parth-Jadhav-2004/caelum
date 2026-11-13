from pathlib import Path
from xml.etree import ElementTree

import pytest
from caelum.config import Config
from caelum.launcher import desktop_quote, entry_path, install


def test_launcher_entries_use_private_environment_launcher(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    config = tmp_path / "config with spaces.toml"
    path = install(config)
    assert path == entry_path()
    assert '"app"' in path.read_text()
    assert "scripts/run.sh" in path.read_text()
    from caelum import launcher

    icon = Path(launcher.__file__).resolve().parent / "icons/hicolor/scalable/apps/caelum.svg"
    assert icon.is_file()
    assert f"Icon={icon}\n" in path.read_text()
    path = install(config, autostart=True)
    assert path == entry_path(True)
    assert '"serve"' in path.read_text()
    install(config, autostart=True, enabled=False)
    assert not path.exists()


def test_desktop_quoting():
    assert desktop_quote('/a path/100% "$HOME"') == '"/a path/100%% \\"\\$HOME\\""'
    with pytest.raises(ValueError):
        desktop_quote("/path\nExec=another-command")


def test_app_icons_preserve_product_page_waveform():
    root = Path(__file__).resolve().parents[1]
    website = ElementTree.parse(root / "website/mark.svg").getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    waveform = website.find("svg:path", namespace)
    for name in ("caelum.svg", "caelum-symbolic.svg"):
        icon = ElementTree.parse(
            root / "python/caelum/icons/hicolor/scalable/apps" / name
        ).getroot()
        assert icon.attrib["viewBox"] == website.attrib["viewBox"]
        path = icon.find("svg:path", namespace)
        for attribute in ("d", "stroke-width", "stroke-linecap"):
            assert path.attrib[attribute] == waveform.attrib[attribute]






def test_native_package_version_does_not_require_python_distribution_metadata(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    from caelum.desktop import display_version

    monkeypatch.setattr("caelum.updates.installed", lambda: {"version": "0.3.1"})
    monkeypatch.setattr(
        "importlib.metadata.version", lambda _: (_ for _ in ()).throw(PackageNotFoundError())
    )
    assert display_version() == "0.3.1"


def test_packaged_launcher_does_not_require_source_checkout(tmp_path, monkeypatch):
    from caelum import launcher

    monkeypatch.setattr(launcher, "__file__", "/opt/caelum/lib/caelum/launcher.py")
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "/usr/bin/caelum")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = launcher.install(tmp_path / "config.toml")
    assert 'Exec="/usr/bin/caelum" "--config"' in result.read_text()
    assert "Icon=/opt/caelum/lib/caelum/icons/hicolor/scalable/apps/caelum.svg\n" in result.read_text()


def test_provider_presets_preserve_other_preferences():
    from caelum.desktop import apply_provider_preset, provider_preset

    config = Config()
    config.app.hotkey = "CTRL + ALT + D"
    assert provider_preset(config) == 1
    groq = apply_provider_preset(config, 0)
    assert provider_preset(groq) == 0
    assert groq.cleanup.key_env == groq.stt.key_env == "GROQ_API_KEY"
    assert groq.cleanup.reasoning_effort == "low"
    assert groq.app.hotkey == config.app.hotkey
    assert config.cleanup.model == ""
    raw = apply_provider_preset(groq, 1)
    assert not raw.cleanup.model
    groq.cleanup.base_url = "https://custom.example/v1"
    assert provider_preset(groq) == 2
    assert apply_provider_preset(groq, 2) == groq


@pytest.mark.parametrize(
    "status,title,detail",
    [
        (None, "Stopped", "Start"),
        ({"state": "hidden"}, "Ready", "begin"),
        ({"state": "hidden", "paused": True}, "Paused", "Resume"),
        ({"state": "recording"}, "Recording", "Release"),
        ({"state": "refining"}, "Processing", "Refining"),
        ({"state": "processing"}, "Processing", "Transcribing"),
        ({"state": "unrefined"}, "Done · unrefined", "Raw transcription"),
        (
            {"state": "error", "pending_audio": True, "error_kind": "invalid_key"},
            "Awaiting retry",
            "Manage keys",
        ),
        ({"state": "error", "error_kind": "microphone"}, "Microphone unavailable", "Settings"),
        ({"state": "saved", "metrics": [{"cleanup_refined": False}]}, "Saved", "Raw transcription"),
        ({"state": "copied"}, "Copied", "Paste manually"),
    ],
)
def test_service_status_copy(status, title, detail):
    from caelum.desktop import service_presentation

    actual_title, actual_detail = service_presentation(status)
    assert actual_title == title
    assert detail in actual_detail


@pytest.mark.parametrize(
    "result,expected",
    [
        ("ok", "connected"),
        ("missing", "key missing"),
        ("invalid", "Invalid provider key"),
        ("offline", "unreachable"),
        ("model", "model unavailable"),
    ],
)
async def test_connection_status(result, expected, monkeypatch):
    from unittest.mock import AsyncMock

    from caelum.desktop import connection_status
    from caelum.providers import ProviderError

    config = Config()
    models = AsyncMock(return_value=[config.stt.model] if result == "ok" else [])
    if result in ("missing", "invalid", "offline"):
        models.side_effect = ProviderError(
            {
                "missing": "Missing credential",
                "invalid": "Invalid provider key",
                "offline": "Provider unreachable",
            }[result],
            "missing_key" if result == "missing" else result,
        )
    monkeypatch.setattr("caelum.providers.Providers.models", models)
    text = await connection_status(config)
    assert expected in text
    assert "Refinement: off" in text


async def test_connection_check_validates_url_before_sending_key(monkeypatch):
    from unittest.mock import AsyncMock

    from caelum.desktop import connection_status

    config = Config()
    config.stt.base_url = "http://insecure.example/v1"
    models = AsyncMock()
    monkeypatch.setattr("caelum.providers.Providers.models", models)
    assert "HTTPS" in await connection_status(config)
    models.assert_not_awaited()
