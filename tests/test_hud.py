"""Overlay presentation can be checked without mapping a Wayland surface."""
from caelum.hud import ERRORS, LABELS, STATES


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
