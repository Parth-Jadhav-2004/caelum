import os

import pytest

from caelum.config import Config, load, save
from caelum.launcher import desktop_quote, entry_path, install


def test_launcher_entries_use_private_environment_launcher(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    config = tmp_path / "config with spaces.toml"
    path = install(config)
    assert path == entry_path()
    assert '"app"' in path.read_text()
    assert "scripts/run.sh" in path.read_text()
    path = install(config, autostart=True)
    assert path == entry_path(True)
    assert '"serve"' in path.read_text()
    install(config, autostart=True, enabled=False)
    assert not path.exists()


def test_desktop_quoting():
    assert desktop_quote('/a path/100% "$HOME"') == '"/a path/100%% \\"\\$HOME\\""'
    with pytest.raises(ValueError):
        desktop_quote("/path\nExec=another-command")


@pytest.mark.skipif(
    os.environ.get("CAELUM_DESKTOP_TESTS") != "1", reason="Opt-in native GTK desktop test"
)
def test_native_desktop_pages_and_themes(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib

    from caelum.desktop import run

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("caelum.desktop.microphones", lambda: [])
    monkeypatch.setattr("caelum.desktop.request", lambda _: {"state": "hidden", "paused": False})
    config_path = tmp_path / "config.toml"
    save(Config(), config_path)
    failures = []
    activations = []

    def activated(app):
        activations.append(True)

        def verify():
            try:
                for page in ("home", "history", "stats", "settings"):
                    app.navigate(page)
                    assert app.stack.get_visible_child_name() == page
                for theme in ("dark", "light"):
                    app.config.desktop.theme = theme
                    app.apply_theme()
                from gi.repository import Gdk

                app.begin_shortcut()
                app.capture_shortcut(None, Gdk.KEY_Control_L, 0, Gdk.ModifierType(0))
                app.capture_shortcut(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK)
                assert app.recording_key
                app.release_shortcut(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK)
                assert app.hotkey.get_text() == "CTRL + SUPER"
                app.begin_shortcut()
                app.capture_shortcut(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType(0))
                app.capture_shortcut(None, Gdk.KEY_Alt_L, 0, Gdk.ModifierType.SUPER_MASK)
                app.capture_shortcut(
                    None, Gdk.KEY_v, 0, Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.ALT_MASK
                )
                assert app.hotkey.get_text() == "SUPER + ALT + V"
                assert app.window.get_width() >= 820
                assert not hasattr(app, "history_switch")
                assert not hasattr(app, "theme_button")
                assert not app.history.path.exists()
                app.work = lambda operation, done: done(operation())
                app.theme_switch.set_active(True)
                assert load(config_path).desktop.theme == "dark"
                assert app.theme_switch.get_state()
                app.theme_switch.set_active(False)
                assert load(config_path).desktop.theme == "light"
                assert not app.theme_switch.get_state()
                app.history.record(
                    "desktop-test", "Saved words appear here.", {}, app.config, True, False
                )
                rows = app.history.read()
                app.render_data(({"state": "hidden"}, rows, rows, app.history.summary()))
                card = app.history_rows.get_first_child()
                assert (
                    card.get_first_child().get_next_sibling().get_text()
                    == "Saved words appear here."
                )
            except BaseException as error:
                failures.append(error)
            finally:
                app.quit()
            return False

        GLib.timeout_add(500, verify)

    run(config_path, on_activate=activated)
    assert activations, "Smoke test must activate its own application instance"
    if failures:
        raise failures[0]
