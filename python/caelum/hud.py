"""GTK4 layer-shell helper. Its input channel never accepts transcripts or credentials."""

import json
import math
import os
import sys
import threading
import time
from collections import deque

STATES = {
    "hidden",
    "starting",
    "listening",
    "recording",
    "processing",
    "loading",
    "missing_model",
    "success_fallback_online",
    "success_fallback_local",
    "refining",
    "success",
    "unrefined",
    "error",
    "no_speech",
    "copied",
    "cancelled",
}
LABELS = {
    "starting": "Starting…",
    "loading": "Getting ready…",
    "missing_model": "Speech model not downloaded",
    "success_fallback_online": "Done · used Online",
    "success_fallback_local": "Done · used this computer",
    "processing": "Transcribing",
    "refining": "Transcribing",
    "success": "Inserted",
    "unrefined": "Inserted",
    "error": "Try again",
    "no_speech": "No speech",
    "copied": "Copied: paste with Ctrl V",
    "cancelled": "Cancelled",
}
ERRORS = {
    "microphone": "Microphone unavailable",
    "network": "Connection lost",
    "insert": "Insert failed",
    "capture": "Capture interrupted",
    "hud": "Feedback unavailable",
    "missing_model": "Speech model not downloaded",
    "local_decode": "Couldn't make sense of that",
    "local_setup": "Speech model needs attention",
}


def presentation(kind):
    """Pure state layout shared by the renderer and transition handling."""
    if kind not in STATES:
        raise ValueError("Unknown pill state")
    capture = kind in ("listening", "recording")
    return {
        "visible": kind != "hidden",
        "capture": capture,
        "width": 140 if capture else 320 if kind == "error" else 264 if kind == "copied" else 184,
        "dwell": {"success": 0.6, "unrefined": 0.6, "error": 5,
                  "no_speech": 0.8, "copied": 2, "cancelled": 0.0}.get(kind),
        "actions": ("cancel", "stop") if capture else ("retry", "cancel") if kind == "error" else (),
    }


class PillFade:
    """An interruptible fade; repeated status messages never restart it."""

    def __init__(self, reduced_motion=False):
        self.duration = 0 if reduced_motion else 0.16
        self.started = 0.0
        self.initial = 0.0
        self.target = 0.0

    def opacity(self, now):
        progress = min(1.0, max(0.0, (now - self.started) / self.duration)) if self.duration else 1.0
        return self.initial + (self.target - self.initial) * progress

    def move(self, visible, now):
        target = float(visible)
        if target != self.target:
            self.initial = self.opacity(now)
            self.started = now
            self.target = target


def run(reduced_motion=False, high_contrast=False):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    import cairo
    from gi.repository import Gdk, GLib, Gtk
    from gi.repository import Gtk4LayerShell as Layer

    Gtk.init()
    if not Layer.is_supported():
        raise RuntimeError("Native Wayland layer-shell unavailable; refusing an ordinary window")
    if "--check" in sys.argv:
        print("supported")
        return
    settings = Gtk.Settings.get_default()
    reduced_motion = reduced_motion or not settings.get_property("gtk-enable-animations")
    loop = GLib.MainLoop()
    win = Gtk.Window()
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_default_size(336, 52)
    win.set_focusable(False)
    Layer.init_for_window(win)
    Layer.set_namespace(win, "caelum-recording-pill")
    Layer.set_layer(win, Layer.Layer.OVERLAY)
    Layer.set_keyboard_mode(win, Layer.KeyboardMode.NONE)
    Layer.set_exclusive_zone(win, 0)
    Layer.set_anchor(win, Layer.Edge.BOTTOM, True)
    Layer.set_margin(win, Layer.Edge.BOTTOM, 16)  # capsule starts 8px inside: 24px clearance
    css = Gtk.CssProvider()
    css.load_from_data(b"window { background: transparent; box-shadow: none; }")
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, 800)
    area = Gtk.DrawingArea()
    area.set_content_width(336)
    area.set_content_height(52)
    area.set_focusable(False)
    overlay = Gtk.Overlay()
    overlay.set_child(area)
    controls = Gtk.Box(spacing=64)
    controls.set_halign(Gtk.Align.CENTER)
    controls.set_valign(Gtk.Align.CENTER)

    def command(action):
        def send():
            from .cli import control
            try:
                control(action)
            except (OSError, RuntimeError, ValueError):
                pass  # authoritative service status reports failures
        threading.Thread(target=send, daemon=True).start()

    for label, name, action in (("×", "Cancel recording", "cancel"), ("✓", "Finish recording", "stop")):
        button = Gtk.Button(label=label)
        button.set_tooltip_text(name)
        button.update_property([Gtk.AccessibleProperty.LABEL], [name])
        button.set_size_request(32, 32)
        button.set_focusable(False)
        button.connect("clicked", lambda _, a=action: command(a))
        controls.append(button)
    overlay.add_overlay(controls)
    error_controls = Gtk.Box(spacing=4)
    error_controls.set_size_request(300, 32)
    error_controls.set_halign(Gtk.Align.CENTER)
    error_controls.set_valign(Gtk.Align.CENTER)
    spacer = Gtk.Box()
    spacer.set_hexpand(True)
    error_controls.append(spacer)
    for label, name, action in (("Retry", "Retry dictation", "retry"), ("Esc", "Cancel dictation", "cancel")):
        button = Gtk.Button(label=label)
        button.update_property([Gtk.AccessibleProperty.LABEL], [name])
        button.set_focusable(False)
        button.connect("clicked", lambda _, a=action: command(a))
        error_controls.append(button)
    overlay.add_overlay(error_controls)
    win.set_child(overlay)
    win.connect("realize", lambda w: w.get_surface().set_input_region(cairo.Region()))
    css.load_from_data(b"window { background: transparent; box-shadow: none; } button { background: transparent; color: #ededef; border: none; border-radius: 16px; padding: 0; min-width: 32px; min-height: 32px; box-shadow: none; } button:hover { background: #26262b; }")
    state = {
        "state": "hidden",
        "session_id": "",
        "sequence": -1,
        "level": 0,
        "elapsed_ms": 0,
        "history": [0] * 17,
        "error_code": "",
    }
    tick = 0
    fade = PillFade(reduced_motion)
    display_state = dict(state)
    dismiss_at = None
    input_buffer = bytearray()
    retired_sessions = deque(maxlen=128)

    def monitor(name):
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            item = monitors.get_item(i)
            if item.get_connector() == name:
                return item
        return monitors.get_item(0) if monitors.get_n_items() else None

    def rounded(cr, x, y, width, height, radius):
        cr.new_sub_path()
        for cx, cy, start in (
            (x + width - radius, y + radius, -90),
            (x + width - radius, y + height - radius, 0),
            (x + radius, y + height - radius, 90),
            (x + radius, y + radius, 180),
        ):
            cr.arc(cx, cy, radius, math.radians(start), math.radians(start + 90))
        cr.close_path()

    def draw(widget, cr, width, height):
        now = time.monotonic()
        alpha = fade.opacity(now)
        cr.push_group()
        kind = display_state["state"]
        layout = presentation(kind)
        capture, capsule_width = layout["capture"], layout["width"]
        x, y = (width - capsule_width) / 2, 8
        rounded(cr, x, y, capsule_width, 36, 18)
        cr.set_source_rgb(0.094, 0.094, 0.106)  # #18181b
        cr.fill_preserve()
        cr.set_source_rgb(*( (0.6, 0.6, 0.65) if high_contrast else (0.149, 0.149, 0.169)))
        cr.set_line_width(1)
        cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        kind = display_state["state"]
        capture = kind in ("listening", "recording")
        accent, white, error = (0.847, 0.847, 0.847), (0.929, 0.929, 0.937), (0.949, 0.333, 0.353)
        cr.set_source_rgb(
            *(
                accent
                if kind in ("recording", "success", "unrefined", "success_fallback_online", "success_fallback_local")
                else error
                if kind in ("error", "missing_model")
                else white
            )
        )
        cx, cy = (x + 24 if capture else x + 39), y + 18
        cr.set_line_width(1.6)
        if capture:
            for i in range(13):
                level = 0 if reduced_motion else display_state["history"][i + 2]
                envelope = 0.4 + 0.6 * math.sin(math.pi * (i + 0.5) / 13)
                bar = 3 + 21 * level * envelope
                bx = x + 40 + i * 5
                cr.set_line_width(2)
                cr.move_to(bx, cy - bar / 2 + 1)
                cr.line_to(bx, cy + bar / 2 - 1)
                cr.stroke()
        else:
            label = (
                ERRORS.get(display_state.get("error_code"), LABELS.get(kind, ""))
                if kind == "error"
                else LABELS.get(kind, "")
            )
            cr.select_font_face("Inter", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(13)
            label_width = cr.text_extents(label).width
            if label_width > 180:
                cr.set_font_size(12)
                label_width = cr.text_extents(label).width
            cx = x + 20 if kind == "error" else x + (capsule_width - (24 + label_width)) / 2 + 7
            if kind in ("processing", "starting", "loading"):
                angle = 0 if reduced_motion else (now % 1.2) / 1.2 * math.tau
                cr.arc(cx, cy, 6, angle, angle + math.pi * 1.45)
                cr.stroke()
            elif kind in ("success", "unrefined", "success_fallback_online", "success_fallback_local"):
                cr.move_to(cx - 5, cy)
                cr.line_to(cx - 1, cy + 4)
                cr.line_to(cx + 6, cy - 4)
                cr.stroke()
            elif kind == "refining":
                cr.move_to(cx, cy - 7)
                for dx, dy in ((2, -2), (7, 0), (2, 2), (0, 7), (-2, 2), (-7, 0), (-2, -2)):
                    cr.line_to(cx + dx, cy + dy)
                cr.close_path()
                cr.stroke()
            elif kind in ("error", "missing_model"):
                cr.move_to(cx, cy - 7)
                cr.line_to(cx + 7, cy + 6)
                cr.line_to(cx - 7, cy + 6)
                cr.close_path()
                cr.stroke()
                cr.move_to(cx, cy - 2)
                cr.line_to(cx, cy + 1)
                cr.stroke()
                cr.arc(cx, cy + 4, 0.7, 0, math.tau)
                cr.fill()
            else:
                rounded(cr, cx - 5, cy - 6, 10, 12, 2)
                cr.stroke()
            cr.move_to(cx + 16, cy + 4.5)
            cr.show_text(label)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)

    def frame():
        nonlocal tick
        now = time.monotonic()
        if dismiss_at is not None and now >= dismiss_at:
            fade.move(False, now)
        alpha = fade.opacity(now)
        controls.set_opacity(alpha)
        error_controls.set_opacity(alpha)
        if not fade.target:
            controls.set_sensitive(False)
            error_controls.set_sensitive(False)
            if win.get_realized():
                win.get_surface().set_input_region(cairo.Region())
            if alpha <= 0:
                win.set_visible(False)
                tick = 0
                return False
        area.queue_draw()
        return True

    def receive(message):
        nonlocal tick, dismiss_at
        if set(message) - {
            "session_id",
            "sequence",
            "state",
            "elapsed_ms",
            "level",
            "history",
            "output",
            "error_code",
        }:
            return
        if message.get("state") not in STATES or not isinstance(message.get("session_id"), str):
            return
        if not isinstance(message.get("sequence"), int) or message["sequence"] < 0:
            return
        if "history" in message and (
            not isinstance(message["history"], list)
            or len(message["history"]) != 17
            or any(
                not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1
                for v in message["history"]
            )
        ):
            return
        if "elapsed_ms" in message and (
            not isinstance(message["elapsed_ms"], (int, float))
            or not math.isfinite(message["elapsed_ms"])
            or message["elapsed_ms"] < 0
        ):
            return
        if (
            message.get("session_id") == state["session_id"]
            and message.get("sequence", -1) <= state["sequence"]
        ):
            return
        previous = state["state"]
        new_session = message["session_id"] != state["session_id"]
        if new_session:
            if message["session_id"] in retired_sessions:
                return
            retired_sessions.append(state["session_id"])
        elif (
            not win.get_visible()
            and previous == message["state"]
            and previous in ("success", "unrefined", "error", "copied", "no_speech", "cancelled")
        ):
            return
        state.update(message)
        if state["state"] == "hidden":
            if win.get_visible():
                fade.move(False, time.monotonic())
            return
        if previous != state["state"] or new_session:
            if new_session or not win.get_visible():
                Layer.set_monitor(win, monitor(message.get("output", "")))
            dwell = presentation(state["state"])["dwell"]
            dismiss_at = time.monotonic() + dwell if dwell is not None else None
            name = (
                "Microphone active"
                if state["state"] in ("listening", "recording")
                else LABELS.get(state["state"], "Dictation")
            )
            area.update_property([Gtk.AccessibleProperty.LABEL], [name])
            if hasattr(area, "announce") and previous not in ("listening", "recording"):
                area.announce(name, Gtk.AccessibleAnnouncementPriority.MEDIUM)
        display_state.update(state)
        if previous != state["state"] or new_session:
            fade.move(True, time.monotonic())
        controls.set_sensitive(bool(fade.target))
        error_controls.set_sensitive(bool(fade.target))
        controls.set_opacity(fade.opacity(time.monotonic()))
        error_controls.set_opacity(fade.opacity(time.monotonic()))
        controls.set_visible(state["state"] in ("listening", "recording"))
        error_controls.set_visible(state["state"] == "error")
        kind = state["state"]
        capsule_width = presentation(kind)["width"]
        if win.get_realized():
            win.get_surface().set_input_region(cairo.Region(cairo.RectangleInt((336 - capsule_width) // 2, 8, capsule_width, 36)))
        win.set_visible(True)  # no present(), activation, or keyboard focus
        if not tick:
            tick = GLib.timeout_add(16, frame)

    def stdin_ready(fd, condition):
        if condition & GLib.IO_HUP:
            loop.quit()
            return False
        chunk = os.read(fd, 65536)
        if not chunk:
            loop.quit()
            return False
        input_buffer.extend(chunk)
        if len(input_buffer) > 131072:
            loop.quit()
            return False
        while b"\n" in input_buffer:
            line, _, rest = input_buffer.partition(b"\n")
            input_buffer[:] = rest
            try:
                receive(json.loads(line))
            except (ValueError, TypeError, KeyError):
                continue
        return True

    area.set_draw_func(draw)
    GLib.io_add_watch(sys.stdin.fileno(), GLib.IO_IN | GLib.IO_HUP, stdin_ready)
    # Warm GTK's renderer before accepting hotkeys; leave no mapped surface at idle.
    warm_frames = 0

    def warmed(widget, frame_clock):
        nonlocal warm_frames
        warm_frames += 1
        if warm_frames >= 3:
            win.set_visible(False)
            win.set_opacity(1)
            print("ready", flush=True)
            return False
        return True

    win.set_opacity(0)
    area.add_tick_callback(warmed)
    win.set_visible(True)
    loop.run()
    win.destroy()


if __name__ == "__main__":
    run("--reduced-motion" in sys.argv, "--high-contrast" in sys.argv)
