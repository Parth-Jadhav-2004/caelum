import pytest

from caelum.benchmark import percentile, wer
from caelum.config import load


@pytest.mark.parametrize(
    "content",
    [
        '[app]\nstrategy="magic"',
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
