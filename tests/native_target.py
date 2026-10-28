"""Disposable native text field used only by the opt-in insertion integration check."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

Gtk.init()
loop = GLib.MainLoop()
window = Gtk.Window(title="Caelum insertion self-test")
entry = Gtk.Entry()
entry.set_placeholder_text("Temporary Caelum integration test")
window.set_child(entry)
window.set_default_size(400, 80)
window.connect("close-request", lambda *_: loop.quit())
entry.connect(
    "changed",
    lambda widget: (
        print("visible-match", flush=True)
        if widget.get_text() == "Caelum insertion check — 42."
        else None
    ),
)
window.present()
entry.grab_focus()
print("ready", flush=True)
loop.run()
