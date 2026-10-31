"""GTK interaction coverage for the compact Overview presentation."""

import os

import pytest

from caelum.config import Config, save


@pytest.mark.skipif(os.environ.get("CAELUM_DESKTOP_TESTS") != "1", reason="Opt-in GTK UI test")
def test_overview_controls_data_copy_and_themes(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    from caelum.desktop import run
    from caelum.onboarding import Progress

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("caelum.desktop.microphones", lambda: [])
    monkeypatch.setattr("caelum.desktop.request", lambda _: {"state": "hidden"})
    config = Config()
    config.app.hotkey = "ALT + CTRL + D"
    config.app.backend = "hyprland"
    path = tmp_path / "config.toml"
    save(config, path)
    Progress(4, True).save(path)
    failures = []

    def activated(app):
        def verify():
            try:
                calls = []
                app.start_service = lambda: calls.append("start")
                app.stop_service = lambda: calls.append("stop")
                app.work = lambda operation, done=None: done(operation()) if done else operation()

                def request(action):
                    calls.append(action)
                    return {"state": "hidden"}

                monkeypatch.setattr("caelum.desktop.request", request)
                app.history.record(
                    "one", "Full transcript survives the compact row.", {}, config, False, False
                )
                rows = app.history.read()
                summary = app.history.summary()
                summary.update(today_words=1234, sessions=7, duration_ms=156000)
                app.render_data((None, rows, rows, summary))
                assert [label.get_text() for label in app.home_metrics] == ["1234", "7", "2.6"]
                assert app.shortcut_label.get_text() == "Hold Alt + Ctrl + D to dictate"
                assert app.status_label.get_text() == "Stopped"
                assert not app.recovery.get_visible()
                app.status_button.emit("clicked")
                assert calls == ["start"]

                app.render_data(({"state": "recording"}, rows, rows, summary))
                assert app.status_label.get_text() == "Listening"
                app.status_button.emit("clicked")
                assert calls[-1] == "stop"
                app.pause_button.emit("clicked")
                assert "pause" in calls
                app.render_data(({"state": "hidden", "paused": True}, rows, rows, summary))
                assert app.status_label.get_text() == "Paused"
                app.pause_button.emit("clicked")
                assert "resume" in calls

                app.render_data(({"state": "error", "pending_audio": True}, rows, rows, summary))
                assert app.retry_button.get_visible() and app.cancel_button.get_visible()
                app.retry_button.emit("clicked")
                app.cancel_button.emit("clicked")
                assert "retry" in calls and "cancel" in calls

                row = app.recent.get_first_child()
                text = row.get_first_child().get_next_sibling()
                assert text.get_text() == rows[0]["final_transcript"]
                assert not text.get_wrap()
                copied = []
                app.copy_text = lambda text, announce=True: copied.append((text, announce))
                copy = row.get_last_child()
                copy.emit("clicked")
                assert copied == [(rows[0]["final_transcript"], False)]
                assert copy.get_child().icon_name == "check"

                settings = Gtk.Settings.get_default()
                if settings.find_property("gtk-interface-color-scheme"):
                    original = settings.get_property("gtk-interface-color-scheme")
                    settings.set_property(
                        "gtk-interface-color-scheme", Gtk.InterfaceColorScheme.LIGHT
                    )
                    assert app.hotkey_color == "#1B1B1A"
                    settings.set_property(
                        "gtk-interface-color-scheme", Gtk.InterfaceColorScheme.DARK
                    )
                    assert app.hotkey_color == "#F2F2F3"
                    settings.set_property("gtk-interface-color-scheme", original)
                app.render_data((None, [], [], summary))
                assert (
                    app.recent.get_first_child().get_text()
                    == "Nothing yet. Hold Alt + Ctrl + D and start talking."
                )
                assert app.window.get_size_request().width == 900
                for name in ("home", "history", "settings", "stats"):
                    app.navigate(name)
                    assert app.stack.get_visible_child_name() == name
            except BaseException as error:
                failures.append(error)
            finally:
                app.quit()
            return False

        GLib.timeout_add(350, verify)

    run(path, on_activate=activated)
    if failures:
        raise failures[0]
