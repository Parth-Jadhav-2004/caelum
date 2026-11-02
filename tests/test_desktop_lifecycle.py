import os
from types import SimpleNamespace

import pytest


@pytest.mark.skipif(
    os.environ.get("CAELUM_DESKTOP_TESTS") != "1", reason="Opt-in native GTK desktop test"
)
def test_service_startup_reuses_daemon_and_tray_close_remains_reachable(tmp_path, monkeypatch):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib

    from caelum import desktop
    from caelum.config import Config, save
    from caelum.onboarding import Progress

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(desktop, "microphones", lambda: [])
    monkeypatch.setattr(desktop, "request", lambda _: {"state": "hidden", "paused": False})
    path = tmp_path / "config.toml"
    save(Config(), path)
    Progress(4, True).save(path)
    failures = []

    def activated(app):
        def verify():
            try:
                app.work = lambda operation, done=None: done(operation()) if done else operation()
                launches = []
                process = SimpleNamespace(poll=lambda: None)
                monkeypatch.setattr(desktop.subprocess, "Popen", lambda *args, **kwargs: launches.append((args, kwargs)) or process)
                app.ensure_service()
                assert not launches  # A daemon already owns the shortcut.

                def missing(_):
                    raise FileNotFoundError()

                monkeypatch.setattr(desktop, "request", missing)
                app.ensure_service()
                app.ensure_service()
                assert len(launches) == 1
                args, kwargs = launches[0]
                assert args[0][-1] == "serve"
                assert str(desktop.Path(desktop.__file__).resolve().parent.parent) in kwargs["env"]["PYTHONPATH"]

                app.tray_held = False
                app.tray_availability(True)
                assert app.tray_held
                app.tray = SimpleNamespace(registered=True, close=lambda: None)
                assert app.close_window()
                assert not app.window.get_visible()
                app.tray_availability(False)
                assert app.window.get_visible() and not app.tray_held
                app.tray.registered = False
                assert not app.close_window()
            except BaseException as error:
                failures.append(error)
            finally:
                app.quit()
            return False

        GLib.timeout_add(200, verify)

    desktop.run(path, on_activate=activated)
    if failures:
        raise failures[0]
