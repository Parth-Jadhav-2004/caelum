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
def test_native_update_consent_queue_discard_and_restart(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    from caelum import updates
    from caelum.config import load
    from caelum.desktop import run
    from caelum.onboarding import Progress

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("caelum.desktop.microphones", lambda: [])
    monkeypatch.setattr("caelum.desktop.request", lambda _: {"state": "hidden", "paused": False})
    monkeypatch.setattr(updates, "installed", lambda: {"version": "0.2.0"})
    update = {"version": "0.3.0"}
    monkeypatch.setattr(updates, "check", lambda: update)
    path = tmp_path / "config.toml"
    save(Config(), path)
    Progress(4, True).save(path)
    failures = []
    downloads = []
    restarts = []

    def download(value):
        downloads.append(value)
        (updates.cache_dir() / "pending").mkdir(parents=True)
        return value["version"]

    monkeypatch.setattr(updates, "stage", download)
    monkeypatch.setattr("caelum.desktop.install_queued_update", lambda: False)
    monkeypatch.setattr("caelum.desktop.os.execv", lambda executable, args: restarts.append(args))

    def activated(app):
        def verify():
            try:
                app.work = lambda operation, done=None: done(operation()) if done else operation()
                app.navigate("settings")
                app.check_updates()
                assert app.update_download.get_visible()
                assert app.update_status.get_text() == "Update available"
                app.prompt_update()
                dialog = next(
                    window
                    for window in Gtk.Window.list_toplevels()
                    if isinstance(window, Gtk.MessageDialog)
                )
                dialog.response(Gtk.ResponseType.CANCEL)
                assert downloads == []
                assert app.update_download.get_sensitive()
                app.prompt_update()
                dialog = next(
                    window
                    for window in Gtk.Window.list_toplevels()
                    if isinstance(window, Gtk.MessageDialog)
                )
                dialog.response(Gtk.ResponseType.ACCEPT)
                assert downloads == [update]
                assert len(restarts) == 1
                assert not app.update_check.get_sensitive()
                assert app.update_discard.get_sensitive()
                assert restarts[0][-3:] == ["--config", str(path), "app"]
                app.restarting_update = False
                app.stack.set_sensitive(True)

                def cancelled_install():
                    raise RuntimeError("Authorization cancelled; retry the queued update.")

                monkeypatch.setattr("caelum.desktop.install_queued_update", cancelled_install)
                app.begin_updates()
                assert len(restarts) == 1
                assert "Authorization cancelled" in app.update_status.get_text()
                assert app.stack.get_sensitive() and app.theme_button.get_sensitive()
                assert app.update_download.get_sensitive() and app.update_download.get_visible()
                assert (updates.cache_dir() / "pending").is_dir()
                monkeypatch.setattr("caelum.desktop.install_queued_update", lambda: False)
                app.prompt_update()  # A queued update retries directly; no second download.
                assert len(restarts) == 2 and downloads == [update]
                app.restarting_update = False
                app.stack.set_sensitive(True)
                app.discard_update()
                assert not (updates.cache_dir() / "pending").exists()
                assert app.update_check.get_sensitive()

                def offline():
                    raise RuntimeError("Offline, try again")

                monkeypatch.setattr(updates, "check", offline)
                app.check_updates()
                assert "Offline" in app.update_status.get_text()
                assert app.update_check.get_sensitive()
                assert not app.update_busy
                app.update_automatic.set_active(False)
                app.history_enabled.set_active(False)
                app.save_settings()
                assert not load(path).desktop.history_enabled
                assert not load(path).desktop.check_updates
                monkeypatch.setattr(updates, "check", lambda: pytest.fail("checks disabled"))
                app.begin_updates()
            except BaseException as error:
                failures.append(error)
            finally:
                for window in Gtk.Window.list_toplevels():
                    if isinstance(window, Gtk.MessageDialog):
                        window.destroy()
                app.quit()
            return False

        GLib.timeout_add(300, verify)

    run(path, on_activate=activated)
    if failures:
        raise failures[0]


@pytest.mark.skipif(
    os.environ.get("CAELUM_DESKTOP_TESTS") != "1", reason="Opt-in native GTK desktop test"
)
def test_native_desktop_pages_and_rail(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    from caelum.desktop import run
    from caelum.onboarding import Progress

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("caelum.desktop.microphones", lambda: [])
    monkeypatch.setattr("caelum.desktop.request", lambda _: {"state": "hidden", "paused": False})
    path = tmp_path / "config.toml"
    save(Config(), path)
    Progress(4, True).save(path)
    failures = []

    def activated(app):
        def verify():
            try:
                for page in ("home", "history", "stats", "settings", "advanced"):
                    app.navigate(page)
                    assert app.stack.get_visible_child_name() == page
                    maximum = 1100 if page == "home" else 640
                    assert app.window.measure(Gtk.Orientation.HORIZONTAL, -1).minimum <= maximum
                assert not hasattr(app, "sidebar_toggle")
                assert set(app.nav_buttons) == {"home", "history", "settings"}
                assert app.nav_buttons["settings"].has_css_class("selected")
                app.nav_buttons["history"].emit("clicked")
                assert app.stack.get_visible_child_name() == "history"
                app.navigate("settings")
                assert app.record_key.grab_focus()
                assert app.window.child_focus(Gtk.DirectionType.TAB_FORWARD)
                assert app.window.child_focus(Gtk.DirectionType.TAB_BACKWARD)
                assert not app.history.path.exists()
            except BaseException as error:
                failures.append(error)
            finally:
                app.quit()
            return False

        GLib.timeout_add(500, verify)

    run(path, on_activate=activated)
    if failures:
        raise failures[0]


def test_native_package_version_does_not_require_python_distribution_metadata(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    from caelum.desktop import display_version

    monkeypatch.setattr("caelum.updates.installed", lambda: {"version": "0.3.1"})
    monkeypatch.setattr(
        "importlib.metadata.version", lambda _: (_ for _ in ()).throw(PackageNotFoundError())
    )
    assert display_version() == "0.3.1"


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
            "Manage keys",
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


@pytest.mark.skipif(
    os.environ.get("CAELUM_DESKTOP_TESTS") != "1", reason="Opt-in native GTK setup test"
)
@pytest.mark.parametrize("contributor", [False, True])
def test_setup_flow_requires_validation_mic_and_practice(tmp_path, monkeypatch, contributor):
    import gi

    gi.require_version("Gtk", "4.0")
    from unittest.mock import AsyncMock

    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk

    from caelum.desktop import run
    from caelum.onboarding import Progress
    from caelum.onboarding_ui import show

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("caelum.desktop.microphones", lambda: [("USB mic", "USB mic")])
    monkeypatch.setattr("caelum.desktop.request", lambda _: {"state": "hidden", "paused": False})
    validate = AsyncMock()
    monkeypatch.setattr("caelum.onboarding_ui.validate_providers", validate)
    monkeypatch.setattr(
        "caelum.onboarding_ui.check_shortcut", AsyncMock(return_value="Shortcut available")
    )
    monkeypatch.setattr("caelum.onboarding_ui.record_sample", lambda *_args: b"speech")
    monkeypatch.setattr(
        "caelum.onboarding_ui.practice", AsyncMock(return_value=("Practice words.", True))
    )
    stored = []
    monkeypatch.setattr("caelum.credentials.get", lambda name: "test-key" if stored else None)
    monkeypatch.setattr(
        "caelum.credentials.store", lambda name, value: stored.append((name, value)) or "keyring"
    )
    path = tmp_path / "config.toml"
    config = Config()
    if contributor:
        config.cleanup.model = "meta/muse-spark-contributor"
    save(config, path)
    failures = []

    def activated(app):
        def verify():
            try:
                app.work = lambda operation, done=None: done(operation()) if done else operation()
                assert app.setup_window is not None  # first launch opens setup automatically
                setup = show(app)
                assert isinstance(setup, Gtk.Box)
                assert not isinstance(setup, Gtk.Window)
                assert setup.get_root() is app.window
                assert app.stack.get_visible_child_name() == "setup"
                assert all(not button.get_active() for button in app.nav_buttons.values())
                assert sum(window.get_application() is app
                           for window in Gtk.Window.list_toplevels()) == 1
                # Hidden steps must not push navigation below the viewport.
                allocated, bounds = setup.next.compute_bounds(setup)
                assert allocated
                assert bounds.get_y() + bounds.get_height() <= setup.get_height()
                assert not setup.next.get_sensitive()
                setup.advance()
                assert setup.stage == 1
                setup.consent.set_active(True)
                setup.key_entry.set_text("test-key")
                if contributor:
                    setup.advance()
                    assert setup.stage == 1
                    validate.assert_not_awaited()
                    assert "training" in setup.notice.get_text()
                    setup.contributor.set_active(True)
                validate.side_effect = RuntimeError("Invalid provider key")
                setup.advance()
                assert setup.stage == 1 and not setup.validated
                assert "Invalid provider key" in setup.notice.get_text()
                validate.side_effect = None
                setup.advance()
                assert validate.await_count == 2
                from caelum.config import load
                from caelum.providers import contributor_scope

                saved = load(path)
                assert saved.cleanup.contributor_consent == (
                    contributor_scope(saved.cleanup) if contributor else ""
                )
                assert setup.stage == 2
                setup.advance()
                assert setup.stage == 2 and setup.tested
                assert stored == [("GROQ_API_KEY", "test-key")]
                assert not setup.key_entry.get_text()
                setup.stage = 2
                setup.mic.set_selected(1)
                setup.test_mic()
                assert setup.tested
                setup.advance()
                assert setup.stage == 3
                old_hotkey = setup.hotkey.get_text()
                setup.begin_shortcut()
                setup.capture_shortcut(None, Gdk.KEY_Control_L, 0, Gdk.ModifierType(0))
                setup.capture_shortcut(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK)
                assert setup.hotkey.get_text() == old_hotkey
                setup.release_shortcut(None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK)
                assert setup.hotkey.get_text() == "CTRL + SUPER"
                setup.advance()
                assert setup.stage == 4
                assert not setup.next.get_sensitive()
                setup.run_practice()
                assert not setup.succeeded  # explicit upload consent is required
                setup.upload.set_active(True)
                assert setup.practice_pressed(
                    None, Gdk.KEY_Super_L, 0, Gdk.ModifierType.CONTROL_MASK
                )
                assert setup.succeeded and setup.next.get_sensitive()
                assert not Progress.load(path).complete
                assert not app.history.path.exists()
                setup.advance()
                assert Progress.load(path).complete
                assert app.config.app.microphone == "USB mic"
                assert app.setup_window is None
                assert app.stack.get_child_by_name("setup") is None
                assert app.stack.get_visible_child_name() == "home"
                setup = show(app)
                assert show(app) is setup  # Reopening reuses the embedded page.
                setup.preset.set_selected(0)
                setup.stage = 3
                setup.render()
                setup.resume_later()
                assert Progress.load(path).stage == 3
                setup = show(app)
                assert setup.stage == 1  # resume validates provider access again
                assert not setup.validated and not setup.succeeded
                assert setup.preset.get_selected() == 0  # draft selection survives resume
                setup.key_entry.set_text("discard-this-draft")
                app.navigate("settings")  # Leaving the page cancels work and clears secrets.
                assert setup.closed and setup.cancelled.is_set()
                assert setup.key_entry.get_text() == ""
                assert app.setup_window is None
            except BaseException as error:
                failures.append(error)
            finally:
                app.quit()
            return False

        GLib.timeout_add(300, verify)

    run(path, on_activate=activated)
    if failures:
        raise failures[0]


@pytest.mark.skipif(
    os.environ.get("CAELUM_DESKTOP_TESTS") != "1", reason="Opt-in native GTK setup test"
)
def test_setup_collects_distinct_custom_keys_before_validation(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    from unittest.mock import AsyncMock

    from gi.repository import GLib, Gtk

    from caelum.desktop import run

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr("caelum.desktop.microphones", lambda: [])
    monkeypatch.setattr("caelum.desktop.request", lambda _: {"state": "hidden"})
    keys = {}
    monkeypatch.setattr("caelum.credentials.get", keys.get)
    monkeypatch.setattr(
        "caelum.credentials.store", lambda name, value: keys.update({name: value}) or "file"
    )
    monkeypatch.setattr("caelum.credentials.delete", lambda name: keys.pop(name, None))
    monkeypatch.setattr(
        "caelum.credentials.describe",
        lambda name: "key saved in private file (not encrypted)" if name in keys else "key missing",
    )
    checked = AsyncMock()
    monkeypatch.setattr("caelum.onboarding_ui.validate_providers", checked)
    config = Config()
    config.cleanup.model = "custom-model"
    config.cleanup.key_env = "REFINEMENT_KEY"
    path = tmp_path / "config.toml"
    save(config, path)
    failures = []

    def activated(app):
        def verify():
            try:
                app.work = lambda operation, done=None: done(operation()) if done else operation()
                setup = app.setup_window
                assert app.window.measure(Gtk.Orientation.HORIZONTAL, -1).minimum <= 640
                assert not setup.remove_key.get_visible()
                setup.consent.set_active(True)
                setup.key_entry.set_text("first-test-key")
                setup.advance()
                assert setup.stage == 1
                assert setup.key_name == "REFINEMENT_KEY"
                assert not setup.key_entry.get_text()
                checked.assert_not_awaited()
                setup.key_entry.set_text("second-test-key")
                setup.advance()
                assert setup.stage == 2 and setup.validated
                checked.assert_awaited_once()
                assert keys == {"GROQ_API_KEY": "first-test-key", "REFINEMENT_KEY": "second-test-key"}
                assert "not encrypted" in app.notice.get_text()
                setup.go_back()
                assert setup.remove_key.get_visible()
                setup.delete_key()
                assert "REFINEMENT_KEY" not in keys
                assert not setup.remove_key.get_visible()
                setup.open_settings()
                assert app.stack.get_visible_child_name() == "advanced"
                assert app.setup_window is None
            except BaseException as error:
                failures.append(error)
            finally:
                app.quit()
            return False

        GLib.timeout_add(300, verify)

    run(path, on_activate=activated)
    if failures:
        raise failures[0]
