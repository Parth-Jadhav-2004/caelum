"""Overlay presentation can be checked without mapping a Wayland surface."""
import pytest
from caelum.hud import ERRORS, LABELS, STATES, PillFade


def test_overlay_states_use_short_plain_labels():
    assert {"hidden", "recording", "processing", "success", "error"} <= STATES
    assert LABELS["processing"] == LABELS["refining"] == "Transcribing"
    assert LABELS["success"] == LABELS["unrefined"] == "Inserted"
    assert LABELS["copied"] == "Copied: paste with Ctrl V"
    assert all(len(reason.split()) == 2 for reason in ERRORS.values())


def test_pill_hides_at_rest_and_exposes_only_state_actions():
    from caelum.hud import presentation

    assert presentation("hidden")["visible"] is False
    for state in ("listening", "recording"):
        layout = presentation(state)
        assert layout["width"] == 140
        assert layout["actions"] == ("cancel", "stop")
        assert layout["dwell"] is None
    assert presentation("processing")["actions"] == ()
    assert presentation("error")["actions"] == ("retry", "cancel")
    for state in ("success", "unrefined"):
        assert presentation(state)["dwell"] == 0.6
        assert presentation(state)["actions"] == ()


def test_fade_finishes_in_160ms_and_repeated_updates_do_not_restart_it():
    fade = PillFade()
    assert fade.opacity(0) == 0
    fade.move(True, 1)
    assert fade.opacity(1.08) == pytest.approx(0.5)
    fade.move(True, 1.08)
    assert fade.opacity(1.16) == pytest.approx(1)
    fade.move(False, 2)
    assert fade.opacity(2.08) == pytest.approx(0.5)
    fade.move(False, 2.08)
    assert fade.opacity(2.17) == 0


def test_fade_reverses_from_current_opacity_and_reduced_motion_is_instant():
    fade = PillFade()
    fade.move(True, 1)
    fade.move(False, 1.08)
    assert fade.opacity(1.08) == pytest.approx(0.5)
    assert fade.opacity(1.16) == pytest.approx(0.25)
    fade.move(True, 1.16)
    assert fade.opacity(1.16) == pytest.approx(0.25)
    assert fade.opacity(1.33) == 1
    reduced = PillFade(reduced_motion=True)
    reduced.move(True, 1)
    assert reduced.opacity(1) == 1
    reduced.move(False, 1)
    assert reduced.opacity(1) == 0
