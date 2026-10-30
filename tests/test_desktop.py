import os

import pytest

from caelum.config import Config, save
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
def test_native_desktop_pages_and_sidebar(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    from caelum.desktop import run

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("caelum.desktop.microphones", lambda: [])
    monkeypatch.setattr("caelum.desktop.request", lambda _: {"state": "hidden", "paused": False})
    config_path = tmp_path / "config.toml"
    legacy = Config()
    legacy.desktop.theme = "light"
    save(legacy, config_path)
    failures = []
    activations = []

    def activated(app):
        activations.append(True)

        def verify():
            try:
                for page in ("home", "history", "stats", "settings"):
                    app.navigate(page)
                    assert app.stack.get_visible_child_name() == page
                    assert app.window.measure(Gtk.Orientation.HORIZONTAL, -1).minimum <= 820
                assert app.config.desktop.theme == "dark"
                assert app.brand.get_text() == "Caelum"
                assert app.brand.get_xalign() == 0
                assert app.sidebar_toggle.get_active()
                for _ in range(2):
                    app.sidebar_toggle.set_active(False)
                    assert app.navigation.get_size_request().width == 88
                    assert all(not label.get_visible() for label in app.nav_labels)
                    assert not app.sidebar_footer.get_visible()
                    app.nav_buttons["history"].emit("clicked")
                    assert app.stack.get_visible_child_name() == "history"
                    assert app.nav_buttons["history"].has_css_class("selected")
                    app.sidebar_toggle.set_active(True)
                    assert app.navigation.get_size_request().width == 208
                    assert all(label.get_visible() for label in app.nav_labels)
                    assert app.sidebar_footer.get_visible()
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
                # X11 client-side decorations can reduce the reported client allocation.
                assert app.window.get_size_request().width == 820
                assert not hasattr(app, "history_switch")
                assert not hasattr(app, "theme_button")
                assert not app.history.path.exists()
                assert not hasattr(app, "theme_switch")
                app.history.record(
                    "desktop-test", "Saved words appear here.", {}, app.config, True, False
                )
                rows = app.history.read()
                summary = app.history.summary()
                app.render_data((None, rows, rows, summary))
                assert app.start_button.get_visible()
                assert not app.stop_button.get_visible()
                app.render_data(({"state": "hidden"}, rows, rows, summary))
                assert not app.start_button.get_visible()
                assert app.stop_button.get_visible()
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


def test_packaged_launcher_does_not_require_source_checkout(tmp_path, monkeypatch):
    from caelum import launcher

    monkeypatch.setattr(launcher, "__file__", "/opt/caelum/lib/caelum/launcher.py")
    monkeypatch.setattr(launcher.shutil, "which", lambda _: "/usr/bin/caelum")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = launcher.install(tmp_path / "config.toml")
    assert 'Exec="/usr/bin/caelum" "--config"' in result.read_text()
