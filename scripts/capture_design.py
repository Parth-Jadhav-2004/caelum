"""Render seeded native screens without touching real settings, keys, audio or service.

Run with the project's Python in a GTK desktop session. X11 ImageMagick capture is
used only if GTK cannot snapshot an actively blinking entry. The temporary modal
window provides a controlled size without changing the desktop's window rules.
"""

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1100)
    parser.add_argument("--height", type=int, default=760)
    parser.add_argument("--font-scale", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("/tmp/caelum-design-captures"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["GDK_BACKEND"] = "x11"
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Graphene", "1.0")
    from gi.repository import GLib, Graphene, Gtk

    from caelum.config import Config, save
    from caelum.desktop import run
    from caelum.onboarding import Progress

    original_read = Path.read_text
    def scaled_read(path, *positional, **keywords):
        text = original_read(path, *positional, **keywords)
        if path.name == "desktop.css":
            return re.sub(r"font-size: ([0-9.]+)px", lambda match:
                          f"font-size: {float(match[1]) * args.font_scale}px", text)
        return text

    failures = []
    with tempfile.TemporaryDirectory(prefix="caelum-design-") as directory:
        root = Path(directory)
        with patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
        }):
            config = Config()
            config.desktop.theme = "light"
            path = root / "config.toml"
            save(config, path)
            Progress(4, True).save(path)

            def activated(app):
                original = app.window
                child = original.get_child()
                original.set_child(None)
                preview = Gtk.Window(transient_for=original, modal=True, title="Caelum design check")
                preview.set_application(app)
                preview.add_css_class("caelum")
                preview.set_default_size(args.width, args.height)
                preview.set_resizable(False)
                preview.set_child(child)
                app.window = preview
                preview.present()
                original.set_visible(False)
                for index, text in enumerate((
                    "Could you send the updated proposal before Thursday? I'll review it this afternoon.",
                    "Remember to book the train tickets for next week.",
                    "The prototype is ready for feedback. Let's test the onboarding flow with three new users.",
                )):
                    app.history.record(str(index), text, {"capture_ms": 18000}, config, True, False)
                states = [(page, theme, stage) for theme in (1, 2)
                          for page, stage in (("home", 0), ("history", 0), ("stats", 0),
                                              ("settings", 0), ("advanced", 0),
                                              ("setup", 1), ("setup", 2),
                                              ("setup", 3), ("setup", 4))]

                def next_state():
                    if not states:
                        app.quit()
                        return False
                    page, theme, stage = states.pop(0)
                    app.render_data(({"state": "hidden"}, app.history.read(),
                                     app.history.read(limit=5), app.history.summary()))
                    app.theme.set_selected(theme)
                    if page == "setup":
                        app.open_setup()
                        app.setup_window.stage = stage
                        app.setup_window.render()
                    else:
                        app.navigate(page)
                    target = args.output / f"{page}{stage or ''}-{'light' if theme == 1 else 'dark'}.png"

                    def capture():
                        try:
                            snapshot = Gtk.Snapshot()
                            w, h = preview.get_width(), preview.get_height()
                            Gtk.WidgetPaintable.new(preview).snapshot(snapshot, w, h)
                            node = snapshot.to_node()
                            if node is None:
                                gi.require_version("GdkX11", "4.0")
                                from gi.repository import GdkX11
                                xid = GdkX11.X11Surface.get_xid(preview.get_surface())
                                subprocess.run(["import", "-window", str(xid), str(target)], check=True)
                            else:
                                texture = preview.get_renderer().render_texture(
                                    node, Graphene.Rect().init(0, 0, w, h)
                                )
                                if not texture.save_to_png(str(target)):
                                    raise RuntimeError("Could not save native screenshot")
                            print(f"{target} ({w} × {h})", flush=True)
                        except Exception as error:
                            failures.append(error)
                            app.quit()
                            return False
                        GLib.timeout_add(100, next_state)
                        return False
                    GLib.timeout_add(350, capture)
                    return False
                GLib.timeout_add(500, next_state)

            with (
                patch.object(Path, "read_text", scaled_read),
                patch("caelum.desktop.microphones", return_value=[]),
                patch("caelum.desktop.request", return_value={"state": "hidden"}),
                patch("caelum.credentials.get", return_value=None),
                patch("caelum.credentials.describe", return_value="key missing; open setup to add a key"),
                patch("caelum.desktop.credential_status", return_value="key missing; open setup to add a key"),
            ):
                run(path, on_activate=activated)
            if failures:
                raise failures[0]


if __name__ == "__main__":
    main()
