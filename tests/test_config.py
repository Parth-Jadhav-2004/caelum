import pytest
from caelum.benchmark import percentile, wer
from caelum.config import load


@pytest.mark.parametrize(
    "content",
    [
        '[app]\nstrategy="magic"',
        '[app]\nrecording_mode="magic"',
        "[stt]\nconcurrency=50",
        "[stt]\noverlap_seconds=10",
        '[cleanup]\nbase_url="http://untrusted.example/api"',
        '[app]\nhotkey="V; rm"',
        '[app]\nmax_recording_seconds="120"',
        "[app]\nunknown=true",
        "[app]\nreduced_motion=1",
        '[app]\nhotkey="CTRL + CTRL"',
        '[app]\nhotkey="SUPER + CTRL + SUPER"',
    ],
)
def test_reject_unsafe_or_invalid_config(tmp_path, content):
    path = tmp_path / "config.toml"
    path.write_text(content)
    with pytest.raises(ValueError):
        load(path)


def test_metrics_math():
    assert wer("very very good", "very good") == pytest.approx(1 / 3)
    assert percentile([1, 2, 3, 4, 5], 95) == pytest.approx(4.8)
    assert percentile([], 95) is None


def test_modifier_only_shortcut(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[app]\nhotkey="CTRL + SUPER"')
    assert load(path).app.hotkey == "CTRL + SUPER"


def test_recording_defaults_and_toggle_roundtrip(tmp_path):
    from caelum.config import Config, save

    config = Config()
    assert config.app.max_recording_seconds == 180
    assert config.app.recording_mode == "hold"
    config.app.recording_mode = "toggle"
    path = tmp_path / "config.toml"
    save(config, path)
    assert load(path).app.recording_mode == "toggle"


def test_legacy_appearance_loads_with_default_palette(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[desktop]\ntheme="light"\n[app]\nhotkey="CTRL + SUPER"\n')
    config = load(path)
    assert config.desktop.color_theme == "t3-code"
    assert config.desktop.theme == "light"
    assert config.app.hotkey == "CTRL + SUPER"


@pytest.mark.parametrize(
    "palette", ["t3-code", "t3-chat", "grove", "ocean", "ember", "iris", "caelum"]
)
@pytest.mark.parametrize("appearance", ["system", "dark", "light"])
def test_palette_roundtrip_preserves_appearance_and_settings(tmp_path, palette, appearance):
    from caelum.config import Config, save

    config = Config()
    config.desktop.color_theme = palette
    config.desktop.theme = appearance
    config.app.hotkey = "CTRL + SUPER"
    path = tmp_path / "config.toml"
    save(config, path)
    restored = load(path)
    assert restored == config


@pytest.mark.parametrize("value", ['"unknown"', '""', "42", "true"])
def test_invalid_palette_rejected(tmp_path, value):
    path = tmp_path / "config.toml"
    path.write_text(f"[desktop]\ncolor_theme={value}\n")
    with pytest.raises(ValueError):
        load(path)
