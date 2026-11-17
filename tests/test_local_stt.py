from caelum.config import Config, load, save
from caelum.quality import cleanup_prompt


def test_new_settings_roundtrip_and_legacy_style(tmp_path):
    config = Config()
    config.stt.vocabulary = "Acme, Zoë\nPostgreSQL"
    config.cleanup.style = "email"
    path = tmp_path / "config.toml"
    save(config, path)
    assert load(path) == config
    path.write_text('[cleanup]\nreasoning_effort = "high"\n')
    assert load(path).cleanup.style == "thorough"
    assert len({cleanup_prompt(style) for style in ("light", "thorough", "email", "casual", "code")}) == 5


def test_retired_preview_options_are_ignored_without_execution(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[stt]\nengine = "local"\nlocal_binary = "do-not-run"\nlocal_model_path = "/old/model.bin"\n')
    config = load(path)
    assert not hasattr(config.stt, "local_binary")
    assert config.stt.local_model == ""
