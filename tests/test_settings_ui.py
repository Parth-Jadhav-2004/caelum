"""Native Settings interaction and persistence regression check (no provider or mic access)."""
import os

import pytest


@pytest.mark.skipif(
    os.environ.get("CAELUM_DESKTOP_TESTS") != "1", reason="Opt-in native GTK desktop test"
)
def test_sentence_settings_autosave_and_advanced(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk

    from caelum import desktop
    from caelum.config import Config, load, save
    from caelum.onboarding import Progress

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(desktop, "microphones", lambda: [("USB mic", "USB mic")])
    requests = []
    monkeypatch.setattr(
        desktop, "request",
        lambda action: requests.append(action) or {"state": "hidden", "paused": False},
    )
    path = tmp_path / "settings.toml"
    save(Config(), path)
    Progress(4, True).save(path)
    failures = []
    writes = []

    def saving(config, destination):
        writes.append(config.desktop.retention_days)
        save(config, destination)

    monkeypatch.setattr(desktop, "save", saving)

    def activated(app):
        def edit():
            try:
                app.navigate("settings")
                assert not hasattr(app, "save_button")
                assert app.record_key.has_css_class("token")
                app.begin_shortcut()
                app.capture_shortcut(None, Gdk.KEY_Control_L, 0, Gdk.ModifierType(0))
                app.capture_shortcut(None, Gdk.KEY_k, 0, Gdk.ModifierType.CONTROL_MASK)
                assert app.hotkey.get_text() == Config().app.hotkey
                app.capture_shortcut(None, Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
                assert app.hotkey.get_text() == Config().app.hotkey
                app.begin_shortcut()
                app.capture_shortcut(None, Gdk.KEY_Control_L, 0, Gdk.ModifierType(0))
                app.capture_shortcut(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK)
                app.release_shortcut(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK)
                assert app.hotkey.get_text() == "CTRL + SUPER"
                app.preset.set_selected(0)
                assert app.entries[("cleanup", "reasoning_effort")].get_text() == "minimal"
                app.tidy.set_selected(2)
                assert app.entries[("cleanup", "reasoning_effort")].get_text() == "high"
                app.tidy.set_selected(0)
                assert not app.entries[("cleanup", "model")].get_text()
                app.tidy.set_selected(1)
                assert app.entries[("cleanup", "model")].get_text() == "openai/gpt-oss-20b"
                app.mic.set_selected(1)
                app.retention.set_value(45)
                app.retention.set_value(46)
                app.update_automatic.set_active(False)
                app.navigate("advanced")
                assert app.stack.get_visible_child_name() == "advanced"
                assert app.nav_buttons["settings"].has_css_class("selected")
                app.entries[("stt", "language")].set_text("en")
                assert writes == []  # Changes coalesce during the 400ms debounce.
                assert app.window.measure(Gtk.Orientation.HORIZONTAL, -1).minimum <= 640
            except BaseException as error:
                failures.append(error)
                app.quit()
                return False
            GLib.timeout_add(1000, verify)
            return False

        def verify():
            try:
                saved = load(path)
                assert writes == [46]
                assert saved.app.hotkey == "CTRL + SUPER"
                assert saved.app.microphone == "USB mic"
                assert saved.desktop.retention_days == 46
                assert saved.stt.language == "en"
                assert not saved.desktop.check_updates
                assert "reload" in requests
                assert app.save_status.get_text() == "Saved"
                app.show_provider_status("Transcription: Invalid provider key")
                assert app.provider_status_dot.has_css_class("error")
                app.show_provider_status("Transcription: key missing")
                assert app.key_setup.get_visible()
                app.show_provider_status("Transcription: connected (model available)")
                assert app.connection_label.get_text() == "Connected"
                assert not app.key_setup.get_visible()
                app.retention.set_value(47)  # Closing flushes the pending debounce.
            except BaseException as error:
                failures.append(error)
            finally:
                app.quit()
            return False

        GLib.timeout_add(200, edit)

    desktop.run(path, on_activate=activated)
    if failures:
        raise failures[0]
    assert load(path).desktop.retention_days == 47
