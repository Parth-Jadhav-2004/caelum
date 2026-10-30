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
                app.sidebar_toggle.set_active(True)
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

                async def checked_connection(_config):
                    return "Transcription: connected (model available)"

                monkeypatch.setattr("caelum.desktop.connection_status", checked_connection)
                original_work = app.work
                app.work = lambda operation, done=None: done(operation()) if done else operation()
                app.check_connection()
                assert "connected" in app.connection_label.get_text()
                assert app.check_button.get_sensitive()
                app.work = original_work
                app.preset.set_selected(0)
                assert app.entries[("cleanup", "model")].get_text() == "openai/gpt-oss-20b"
                assert app.entries[("cleanup", "key_env")].get_text() == "GROQ_API_KEY"
                app.preset.set_selected(1)
                assert app.entries[("cleanup", "model")].get_text() == ""
                app.entries[("cleanup", "base_url")].set_text("https://custom.example/v1")
                assert app.preset.get_selected() == 2
                assert app.advanced.get_expanded()
                app.sidebar_toggle.set_active(False)
                for page in ("home", "history", "stats", "settings"):
                    app.navigate(page)
                    assert app.window.measure(Gtk.Orientation.HORIZONTAL, -1).minimum <= 640
                app.navigate("settings")
                assert app.preset.grab_focus()
                assert app.window.get_focus() is not None
                assert app.window.child_focus(Gtk.DirectionType.TAB_FORWARD)
                assert app.window.child_focus(Gtk.DirectionType.TAB_BACKWARD)
                settings = Gtk.Settings.get_default()
                original_font = settings.get_property("gtk-font-name")
                settings.set_property("gtk-font-name", "Sans 16")
                for page in ("home", "history", "stats", "settings"):
                    app.navigate(page)
                    assert app.window.measure(Gtk.Orientation.HORIZONTAL, -1).minimum <= 800
                settings.set_property("gtk-font-name", original_font)
                # X11 client-side decorations can reduce the reported client allocation.
                assert app.window.get_size_request().width == 480
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
                app.render_data(({"state": "error", "pending_audio": True}, rows, rows, summary))
                assert app.retry_button.get_visible()
                assert app.cancel_button.get_visible()
                assert app.settings_action.get_visible()
                assert app.status_label.get_text() == "Awaiting retry"
                assert not app.record_button.get_visible()
                app.render_data(({"state": "hidden"}, rows, rows, summary))
                assert not app.retry_button.get_visible()
                assert not app.start_button.get_visible()
                assert app.stop_button.get_visible()
                assert not app.cancel_button.get_visible()
                assert app.status_label.get_text() == "Ready"
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
            "Update the key",
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
