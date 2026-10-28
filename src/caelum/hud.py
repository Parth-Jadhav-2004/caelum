"""GTK4 layer-shell helper. Its input channel never accepts transcripts or credentials."""

import json
import math
import os
import sys
import time
from collections import deque

STATES = {
    "hidden",
    "starting",
    "listening",
    "recording",
    "processing",
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
    "processing": "Processing…",
    "refining": "Refining…",
    "success": "Done",
    "unrefined": "Done · unrefined",
    "error": "Retry or cancel",
    "no_speech": "No speech",
    "copied": "Copied · paste manually",
    "cancelled": "Cancelled",
}
ERRORS = {
    "microphone": "Microphone unavailable",
    "network": "Connection lost",
    "insert": "Could not insert",
    "capture": "Capture interrupted",
    "hud": "Feedback unavailable",
}


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
    win.set_default_size(280, 96)
    win.set_focusable(False)
    Layer.init_for_window(win)
    Layer.set_namespace(win, "caelum-recording-pill")
    Layer.set_layer(win, Layer.Layer.OVERLAY)
    Layer.set_keyboard_mode(win, Layer.KeyboardMode.NONE)
    Layer.set_exclusive_zone(win, 0)
    Layer.set_anchor(win, Layer.Edge.BOTTOM, True)
    Layer.set_margin(win, Layer.Edge.BOTTOM, 8)  # 16 px gutter + 8 = 24 body clearance
    css = Gtk.CssProvider()
    css.load_from_data(b"window { background: transparent; box-shadow: none; }")
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, 800)
    area = Gtk.DrawingArea()
    area.set_content_width(280)
    area.set_content_height(96)
    area.set_focusable(False)
    win.set_child(area)
    win.connect("realize", lambda w: w.get_surface().set_input_region(cairo.Region()))
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
    transition = time.monotonic()
    dismiss_at = None
    dismiss_started = None
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
        elapsed = now - transition
        alpha = min(1, elapsed / (0.08 if reduced_motion else 0.18))
        offset = 0 if reduced_motion else 6 * (1 - alpha) ** 3
        if dismiss_started is not None:
            progress = min(1, (now - dismiss_started) / (0.08 if reduced_motion else 0.16))
            alpha *= 1 - progress
            offset += 0 if reduced_motion else progress * 4
        cr.push_group()
        x, y = (width - 232) / 2, 32 + offset
        for spread in range(12, 0, -2):
            rounded(cr, x - spread, y + 6 - spread / 2, 232 + 2 * spread, 48 + spread, 24 + spread)
            cr.set_source_rgba(0, 0, 0, 0.018)
            cr.fill()
        rounded(cr, x, y, 232, 48, 24)
        cr.set_source_rgba(0.09, 0.098, 0.114, 1 if high_contrast else 0.94)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.14)
        cr.set_line_width(1)
        cr.stroke()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        kind = state["state"]
        capture = kind in ("listening", "recording")
        mint, white, error = (0.659, 0.863, 0.784), (0.961, 0.961, 0.969), (0.953, 0.706, 0.667)
        cr.set_source_rgb(
            *(
                mint
                if kind in ("recording", "success", "unrefined")
                else error
                if kind == "error"
                else white
            )
        )
        cx, cy = (x + 24 if capture else x + 39), y + 24
        cr.set_line_width(1.6)
        if capture:
            cr.arc(cx, cy, 4, 0, math.tau)
            cr.fill() if kind == "recording" else cr.stroke()
            for i in range(17):
                level = 0 if reduced_motion else state["history"][i]
                envelope = 0.4 + 0.6 * math.sin(math.pi * (i + 0.5) / 17)
                bar = 3 + 21 * level * envelope
                bx = x + 65 + i * 5.5
                cr.set_line_width(2.5)
                cr.move_to(bx, cy - bar / 2 + 1.25)
                cr.line_to(bx, cy + bar / 2 - 1.25)
                cr.stroke()
            seconds = int(state["elapsed_ms"]) // 1000
            label = f"{seconds // 60:02}:{seconds % 60:02}"
            cr.select_font_face("monospace", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(13)
            cr.move_to(x + 176, cy + 4.5)
            cr.show_text(label)
        else:
            label = (
                ERRORS.get(state.get("error_code"), LABELS.get(kind, ""))
                if kind == "error"
                else LABELS.get(kind, "")
            )
            cr.select_font_face("Noto Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(13)
            label_width = cr.text_extents(label).width
            if label_width > 180:
                cr.set_font_size(12)
                label_width = cr.text_extents(label).width
            cx = x + (232 - (24 + label_width)) / 2 + 7
            if kind in ("processing", "starting"):
                angle = 0 if reduced_motion else (now % 1.2) / 1.2 * math.tau
                cr.arc(cx, cy, 6, angle, angle + math.pi * 1.45)
                cr.stroke()
            elif kind in ("success", "unrefined"):
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
            elif kind == "error":
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
        nonlocal tick, dismiss_started
        now = time.monotonic()
        if dismiss_at is not None and now >= dismiss_at and dismiss_started is None:
            dismiss_started = now
        if dismiss_started is not None and now - dismiss_started >= (
            0.08 if reduced_motion else 0.16
        ):
            win.set_visible(False)
            tick = 0
            return False
        area.queue_draw()
        return True

    def receive(message):
        nonlocal tick, transition, dismiss_at, dismiss_started
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
                dismiss_started = time.monotonic()
            return
        if previous != state["state"] or new_session:
            if new_session or not win.get_visible():
                transition = time.monotonic()
                Layer.set_monitor(win, monitor(message.get("output", "")))
            dismiss_started = None
            dwell = {
                "success": 0.65,
                "unrefined": 0.65,
                "error": 5,
                "no_speech": 0.8,
                "copied": 2,
                "cancelled": 0.0,
            }.get(state["state"])
            dismiss_at = time.monotonic() + dwell if dwell is not None else None
            name = (
                "Microphone active"
                if state["state"] in ("listening", "recording")
                else LABELS.get(state["state"], "Dictation")
            )
            area.update_property([Gtk.AccessibleProperty.LABEL], [name])
            if hasattr(area, "announce") and previous not in ("listening", "recording"):
                area.announce(name, Gtk.AccessibleAnnouncementPriority.MEDIUM)
        win.set_visible(True)  # no present(), activation, or keyboard focus
        if not tick:
            tick = GLib.timeout_add(33, frame)

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
