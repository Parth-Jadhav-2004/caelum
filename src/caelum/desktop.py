"""Native GTK desktop shell; slow work stays outside the GTK main thread."""

import asyncio
import json
import math
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .config import config_path, load, save, validate
from .credentials import describe as credential_status
from .history import History
from .launcher import entry_path, install
from .portable import backend_name


def request(action):
    root = os.environ.get("XDG_RUNTIME_DIR")
    if not root:
        raise RuntimeError("Open Caelum inside your desktop session")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(Path(root) / "caelum/control.sock"))
        client.sendall(json.dumps({"action": action}).encode() + b"\n")
        result = json.loads(client.makefile("r").readline(65536))
        if "error" in result:
            raise RuntimeError(result["error"])
        return result


def install_queued_update():
    from .updates import apply_pending

    running = False
    try:
        request("prepare-update")
        running = True
    except (FileNotFoundError, ConnectionRefusedError):
        pass
    import fcntl

    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        raise RuntimeError("Open Caelum inside your desktop session to install updates")
    lock_path = Path(runtime) / "caelum/daemon.lock"
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    deadline = time.monotonic() + 10
    with lock_path.open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Dictation is still stopping. Restart Caelum to retry."
                    ) from None
                time.sleep(0.1)
        apply_pending()
    return running


def display_version():
    from importlib.metadata import PackageNotFoundError, version

    from .updates import installed

    info = installed()
    if info:
        return info["version"]
    try:
        return version("caelum-dictation")
    except PackageNotFoundError:
        return "unknown"


def microphones():
    import sounddevice as sound

    return [
        (device["name"], device["name"])
        for device in sound.query_devices()
        if device["max_input_channels"] > 0
    ]


PRESETS = ("Groq", "Transcription only", "Custom provider")


def provider_preset(config):
    groq = "https://api.groq.com/openai/v1"
    if config.stt.base_url.rstrip("/") != groq or config.stt.model != "whisper-large-v3-turbo":
        return 2
    if not config.cleanup.model:
        return 1
    if (
        config.cleanup.base_url.rstrip("/") == groq
        and config.cleanup.model == "openai/gpt-oss-20b"
        and config.cleanup.key_env == config.stt.key_env == "GROQ_API_KEY"
    ):
        return 0
    return 2


def apply_provider_preset(config, selected):
    updated = deepcopy(config)
    if selected == 2:
        return updated
    if selected not in (0, 1):
        raise ValueError("Unknown provider preset")
    updated.stt.base_url = "https://api.groq.com/openai/v1"
    updated.stt.model = "whisper-large-v3-turbo"
    updated.stt.key_env = "GROQ_API_KEY"
    updated.cleanup.base_url = updated.stt.base_url
    updated.cleanup.key_env = updated.stt.key_env
    updated.cleanup.model = "openai/gpt-oss-20b" if selected == 0 else ""
    updated.cleanup.reasoning_effort = "low" if selected == 0 else ""
    return updated


async def connection_status(config):
    from .providers import ProviderError, Providers

    try:
        validate(config)
    except ValueError as error:
        return f"Check provider settings: {error}"
    provider = Providers(config)
    results = []
    try:
        for title, settings in (("Transcription", config.stt), ("Refinement", config.cleanup)):
            if not settings.model:
                results.append(f"{title}: off (raw transcription)")
                continue
            try:
                models = await provider.models(settings)
                results.append(
                    f"{title}: connected (model available)"
                    if settings.model in models
                    else f"{title}: model unavailable; choose another model in Advanced"
                )
            except ProviderError as error:
                results.append(
                    f"{title}: key missing; open Settings → provider status → Manage keys"
                    if error.kind == "missing_key"
                    else f"{title}: {error}"
                )
    finally:
        await provider.client.aclose()
    return "\n".join(results)


def service_presentation(status):
    if not status:
        return "Stopped", "Start the service to record."
    if status.get("paused"):
        return "Paused", "Resume to use the recording shortcut."
    state = status.get("state", "hidden")
    if state == "error":
        if status.get("pending_audio"):
            guidance = {
                "invalid_key": "Replace the key in Settings → provider status → Manage keys, then retry.",
                "missing_key": "Add the key in Settings → provider status → Manage keys, then retry.",
                "quota": "Check provider usage or billing before retrying.",
                "rate_limit": "Wait for the provider rate limit to reset, then retry.",
                "offline": "Check your network connection, then retry.",
                "timeout": "The provider timed out. Retry when the connection is stable.",
                "model": "Choose an available model in Settings.",
            }.get(status.get("error_kind"), "Retry or cancel before the recording expires.")
            return "Awaiting retry", guidance + " Pending audio stays in memory only."
        if status.get("error_kind") in ("microphone", "capture"):
            return "Microphone unavailable", "Open Settings to choose a microphone and test input."
        return "Recording failed", "Check Settings and try recording again."
    labels = {
        "hidden": (
            "Ready",
            "Use Record or your approved desktop shortcut to begin."
            if status.get("backend") == "portable"
            else "Hold your shortcut to begin.",
        ),
        "starting": ("Starting microphone", "Preparing to record."),
        "listening": ("Recording", "Listening for speech. No interim text is shown."),
        "recording": ("Recording", "Release your shortcut or finish recording to process."),
        "processing": ("Processing", "Transcribing your recording."),
        "refining": ("Processing", "Refining punctuation and formatting."),
        "success": ("Done", "Refined text was sent to the original application."),
        "unrefined": (
            "Done · unrefined",
            "Raw transcription was sent to the original application.",
        ),
        "copied": ("Copied", "Paste manually in the intended application."),
        "saved": ("Saved", "Use Copy text below, then paste into your chosen app."),
        "no_speech": ("No speech detected", "Nothing inserted. Try recording again."),
    }
    title, detail = labels.get(state, ("Ready", "Use your shortcut or Record to begin."))
    metrics = status.get("metrics") or []
    if state in ("saved", "copied") and metrics and not metrics[-1].get("cleanup_refined", False):
        detail += " Raw transcription; refinement was skipped or unavailable."
    return title, detail


def run(path=None, *, on_activate=None):
    if os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("GDK_BACKEND", "wayland")
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_foreign("cairo")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango

    class SentenceLayout(Gtk.LayoutManager):
        """Wrap native controls and words in reading order, without FlowBox's columns."""

        def do_get_request_mode(self, widget):
            return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

        def children(self, widget):
            child = widget.get_first_child()
            while child:
                if child.get_visible():
                    yield child
                child = child.get_next_sibling()

        def lines(self, widget, width):
            x, y, line_height = 0, 0, 0
            placed = []
            for child in self.children(widget):
                minimum, natural, _, _ = child.measure(Gtk.Orientation.HORIZONTAL, -1)
                w = min(natural, max(minimum, width))
                _, h, _, _ = child.measure(Gtk.Orientation.VERTICAL, w)
                h = max(55, h)
                if x and x + w > width:
                    x, y, line_height = 0, y + line_height, 0
                placed.append((child, x, y, w, h))
                x += w + 9
                line_height = max(line_height, h)
            return placed, y + line_height

        def do_measure(self, widget, orientation, for_size):
            if orientation == Gtk.Orientation.HORIZONTAL:
                sizes = [child.measure(orientation, -1) for child in self.children(widget)]
                return (max((size.minimum for size in sizes), default=0),
                        sum(size.natural for size in sizes) + max(0, len(sizes) - 1) * 9,
                        -1, -1)
            _, height = self.lines(widget, max(1, for_size))
            return height, height, -1, -1

        def do_allocate(self, widget, width, height, baseline):
            placed, _ = self.lines(widget, width)
            for child, x, y, w, h in placed:
                point = Graphene.Point()
                point.init(x, y)
                child.allocate(w, h, -1, Gsk.Transform().translate(point))

    class ClampedLayout(Gtk.LayoutManager):
        """Constrain content width without adding margins to the minimum window size."""

        def __init__(self, maximum, center, vertical_center):
            super().__init__()
            self.maximum = maximum
            self.center = center
            self.vertical_center = vertical_center

        def do_get_request_mode(self, widget):
            return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

        def do_measure(self, widget, orientation, for_size):
            child = widget.get_first_child()
            if orientation == Gtk.Orientation.HORIZONTAL:
                minimum, natural, _, _ = child.measure(orientation, -1)
                return minimum, max(minimum, min(self.maximum, natural)), -1, -1
            width = min(self.maximum, for_size) if for_size >= 0 else self.maximum
            return child.measure(orientation, width)

        def do_allocate(self, widget, width, height, baseline):
            child = widget.get_first_child()
            w = min(self.maximum, width)
            h = height
            if self.vertical_center:
                _, natural, _, _ = child.measure(Gtk.Orientation.VERTICAL, w)
                h = min(height, natural)
            point = Graphene.Point()
            point.init((width - w) // 2 if self.center else 0, (height - h) // 2)
            child.allocate(w, h, -1, Gsk.Transform().translate(point))

    class Desktop(Gtk.Application):
        def __init__(self):
            super().__init__(
                application_id="io.caelum.Dictation",
                flags=Gio.ApplicationFlags.NON_UNIQUE
                if on_activate
                else Gio.ApplicationFlags.DEFAULT_FLAGS,
            )
            self.path = Path(path) if path else config_path()
            self.config = load(self.path)
            self.history = History(self.path)
            self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="caelum-desktop")
            self.process = None
            self.refreshing = False
            self.closed = False
            self.update_busy = False
            self.available_update = None
            self.refresh_generation = 0
            self.devices = [("System default", None)]
            self.history_signature = None
            self.paused = False
            self.portable = backend_name(self.config) == "portable"
            self.connect("activate", self.activate)
            self.connect("shutdown", self.shutdown)

        def work(self, operation, done=None):
            future = self.pool.submit(operation)

            def deliver():
                if self.closed:
                    return False
                try:
                    result = future.result()
                except Exception as error:
                    self.message(
                        str(error)
                        if isinstance(error, (ValueError, RuntimeError))
                        else "Operation failed. Check device access or local file permissions."
                    )
                else:
                    if done:
                        done(result)
                return False

            future.add_done_callback(lambda _: GLib.idle_add(deliver))
            return future

        def label(self, text, style=None, wrap=False):
            widget = Gtk.Label(label=text, xalign=0)
            widget.set_wrap(wrap)
            if style:
                widget.add_css_class(style)
            return widget

        def button(self, text, callback, style=None):
            widget = Gtk.Button(label=text)
            widget.connect("clicked", lambda _: callback())
            if style:
                widget.add_css_class(style)
            return widget

        def box(self, vertical=True, spacing=12):
            return Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                spacing=spacing,
            )

        def clamp(self, child, maximum=600, center=True, vertical_center=False):
            box = self.box(spacing=0)
            box.set_layout_manager(ClampedLayout(maximum, center, vertical_center))
            box.set_hexpand(True)
            box.set_vexpand(vertical_center)
            child.set_halign(Gtk.Align.FILL)
            child.set_valign(Gtk.Align.FILL)
            box.append(child)
            return box

        def flow(self):
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_max_children_per_line(6)
            flow.set_min_children_per_line(1)
            flow.set_row_spacing(8)
            flow.set_column_spacing(8)
            return flow

        def activate(self, _):
            if hasattr(self, "window"):
                self.window.present()
                return
            self.window = Gtk.ApplicationWindow(application=self, title="Caelum")
            self.window.set_default_size(1100, 700)
            self.window.set_size_request(480, 480)
            self.window.add_css_class("caelum")
            header = Gtk.HeaderBar()
            header.set_title_widget(Gtk.Box())
            self.window.set_titlebar(header)
            outer = self.box(False, 0)
            self.navigation = self.box(spacing=0)
            self.navigation.add_css_class("navigation")
            self.navigation.set_size_request(76, -1)
            self.brand = self.label("Caelum", "wordmark")
            self.brand.set_halign(Gtk.Align.CENTER)
            self.brand.set_margin_bottom(24)
            self.navigation.append(self.brand)
            self.stack = Gtk.Stack()
            self.stack.set_hhomogeneous(False)
            self.stack.set_vhomogeneous(False)
            self.stack.set_hexpand(True)
            self.stack.set_vexpand(True)
            self.nav_buttons = {}
            for name, title, icon in (
                ("home", "Home", "home"),
                ("history", "History", "clock"),
                ("settings", "Settings", "gear"),
            ):
                button = Gtk.ToggleButton()
                button.add_css_class("nav-item")
                button.set_size_request(44, 44)
                button.set_halign(Gtk.Align.CENTER)
                button.set_margin_bottom(8)
                button.set_child(self.line_icon(icon))
                button.set_tooltip_text(title)
                button.update_property([Gtk.AccessibleProperty.LABEL], [title])
                button.connect("clicked", lambda _, name=name: self.navigate(name))
                self.nav_buttons[name] = button
                self.navigation.append(button)
            spacer = self.box()
            spacer.set_vexpand(True)
            self.navigation.append(spacer)
            self.theme = Gtk.DropDown.new_from_strings(["System", "Light", "Dark"])
            self.theme.set_selected(("system", "light", "dark").index(self.config.desktop.theme))
            self.theme_button = self.token_menu(self.theme, lambda: ["System", "Light", "Dark"])
            self.theme_button.remove_css_class("token")
            self.theme_button.add_css_class("theme-menu")
            self.theme_button.set_tooltip_text("Appearance: System, Light or Dark")
            self.theme_button.update_property([Gtk.AccessibleProperty.LABEL], ["Appearance"])
            self.navigation.append(self.theme_button)
            self.theme.connect("notify::selected", self.change_theme)
            outer.append(self.navigation)
            content = self.box(spacing=0)
            content.set_hexpand(True)
            self.notice = self.label("", "notice", True)
            self.notice.set_visible(False)
            content.append(self.notice)
            content.append(self.stack)
            outer.append(content)
            self.window.set_child(outer)
            self.build_home()
            self.build_history()
            self.build_stats()
            self.build_settings()
            self.apply_theme()
            self.navigate("home")
            self.window.present()
            self.refresh()
            self.timer = GLib.timeout_add_seconds(1, self.refresh)
            self.work(microphones, self.set_devices)
            from .onboarding import Progress

            if not Progress.load(self.path).complete:
                self.open_setup()
            if on_activate:
                on_activate(self)
            else:
                self.begin_updates()

        def page(self, name, title, description):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            body = self.box(spacing=24)
            body.add_css_class("page")
            heading = self.box(spacing=8)
            heading.append(self.label(title, "title"))
            heading.append(self.label(description, "muted", True))
            body.append(heading)
            scroll.set_child(body)
            self.stack.add_named(scroll, name)
            return body

        def navigate(self, name):
            if name != "setup" and self.stack.get_visible_child_name() == "setup":
                setup = getattr(self, "setup_window", None)
                if setup:
                    setup.finish_setup()
            self.window.set_size_request(900 if name == "home" else 480, 480)
            self.stack.set_visible_child_name(name)
            if name == "advanced":
                name = "settings"
            for key, button in self.nav_buttons.items():
                button.set_active(key == name)
                if key == name:
                    button.add_css_class("selected")
                else:
                    button.remove_css_class("selected")

        def message(self, text):
            self.notice.set_text(text)
            self.notice.set_visible(bool(text))

        def line_icon(self, name):
            icon = Gtk.DrawingArea()
            icon.icon_name = name
            icon.set_content_width(22)
            icon.set_content_height(22)
            icon.set_halign(Gtk.Align.CENTER)
            icon.set_valign(Gtk.Align.CENTER)

            def draw(area, context, width, height):
                color = area.get_style_context().get_color()
                context.set_source_rgba(color.red, color.green, color.blue, color.alpha)
                context.translate((width - 22) / 2, (height - 22) / 2)
                context.scale(22 / 24, 22 / 24)
                context.set_line_width(1.7 * 24 / 22)
                context.set_line_cap(1)
                context.set_line_join(1)
                kind = area.icon_name
                if kind == "home":
                    for x, y in ((3, 10), (12, 3), (21, 10), (21, 21), (3, 21), (3, 10)):
                        context.line_to(x, y)
                elif kind == "clock":
                    context.arc(12, 12, 9, 0, math.tau)
                    context.stroke()
                    context.move_to(12, 6)
                    context.line_to(12, 12)
                    context.line_to(16, 15)
                elif kind == "gear":
                    for i in range(32):
                        angle = math.tau * i / 32 - math.pi / 2
                        radius = 10 if i % 4 in (0, 1) else 7.7
                        context.line_to(12 + radius * math.cos(angle), 12 + radius * math.sin(angle))
                    context.close_path()
                    context.stroke()
                    context.arc(12, 12, 3.2, 0, math.tau)
                elif kind == "copy":
                    context.move_to(8, 16)
                    context.line_to(5, 16)
                    context.line_to(5, 4)
                    context.line_to(16, 4)
                    context.stroke()
                    context.rectangle(9, 8, 11, 13)
                elif kind == "check":
                    context.move_to(5, 12)
                    context.line_to(10, 17)
                    context.line_to(20, 7)
                elif kind == "microphone":
                    context.arc(12, 7, 3, math.pi, math.tau)
                    context.line_to(15, 12)
                    context.arc(12, 12, 3, 0, math.pi)
                    context.close_path()
                    context.stroke()
                    context.move_to(6, 10)
                    context.line_to(6, 12)
                    context.arc_negative(12, 12, 6, math.pi, 0)
                    context.move_to(12, 18)
                    context.line_to(12, 22)
                    context.move_to(9, 22)
                    context.line_to(15, 22)
                elif kind == "stop":
                    context.rectangle(6, 6, 12, 12)
                elif kind == "cancel":
                    context.move_to(6, 6)
                    context.line_to(18, 18)
                    context.move_to(18, 6)
                    context.line_to(6, 18)
                elif kind == "retry":
                    context.arc(12, 12, 8, -math.pi / 2, math.pi)
                    context.move_to(4, 5)
                    context.line_to(4, 12)
                    context.line_to(10, 12)
                context.stroke()

            icon.set_draw_func(draw)
            return icon

        def icon_button(self, name, label, callback):
            button = Gtk.Button()
            button.add_css_class("icon-button")
            button.set_size_request(44, 44)
            button.set_child(self.line_icon(name))
            button.set_tooltip_text(label)
            button.update_property([Gtk.AccessibleProperty.LABEL], [label])
            button.connect("clicked", lambda _: callback())
            return button

        def display_hotkey(self, hotkey):
            names = {"CTRL": "Ctrl", "SUPER": "Super", "ALT": "Alt", "SHIFT": "Shift"}
            return " + ".join(names.get(key.strip(), key.strip()) for key in hotkey.split("+"))

        def update_hotkey(self, hotkey):
            self.current_hotkey = hotkey
            escaped = GLib.markup_escape_text(hotkey)
            self.shortcut_label.set_markup(
                f'Hold <span foreground="{self.hotkey_color}"><b>{escaped}</b></span> to dictate'
            )

        def build_home(self):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            page = self.box(spacing=40)
            page.add_css_class("overview")
            scroll.set_child(page)
            self.stack.add_named(scroll, "home")
            top = self.box(False, 24)
            top.set_valign(Gtk.Align.START)
            self.service_running = False
            self.status_button = Gtk.Button()
            self.status_button.add_css_class("status-pill")
            self.status_button.connect(
                "clicked", lambda _: self.stop_service() if self.service_running else self.start_service()
            )
            pill = self.box(False, 10)
            self.status_dot = self.box()
            self.status_dot.add_css_class("status-dot")
            self.status_dot.set_size_request(9, 9)
            self.status_dot.set_valign(Gtk.Align.CENTER)
            self.status_label = self.label("Stopped")
            pill.append(self.status_dot)
            pill.append(self.status_label)
            self.status_button.set_child(pill)
            top.append(self.status_button)
            self.service_menu = Gtk.Popover()
            self.service_menu.set_parent(self.status_button)
            self.service_menu.set_position(Gtk.PositionType.BOTTOM)
            self.service_menu.set_has_arrow(False)
            menu = self.box(spacing=4)
            def pause_from_menu():
                self.service_menu.popdown()
                self.toggle_pause()

            self.pause_button = self.button("Pause", pause_from_menu)
            self.pause_button.set_sensitive(False)
            menu.append(self.pause_button)
            self.service_menu.set_child(menu)
            context = Gtk.GestureClick(button=3)
            context.connect("pressed", lambda *_: self.service_menu.popup())
            self.status_button.add_controller(context)
            keyboard = Gtk.EventControllerKey()

            def context_key(_, key, code, modifiers):
                if key == Gdk.KEY_Menu or (key == Gdk.KEY_F10 and modifiers & Gdk.ModifierType.SHIFT_MASK):
                    self.service_menu.popup()
                    return True
                return False

            keyboard.connect("key-pressed", context_key)
            self.status_button.add_controller(keyboard)
            self.shortcut_label = self.label("", "hotkey")
            self.shortcut_label.set_hexpand(True)
            self.shortcut_label.set_xalign(1)
            self.shortcut_label.set_wrap(True)
            self.shortcut_label.set_valign(Gtk.Align.CENTER)
            top.append(self.shortcut_label)
            page.append(top)
            self.recovery = self.box(spacing=12)
            self.recovery.set_visible(False)
            self.status_detail = self.label("", "muted", True)
            self.recovery.append(self.status_detail)
            controls = self.box(False, 8)
            self.retry_button = self.icon_button(
                "retry", "Retry dictation", lambda: self.work(lambda: request("retry"), lambda _: self.refresh())
            )
            self.cancel_button = self.icon_button(
                "cancel", "Cancel recording", lambda: self.work(lambda: request("cancel"), lambda _: self.refresh())
            )
            self.record_button = self.icon_button("microphone", "Record", self.toggle_recording)
            self.record_button.set_visible(self.portable)
            self.record_button.set_sensitive(False)
            # Portable recording and recovery remain available without extra text buttons.
            self.session_controls = controls
            for button in (self.record_button, self.retry_button, self.cancel_button):
                controls.append(button)
            controls.set_valign(Gtk.Align.CENTER)
            top.insert_child_after(controls, self.status_button)
            page.append(self.recovery)
            metrics = self.box(False, 72)
            metrics.add_css_class("overview-metrics")
            self.home_metrics = []
            for title in ("words today", "sessions", "minutes"):
                item = self.box(spacing=8)
                value = self.label("0", "overview-number")
                self.home_metrics.append(value)
                item.append(value)
                item.append(self.label(title, "overview-caption"))
                metrics.append(item)
            page.append(metrics)
            self.recent = self.box(spacing=0)
            self.recent.add_css_class("recent-list")
            self.recent.set_overflow(Gtk.Overflow.HIDDEN)
            seat = Gdk.Display.get_default().get_default_seat()
            if seat and seat.get_capabilities() & Gdk.SeatCapabilities.TOUCH:
                self.recent.add_css_class("touch")
            page.append(self.recent)

        def recent_row(self, row):
            item = self.box(False, 20)
            item.add_css_class("recent-row")
            date = datetime.fromisoformat(row["created_at"]).astimezone()
            timestamp = self.label(date.strftime("%H:%M"), "recent-time")
            timestamp.set_size_request(44, -1)
            timestamp.set_tooltip_text(date.strftime("%b %d, %H:%M"))
            item.append(timestamp)
            text = row["final_transcript"]
            label = self.label(text, "recent-text")
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_width_chars(1)
            label.set_tooltip_text(text)
            item.append(label)
            button = self.icon_button("copy", "Copy dictation", lambda: copied())
            button.add_css_class("recent-copy")
            item.append(button)
            button.feedback_timer = None

            def copied():
                self.copy_text(text, announce=False)
                button.get_child().icon_name = "check"
                button.get_child().queue_draw()
                button.update_property([Gtk.AccessibleProperty.LABEL], ["Copied"])
                button.set_tooltip_text("Copied")
                if button.feedback_timer:
                    GLib.source_remove(button.feedback_timer)

                def restore():
                    button.get_child().icon_name = "copy"
                    button.get_child().queue_draw()
                    button.update_property([Gtk.AccessibleProperty.LABEL], ["Copy dictation"])
                    button.set_tooltip_text("Copy dictation")
                    button.feedback_timer = None
                    return False

                button.feedback_timer = GLib.timeout_add(1400, restore)

            return item

        def build_history(self):
            page = self.page(
                "history",
                "History",
                "Only completed dictations. Local to this device. Never microphone audio.",
            )
            self.history_note = self.label("", "muted", True)
            page.append(self.history_note)
            row = self.box(False)
            self.search = Gtk.SearchEntry(placeholder_text="Search your dictations")
            self.search.set_hexpand(True)
            self.search.connect("search-changed", lambda _: self.refresh())
            row.append(self.search)
            row.append(self.button("Statistics", lambda: self.navigate("stats")))
            row.append(self.button("Export…", self.export_history))
            row.append(self.button("Delete all", self.confirm_delete_all))
            page.append(row)
            self.history_rows = self.box()
            page.append(self.history_rows)

        def build_stats(self):
            page = self.page(
                "stats",
                "Statistics",
                "Your dictation activity.",
            )
            self.stats_labels = {}
            grid = Gtk.Grid(column_spacing=14, row_spacing=14, column_homogeneous=True)
            for index, (key, title) in enumerate(
                (
                    ("today_words", "Words today"),
                    ("week_words", "Words · last 7 days"),
                    ("month_words", "Words this month"),
                    ("words", "Words retained"),
                    ("wpm", "Words / recording minute"),
                    (
                        "latency_ms",
                        "Mean completion time" if self.portable else "Mean output dispatch",
                    ),
                )
            ):
                panel = self.box(spacing=8)
                panel.add_css_class("panel")
                panel.append(self.label(title, "muted"))
                label = self.label("—", "metric")
                self.stats_labels[key] = label
                panel.append(label)
                grid.attach(panel, index % 2, index // 2, 1, 1)
            page.append(grid)
            page.append(self.label("Words over the last seven days", "section-title"))
            self.chart = Gtk.DrawingArea()
            self.chart.set_content_height(170)
            self.chart.set_draw_func(self.draw_chart)
            self.daily = {}
            page.append(self.chart)

        def draw_chart(self, _, context, width, height):
            foreground = self.chart.get_style_context().get_color()
            maximum = max([1, *self.daily.values()])
            column = width / 7
            context.select_font_face("Adwaita Sans")
            context.set_font_size(11)
            for index, (day, words) in enumerate(self.daily.items()):
                left = index * column + 10
                top = (height - 46) * words / maximum
                context.set_source_rgba(foreground.red, foreground.green, foreground.blue, foreground.alpha)
                context.rectangle(left, height - 28 - top, max(1, column - 22), max(1, top))
                context.fill()
                context.move_to(left, height - 34 - top)
                context.show_text(str(words))
                context.set_source_rgba(foreground.red, foreground.green, foreground.blue, foreground.alpha)
                context.move_to(left, height - 8)
                context.show_text(datetime.fromisoformat(day).strftime("%a"))

        def field(self, page, title, widget, description=None):
            group = self.box(spacing=8)
            group.append(self.label(title, "field-title", True))
            widget.update_property([Gtk.AccessibleProperty.LABEL], [title])
            if description:
                group.append(self.label(description, "muted", True))
            group.append(widget)
            page.append(group)
            return widget

        def entry(self, text):
            widget = Gtk.Entry()
            widget.set_text(str(text))
            return widget

        def settings_page(self, name):
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            body = self.box(spacing=40)
            body.add_css_class("sentence-page")
            def adapt(widget, _clock):
                if widget.get_width() < 760:
                    widget.add_css_class("compact-settings")
                else:
                    widget.remove_css_class("compact-settings")
                return True
            body.add_tick_callback(adapt)
            scroll.set_child(body)
            self.stack.add_named(scroll, name)
            return body

        def sentence(self, parent, *parts):
            flow = self.box(False, 0)
            flow.set_layout_manager(SentenceLayout())
            flow.add_css_class("sentence")
            for part in parts:
                if isinstance(part, str):
                    for word in part.split():
                        label = self.label(word)
                        label.set_valign(Gtk.Align.CENTER)
                        flow.append(label)
                else:
                    part.set_valign(Gtk.Align.CENTER)
                    flow.append(part)
            parent.append(flow)

        def token_menu(self, model, names):
            button = Gtk.MenuButton()
            button.set_direction(Gtk.ArrowType.NONE)
            button.add_css_class("token")
            popover = Gtk.Popover()
            items = self.box(spacing=0)
            popover.set_child(items)
            button.set_popover(popover)

            def populate(*_):
                child = items.get_first_child()
                while child:
                    items.remove(child)
                    child = items.get_first_child()
                for index, name in enumerate(names()):
                    def choose(index=index):
                        model.set_selected(index)
                        popover.popdown()
                    items.append(self.button(name, choose, "menu-choice"))
                values = names()
                index = model.get_selected()
                button.set_label(values[index] + " ▾" if index < len(values) else "Choose ▾")

            model.connect("notify::selected", populate)
            model.connect("notify::model", populate)
            populate()
            return button

        def build_settings(self):
            page = self.settings_page("settings")
            self.entries = {}
            self.selecting_preset = True
            self.autosave_source = 0
            self.save_in_flight = False
            self.save_again = False
            self.settings_revision = 0
            self.hotkey = self.entry(self.config.app.hotkey)
            self.record_key = self.button(
                self.config.app.hotkey.title(), self.begin_shortcut, "token"
            )
            controller = Gtk.EventControllerKey()
            controller.connect("key-pressed", self.capture_shortcut)
            controller.connect("key-released", self.release_shortcut)
            self.record_key.add_controller(controller)
            self.recording_key = False
            self.pending_modifiers = []
            self.mic = Gtk.DropDown.new_from_strings(["System default"])
            microphone = self.token_menu(self.mic, lambda: [name for name, _ in self.devices])
            recording = self.box(spacing=12)
            self.sentence(recording, "Hold", self.record_key,
                          "to talk, and listen through", microphone)
            mic_test = self.box(False, 14)
            self.meter_bars = []
            bars = self.box(False, 4)
            bars.set_valign(Gtk.Align.CENTER)
            for height in (6, 12, 17, 10, 22, 16, 9, 19):
                bar = self.box(spacing=0)
                bar.add_css_class("mic-bar")
                bar.set_size_request(3, height)
                bar.set_valign(Gtk.Align.CENTER)
                bars.append(bar)
                self.meter_bars.append(bar)
            mic_test.append(bars)
            self.test_button = self.button("Test mic", self.test_microphone, "text-link")
            mic_test.append(self.test_button)
            recording.append(mic_test)
            page.append(recording)

            providers = self.box(spacing=12)
            self.preset = Gtk.DropDown.new_from_strings(PRESETS)
            self.preset.set_selected(provider_preset(self.config))
            provider = self.token_menu(self.preset, lambda: list(PRESETS))
            self.tidy = Gtk.DropDown.new_from_strings(["off", "lightly", "thoroughly"])
            self.tidy.set_selected(
                0 if not self.config.cleanup.model else
                2 if self.config.cleanup.reasoning_effort in ("medium", "high", "xhigh", "max")
                else 1
            )
            tidy = self.token_menu(self.tidy, lambda: ["off", "lightly", "thoroughly"])
            self.sentence(providers, "Transcribe with", provider, "and tidy the text", tidy)
            status = self.flow()
            self.provider_status_dot = self.label("●", "provider-dot")
            status.append(self.provider_status_dot)
            self.connection_label = self.label("", "settings-muted", True)
            status.append(self.connection_label)
            self.key_setup = self.button("Manage keys", self.open_setup, "text-link")
            status.append(self.key_setup)
            self.check_button = self.button("Check connection", self.check_connection, "text-link")
            status.append(self.check_button)
            providers.append(status)
            page.append(providers)

            self.retention = Gtk.SpinButton.new_with_range(1, 3650, 1)
            self.retention.set_value(self.config.desktop.retention_days)
            self.retention_token = Gtk.MenuButton()
            self.retention_token.set_direction(Gtk.ArrowType.NONE)
            self.retention_token.add_css_class("token")
            days = Gtk.Popover()
            days.set_child(self.retention)
            self.retention_token.set_popover(days)
            self.retention_token.set_label(f"{self.config.desktop.retention_days} days")
            self.login_button = Gtk.Switch()
            self.login_button.add_css_class("settings-switch")
            self.login_button.set_active(entry_path(True).exists())
            self.login_button.update_property([Gtk.AccessibleProperty.LABEL], ["Start at login"])
            self.login_button.connect("notify::active", lambda *_: self.queue_autosave())
            self.sentence(page, "Keep dictations for", self.retention_token,
                          ", and start Caelum at login", self.login_button)

            advanced = self.settings_page("advanced")
            back = self.button("← Settings", lambda: self.navigate("settings"), "text-link")
            back.set_halign(Gtk.Align.START)
            advanced.append(back)
            advanced.append(self.label("Advanced", "advanced-title"))
            rows = self.box(spacing=0)
            rows.set_halign(Gtk.Align.FILL)
            advanced.append(self.clamp(rows, maximum=720, center=False))
            self.inline_values = {}
            for section, key, title in (
                ("stt", "language", "Language"),
                ("stt", "base_url", "Transcription URL"),
                ("stt", "model", "Transcription model"),
                ("stt", "key_env", "Transcription key variable"),
                ("cleanup", "base_url", "Refinement URL"),
                ("cleanup", "model", "Refinement model"),
                ("cleanup", "key_env", "Refinement key variable"),
                ("cleanup", "reasoning_effort", "Reasoning effort"),
            ):
                row = self.box(False, 16)
                row.add_css_class("advanced-row")
                label = self.label(title, wrap=True)
                label.set_hexpand(True)
                row.append(label)
                widget = self.entry(getattr(getattr(self.config, section), key))
                widget.set_width_chars(12)
                widget.set_max_width_chars(32)
                widget.add_css_class("inline-input")
                widget.update_property([Gtk.AccessibleProperty.LABEL], [title])
                self.entries[(section, key)] = widget
                value = Gtk.Stack()
                value.set_valign(Gtk.Align.CENTER)
                display = self.button("", lambda value=value: self.edit_inline(value), "inline-value")
                value.add_named(display, "value")
                value.add_named(widget, "edit")
                self.inline_values[(section, key)] = display
                def changed(entry, display=display, key=key):
                    display.set_label(entry.get_text() or ("auto-detect" if key == "language" else "off"))
                    display.get_child().set_ellipsize(Pango.EllipsizeMode.END)
                    display.get_child().set_max_width_chars(30)
                    self.provider_edited(entry)
                widget.connect("changed", changed)
                changed(widget)
                widget.connect("activate", lambda _, value=value: value.set_visible_child_name("value"))
                focus = Gtk.EventControllerFocus()
                focus.connect("leave", lambda _, value=value: value.set_visible_child_name("value"))
                widget.add_controller(focus)
                row.append(value)
                rows.append(row)
            self.history_enabled = Gtk.CheckButton(label="Save dictation history")
            self.history_enabled.set_active(self.config.desktop.history_enabled)
            history_row = self.box(False)
            history_row.add_css_class("advanced-row")
            history_row.append(self.history_enabled)
            rows.append(history_row)
            self.update_automatic = Gtk.Switch()
            self.update_automatic.set_active(self.config.desktop.check_updates)
            self.update_automatic.add_css_class("settings-switch")
            self.update_automatic.update_property(
                [Gtk.AccessibleProperty.LABEL], ["Check for updates when Caelum opens"]
            )
            automatic = self.box(False, 16)
            automatic.add_css_class("advanced-row")
            label = self.label("Check for updates when Caelum opens", wrap=True)
            label.set_hexpand(True)
            automatic.append(label)
            self.update_automatic.set_valign(Gtk.Align.CENTER)
            automatic.append(self.update_automatic)
            rows.append(automatic)
            key_row = self.flow()
            key_row.add_css_class("advanced-row")
            key_label = self.label("Key to manage", wrap=True)
            key_label.set_hexpand(True)
            key_row.append(key_label)
            self.setup_key_choice = Gtk.DropDown()
            key_row.append(self.setup_key_choice)
            key_row.append(self.button("Manage key", self.manage_key, "text-link"))
            rows.append(key_row)
            self.refresh_key_choices()
            actions = self.flow()
            actions.append(self.button("Add to app launcher", lambda: self.work(
                lambda: install(self.path),
                lambda _: self.message("Caelum added to your app launcher.")), "text-link"))
            self.update_discard = self.button("Discard queued update", self.discard_update, "text-link")
            actions.append(self.update_discard)
            advanced.append(actions)
            spacer = self.box()
            spacer.set_vexpand(True)
            page.append(spacer)
            self.build_updates(page)
            self.selecting_preset = False
            self.preset.connect("notify::selected", self.select_preset)
            self.tidy.connect("notify::selected", self.select_tidy)
            self.mic.connect("notify::selected", lambda *_: self.queue_autosave())
            self.hotkey.connect("changed", lambda *_: self.queue_autosave())
            self.retention.connect("value-changed", self.retention_changed)
            self.history_enabled.connect("toggled", lambda *_: self.queue_autosave())
            self.update_automatic.connect("notify::active", lambda *_: self.queue_autosave())
            self.show_provider_status(self.key_status(self.config))

        def refresh_key_choices(self):
            draft = self.provider_draft()
            self.setup_key_names = list(dict.fromkeys(
                [draft.stt.key_env] + ([draft.cleanup.key_env] if draft.cleanup.model else [])
            ))
            self.setup_key_choice.set_model(Gtk.StringList.new(self.setup_key_names))
            self.setup_key_choice.set_selected(0)

        def manage_key(self):
            # Use current Advanced edits when opening provider setup.
            try:
                self.config = self.settings_draft()
            except ValueError as error:
                self.message(str(error))
                return
            self.open_setup(self.setup_key_names[self.setup_key_choice.get_selected()])

        def edit_inline(self, value):
            value.set_visible_child_name("edit")
            value.get_visible_child().grab_focus()

        def retention_changed(self, *_):
            self.retention_token.set_label(f"{self.retention.get_value_as_int()} days")
            self.queue_autosave()

        def select_tidy(self, *_):
            if self.selecting_preset:
                return
            selected = self.tidy.get_selected()
            self.selecting_preset = True
            model = self.entries[("cleanup", "model")]
            if not selected:
                self.refinement_model = model.get_text() or getattr(self, "refinement_model", "")
                model.set_text("")
            elif not model.get_text():
                model.set_text(getattr(self, "refinement_model", "") or "openai/gpt-oss-20b")
            self.entries[("cleanup", "reasoning_effort")].set_text(
                ("", "minimal", "high")[selected]
            )
            self.selecting_preset = False
            self.provider_edited(None)

        def build_updates(self, page):
            from .updates import cache_dir, installed

            footer = self.flow()
            footer.add_css_class("settings-footer")
            version = self.box(False, 4)
            version.append(self.label(f"Caelum {display_version()} ·", "settings-muted"))
            self.update_status = self.label("up to date", "settings-muted", True)
            version.append(self.update_status)
            self.update_check = self.button("Check", self.check_updates, "text-link")
            self.update_check.set_sensitive(bool(installed()))
            version.append(self.update_check)
            self.update_download = self.button(
                "Update & restart", self.prompt_update, "text-link"
            )
            self.update_download.set_visible(False)
            version.append(self.update_download)
            footer.append(version)
            self.save_status = self.label("Saved automatically", "settings-muted", True)
            self.save_status.set_hexpand(True)
            footer.append(self.save_status)
            footer.append(self.button("Advanced →", lambda: self.navigate("advanced"), "text-link"))
            page.append(footer)
            pending = (cache_dir() / "pending").is_dir()
            self.update_discard.set_visible(pending)
            self.update_discard.set_sensitive(pending)
            if pending:
                self.update_status.set_text("Update queued")
                self.update_check.set_sensitive(False)
                self.update_download.set_visible(True)
                self.update_download.set_sensitive(True)

        def update_work(self, operation, done):
            if self.update_busy:
                return
            self.update_busy = True
            for button in (self.update_check, self.update_download, self.update_discard):
                button.set_sensitive(False)

            def perform():
                try:
                    return operation(), None
                except Exception as error:
                    message = (
                        str(error)
                        if isinstance(error, (ValueError, RuntimeError))
                        else (
                            "Update failed or authorization was cancelled. A queued update is kept; "
                            "retry on next launch or discard it. Dictation may need starting again."
                        )
                    )
                    return None, message

            def finished(result):
                from .updates import cache_dir, installed

                self.update_busy = False
                pending = (cache_dir() / "pending").is_dir()
                self.update_check.set_sensitive(bool(installed()) and not pending)
                self.update_download.set_sensitive(bool(self.available_update) or pending)
                self.update_discard.set_sensitive(pending)
                self.update_discard.set_visible(pending)
                self.update_download.set_visible(bool(self.available_update) or pending)
                self.update_check.set_visible(not self.available_update and not pending)
                value, error = result
                if error:
                    self.restarting_update = False
                    self.stack.set_sensitive(True)
                    self.theme_button.set_sensitive(True)
                    self.update_status.set_text(error)
                    return
                done(value)

            self.work(perform, finished)

        def begin_updates(self):
            from .updates import cache_dir, installed

            if not installed():
                return
            if (cache_dir() / "pending").is_dir():
                self.update_status.set_text(
                    "Installing queued update. Authorize the system prompt…"
                )

                def applied(running):
                    if running:
                        subprocess.Popen(
                            [
                                sys.executable,
                                "-m",
                                "caelum.cli",
                                "--config",
                                str(self.path),
                                "serve",
                            ],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    os.execv(
                        sys.executable,
                        [sys.executable, "-m", "caelum.cli", "--config", str(self.path), "app"],
                    )

                if getattr(self, "setup_window", None):
                    self.setup_window.finish_setup()
                    self.navigate("home")
                if self.autosave_source:
                    GLib.source_remove(self.autosave_source)
                    self.autosave_source = 0
                try:
                    draft = self.settings_draft()
                except ValueError as error:
                    self.update_status.set_text(f"Fix settings before restarting: {error}")
                    return

                login = self.login_button.get_active()
                self.restarting_update = True
                self.stack.set_sensitive(False)
                self.theme_button.set_sensitive(False)

                def install_update():
                    # Wait for an already-running autosave before the final draft write.
                    if getattr(self, "settings_future", None):
                        self.settings_future.result()
                    save(draft, self.path)
                    if entry_path(True).exists() != login:
                        install(self.path, autostart=True, enabled=login)
                    return install_queued_update()

                self.update_work(install_update, applied)
            elif self.config.desktop.check_updates:
                self.check_updates()

        def check_updates(self):
            from .updates import check

            self.update_status.set_text("Checking for updates…")

            def checked(update):
                self.available_update = update
                self.update_download.set_sensitive(bool(update))
                self.update_status.set_text(
                    "Update available" if update else "up to date"
                )
                self.update_download.set_visible(bool(update))
                self.update_check.set_visible(not update)

            self.update_work(check, checked)

        def prompt_update(self):
            from .updates import cache_dir

            if (cache_dir() / "pending").is_dir() and not self.update_busy:
                self.begin_updates()
                return
            if not self.available_update or self.update_busy:
                return
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE,
                text=f"Download Caelum {self.available_update['version']}?",
                secondary_text=(
                    "The signed package will be downloaded and installed with administrator "
                    "authorization, then Caelum will restart automatically. "
                    "Finish any active dictation first. Your settings, keys, and history are kept."
                ),
            )
            dialog.add_button("Later", Gtk.ResponseType.CANCEL)
            dialog.add_button("Update & restart", Gtk.ResponseType.ACCEPT)
            dialog.set_default_response(Gtk.ResponseType.CANCEL)

            def responded(window, response):
                window.destroy()
                if response == Gtk.ResponseType.ACCEPT:
                    from .updates import stage

                    self.update_status.set_text("Downloading and verifying update…")
                    self.update_work(
                        lambda: stage(self.available_update),
                        lambda version: self.begin_updates(),
                    )

            dialog.connect("response", responded)
            dialog.present()

        def discard_update(self):
            from .updates import discard_pending

            self.available_update = None
            self.update_work(
                discard_pending,
                lambda _: self.update_status.set_text("Queued update discarded."),
            )

        def open_setup(self, key_name=None):
            from .onboarding_ui import show

            try:
                show(self, key_name=key_name)
            except (OSError, RuntimeError, ValueError):
                self.message(
                    "Could not open setup. Check permissions on your Caelum config directory."
                )

        def sync_setup_settings(self):
            self.selecting_preset = True
            for (section, key), widget in self.entries.items():
                widget.set_text(str(getattr(getattr(self.config, section), key)))
            self.preset.set_selected(provider_preset(self.config))
            self.tidy.set_selected(
                0 if not self.config.cleanup.model else
                2 if self.config.cleanup.reasoning_effort in ("medium", "high", "xhigh", "max")
                else 1
            )
            self.selecting_preset = False
            self.history_enabled.set_active(self.config.desktop.history_enabled)
            self.hotkey.set_text(self.config.app.hotkey)
            self.record_key.set_label(self.config.app.hotkey.title())
            self.retention.set_value(self.config.desktop.retention_days)
            self.syncing_setup = True
            self.set_devices([(name, value) for name, value in self.devices if value is not None])
            self.syncing_setup = False
            self.show_provider_status(self.key_status(self.config))
            self.connection_generation = getattr(self, "connection_generation", 0) + 1
            self.refresh_key_choices()

        def key_status(self, config):
            for title, provider in (("Transcription", config.stt), ("Refinement", config.cleanup)):
                if not provider.model:
                    continue
                status = credential_status(provider.key_env)
                if "missing" in status or "unavailable" in status:
                    return f"{title}: {provider.key_env} {status.split(';')[0]}"
            return "Key found"

        def show_provider_status(self, text):
            # Keep the first actionable failure; successful checks fit on one short line.
            lines = text.splitlines()
            problem = next((line for line in lines if "connected" not in line
                            and "off (raw" not in line), None)
            text = problem or "Connected"
            missing = "missing" in text or "key unavailable" in text
            okay = text in ("Key found", "Connected")
            self.connection_label.set_text(text)
            self.provider_status_dot.remove_css_class("warning")
            self.provider_status_dot.remove_css_class("error")
            if not okay:
                self.provider_status_dot.add_css_class("warning" if missing or "Checking" in text else "error")
            self.key_setup.set_visible(missing)

        def provider_draft(self):
            updated = deepcopy(self.config)
            for (section, key), widget in self.entries.items():
                setattr(getattr(updated, section), key, widget.get_text().strip())
            return updated

        def provider_edited(self, _):
            if getattr(self, "selecting_preset", False):
                return
            self.selecting_preset = True
            self.preset.set_selected(provider_preset(self.provider_draft()))
            self.tidy.set_selected(
                0 if not self.entries[("cleanup", "model")].get_text() else
                2 if self.entries[("cleanup", "reasoning_effort")].get_text()
                in ("medium", "high", "xhigh", "max") else 1
            )
            self.selecting_preset = False
            self.connection_generation = getattr(self, "connection_generation", 0) + 1
            self.show_provider_status(self.key_status(self.provider_draft()))
            self.refresh_key_choices()
            self.queue_autosave()

        def select_preset(self, *_):
            if getattr(self, "selecting_preset", False):
                return
            selected = self.preset.get_selected()
            if selected == 2:
                self.navigate("advanced")
                return
            updated = apply_provider_preset(self.provider_draft(), selected)
            if updated.cleanup.model:
                updated.cleanup.reasoning_effort = "minimal"
            self.selecting_preset = True
            for (section, key), widget in self.entries.items():
                widget.set_text(str(getattr(getattr(updated, section), key)))
            self.tidy.set_selected(0 if not updated.cleanup.model else 1)
            self.selecting_preset = False
            self.connection_generation = getattr(self, "connection_generation", 0) + 1
            self.show_provider_status(self.key_status(updated))
            self.refresh_key_choices()
            self.queue_autosave()

        def check_connection(self):
            updated = self.provider_draft()
            generation = getattr(self, "connection_generation", 0)
            self.check_button.set_sensitive(False)
            self.show_provider_status("Checking connection…")

            def checked(text):
                self.check_button.set_sensitive(True)
                if generation == getattr(self, "connection_generation", 0):
                    self.show_provider_status(text)

            def check():
                try:
                    return asyncio.run(connection_status(updated))
                finally:
                    GLib.idle_add(self.check_button.set_sensitive, True)

            self.work(check, checked)

        def set_devices(self, devices):
            index = self.mic.get_selected()
            selected = self.devices[index][1] if index < len(self.devices) else self.config.app.microphone
            if getattr(self, "syncing_setup", False):
                selected = self.config.app.microphone
            self.devices = [("System default", None), *dict.fromkeys(devices)]
            if selected is not None and not any(value == selected for _, value in self.devices):
                self.devices.append((f"{selected} · configured, not detected", selected))
            was_selecting = self.selecting_preset
            self.selecting_preset = True
            self.mic.set_model(Gtk.StringList.new([name for name, _ in self.devices]))
            self.mic.set_selected(
                next(
                    (index for index, (_, value) in enumerate(self.devices) if value == selected), 0
                )
            )

            self.selecting_preset = was_selecting

        def begin_shortcut(self):
            self.recording_key = True
            self.pending_modifiers = []
            self.pending_shortcut = None
            self.record_key.set_label("Press keys…")
            self.record_key.grab_focus()

        def capture_shortcut(self, _, keyval, keycode, state):
            if not self.recording_key:
                return False
            if keyval == Gdk.KEY_Escape:
                self.recording_key = False
                self.record_key.set_label(self.hotkey.get_text().title())
                return True
            name = Gdk.keyval_name(keyval) or ""
            modifiers = [
                name
                for mask, name in (
                    (Gdk.ModifierType.SUPER_MASK, "SUPER"),
                    (Gdk.ModifierType.CONTROL_MASK, "CTRL"),
                    (Gdk.ModifierType.ALT_MASK, "ALT"),
                    (Gdk.ModifierType.SHIFT_MASK, "SHIFT"),
                )
                if state & mask
            ]
            modifier_key = {
                "Control": "CTRL",
                "Super": "SUPER",
                "Alt": "ALT",
                "Shift": "SHIFT",
            }.get(name.removesuffix("_L").removesuffix("_R"))
            if modifier_key:
                self.pending_modifiers = list(dict.fromkeys([*modifiers, modifier_key]))
                return True
            if modifiers:
                self.pending_shortcut = " + ".join([*modifiers, name.upper()])
            return True

        def release_shortcut(self, _, keyval, keycode, state):
            if not self.recording_key:
                return
            combo = self.pending_shortcut or (
                " + ".join(self.pending_modifiers) if len(self.pending_modifiers) >= 2 else None
            )
            if combo:
                self.recording_key = False
                self.hotkey.set_text(combo)
                self.record_key.set_label(combo.title())

        def set_mic_level(self, value):
            for index, bar in enumerate(self.meter_bars):
                height = 4 + int(value * (12 + ((index * 7) % 19)))
                bar.set_size_request(3, height)
            return False

        def test_microphone(self):
            self.test_button.set_sensitive(False)
            device = self.devices[self.mic.get_selected()][1]

            def test():
                import time

                import numpy as np
                import sounddevice as sound

                def level(data, frames, timing, status):
                    value = min(1, float(np.sqrt(np.mean(data**2))) * 8)
                    GLib.idle_add(self.set_mic_level, value)

                try:
                    try:
                        status = request("status")
                    except (FileNotFoundError, ConnectionRefusedError):
                        status = None
                    if status and status["state"] in ("starting", "listening", "recording"):
                        raise RuntimeError("Finish recording before testing the microphone")
                    with sound.InputStream(device=device, channels=1, callback=level):
                        time.sleep(3)
                finally:
                    GLib.idle_add(self.test_button.set_sensitive, True)
                    GLib.idle_add(self.set_mic_level, 0)

            self.work(test)

        def queue_autosave(self):
            if self.selecting_preset or self.closed or getattr(self, "restarting_update", False):
                return
            self.settings_revision += 1
            if self.autosave_source:
                GLib.source_remove(self.autosave_source)
            self.save_status.set_text("Saving…")
            self.autosave_source = GLib.timeout_add(400, self.save_settings)

        def settings_draft(self):
            updated = self.provider_draft()
            updated.app.hotkey = self.hotkey.get_text().strip().upper()
            updated.app.microphone = self.devices[self.mic.get_selected()][1]
            updated.desktop.history_enabled = self.history_enabled.get_active()
            updated.desktop.retention_days = self.retention.get_value_as_int()
            updated.desktop.check_updates = self.update_automatic.get_active()
            updated.desktop.theme = ("system", "light", "dark")[self.theme.get_selected()]
            return validate(updated)

        def save_settings(self):
            if self.autosave_source:
                GLib.source_remove(self.autosave_source)
                self.autosave_source = 0
            if self.save_in_flight:
                self.save_again = True
                return False
            try:
                updated = self.settings_draft()
            except ValueError as error:
                self.save_status.set_text(f"Not saved: {error}")
                return False
            revision = self.settings_revision
            login = self.login_button.get_active()
            self.save_in_flight = True

            def persist():
                try:
                    save(updated, self.path)
                    if entry_path(True).exists() != login:
                        install(self.path, autostart=True, enabled=login)
                    try:
                        request("reload")
                    except (FileNotFoundError, ConnectionRefusedError):
                        pass
                    except (RuntimeError, OSError) as error:
                        return f"Saved; service not updated: {error}"
                    return None
                except (ValueError, RuntimeError, OSError) as error:
                    return f"Could not save: {error}"

            def saved(error):
                self.save_in_flight = False
                if not error or error.startswith("Saved;"):
                    self.config = updated
                    if not self.portable:
                        self.shortcut_label.set_text(updated.app.hotkey)
                if getattr(self, "restarting_update", False):
                    return
                if self.save_again or revision != self.settings_revision:
                    self.save_again = False
                    self.save_settings()
                    return
                self.save_status.set_text(error or "Saved")
                if not error:
                    def reset():
                        if revision == self.settings_revision:
                            self.save_status.set_text("Saved automatically")
                        return False
                    GLib.timeout_add(1800, reset)
                self.refresh()

            self.settings_future = self.work(persist, saved)
            return False

        def change_theme(self, *_):
            self.config.desktop.theme = ("system", "light", "dark")[self.theme.get_selected()]
            self.apply_theme()
            self.queue_autosave()

        def apply_theme(self, *_):
            settings = Gtk.Settings.get_default()
            scheme = settings.find_property("gtk-interface-color-scheme")
            system_dark = (
                settings.get_property("gtk-interface-color-scheme") == Gtk.InterfaceColorScheme.DARK
                if scheme else settings.get_property("gtk-theme-name").lower().endswith("-dark")
            )
            selected = self.config.desktop.theme
            dark = selected == "dark" or selected == "system" and system_dark
            self.theme_button.set_tooltip_text(f"Appearance: {selected.title()}")
            palette = (
                ("#0B0B0D", "#151517", "#F2F2F3", "#9A9AA3", "#26262B", "#26262B", "#252528", "#202023", "#6FD3A4", "#CDA764")
                if dark else
                ("#F6F5F2", "#FFFFFF", "#1B1B1A", "#5E5D58", "#E4E2DC", "#EEECE6", "#E9E7E0", "#F1F0EC", "#2F6F57", "#9A6A23")
            )
            self.hotkey_color = palette[2]
            if hasattr(self, "current_hotkey"):
                self.update_hotkey(self.current_hotkey)
            names = ("page", "surface", "ink", "muted", "border", "divider", "active", "fill", "accent", "amber")
            css = "\n".join(f"@define-color caelum_{name} {value};" for name, value in zip(names, palette, strict=True))
            css += "\n" + Path(__file__).with_name("desktop.css").read_text()
            if dark:
                css += """
                .caelum .sentence-page button.token,
                .caelum .sentence-page menubutton.token > button {
                  background: #16251E; color: #6FD3A4;
                }
                .caelum .sentence-page .provider-dot.error { color: #FF8E8E; }
                """
            if hasattr(self, "css"):
                Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(), self.css)
            self.css = Gtk.CssProvider()
            if hasattr(self.css, "load_from_string"):
                self.css.load_from_string(css)
            else:
                self.css.load_from_data(css.encode())
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            if not hasattr(self, "theme_signals"):
                self.theme_signals = [settings.connect("notify::gtk-theme-name", self.apply_theme)]
                if scheme:
                    self.theme_signals.append(settings.connect("notify::gtk-interface-color-scheme", self.apply_theme))
            self.chart.queue_draw()

        def toggle_recording(self):
            self.record_button.set_sensitive(False)
            self.work(lambda: request("toggle"), lambda _: self.refresh())

        def start_service(self):
            if self.process and self.process.poll() is None:
                return
            self.process = subprocess.Popen(
                [sys.executable, "-m", "caelum.cli", "--config", str(self.path), "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.message(
                "Starting dictation… If it cannot start, open Settings and check the key, microphone, and shortcut."
            )

        def stop_service(self):
            self.work(
                lambda: request("shutdown"),
                lambda _: self.message("Dictation stopped. Pending audio discarded."),
            )

        def toggle_pause(self):
            self.work(
                lambda: request("resume" if self.paused else "pause"), lambda _: self.refresh()
            )

        def refresh(self):
            if self.closed:
                return False
            self.refresh_generation += 1
            if self.refreshing:
                return True
            self.refreshing = True
            generation = self.refresh_generation
            query = self.search.get_text()

            def read():
                try:
                    try:
                        status = request("status")
                    except (OSError, RuntimeError):
                        status = None
                    return (
                        status,
                        self.history.read(query),
                        self.history.read(limit=3),
                        self.history.summary(),
                    )
                finally:
                    GLib.idle_add(self.end_refresh, generation)

            self.work(read, self.render_data)
            return True

        def end_refresh(self, generation):
            self.refreshing = False
            if generation != self.refresh_generation:
                self.refresh()
            return False

        def clear(self, box):
            while child := box.get_first_child():
                box.remove(child)

        def render_data(self, data):
            status, rows, recent, summary = data
            self.service_running = bool(status)
            self.paused = bool(status and status.get("paused", False))
            state = status.get("state", "hidden") if status else "stopped"
            title, detail = service_presentation(status)
            if not status:
                pill_title = "Stopped"
            elif self.paused:
                pill_title = "Paused"
            elif state in ("starting", "listening", "recording"):
                pill_title = "Listening"
            elif state in ("processing", "refining"):
                pill_title = "Processing"
            elif state == "error":
                pill_title = title
            else:
                pill_title = "Ready"
            self.status_label.set_text(pill_title)
            for name in ("ready", "paused", "stopped"):
                self.status_dot.remove_css_class(name)
            self.status_dot.add_css_class("paused" if self.paused else "ready" if status and state != "error" else "stopped")
            action = "Stop service" if status else "Start service"
            self.status_button.set_tooltip_text(f"{action} · Right-click or Shift+F10 for pause/resume")
            self.status_button.update_property([Gtk.AccessibleProperty.LABEL], [f"{action} · {pill_title}"])
            self.status_detail.set_text(detail if state == "error" else "")
            self.status_detail.set_visible(state == "error")
            hotkey = self.display_hotkey(status.get("hotkey", self.config.app.hotkey) if status else self.config.app.hotkey)
            self.update_hotkey(hotkey)
            if status and status.get("storage_error"):
                self.message("Dictation works, but history could not be saved. Check disk permissions.")
            elif not status and self.process and self.process.poll() is not None and self.process.returncode:
                self.message("Service could not start. Open Settings to check credentials and desktop access.")
            retry_available = (
                bool(status) and status["state"] == "error" and status.get("pending_audio", False)
            )
            self.retry_button.set_visible(retry_available)
            self.cancel_button.set_visible(
                bool(status)
                and (
                    status.get("pending_audio", False)
                    or status["state"]
                    in ("starting", "listening", "recording", "processing", "refining")
                )
            )
            self.record_button.set_visible(self.portable and not retry_available)
            self.record_button.set_sensitive(
                bool(status)
                and not self.paused
                and status["state"] not in ("processing", "refining")
                and not status.get("pending_audio", False)
            )
            record_label = "Finish recording" if state in ("listening", "recording", "starting") else "Record"
            self.record_button.get_child().icon_name = "stop" if record_label == "Finish recording" else "microphone"
            self.record_button.get_child().queue_draw()
            self.record_button.set_tooltip_text(record_label)
            self.record_button.update_property([Gtk.AccessibleProperty.LABEL], [record_label])
            self.cancel_button.update_property([Gtk.AccessibleProperty.LABEL], ["Discard recording" if retry_available else "Cancel recording"])
            self.cancel_button.set_tooltip_text("Discard recording" if retry_available else "Cancel recording")
            self.session_controls.set_visible(self.portable or self.cancel_button.get_visible() or retry_available)
            self.recovery.set_visible(state == "error")
            self.pause_button.set_sensitive(bool(status))
            self.pause_button.set_label("Resume" if self.paused else "Pause")
            self.history_note.set_text(
                f"Saved automatically on this device · Kept for {self.config.desktop.retention_days} days"
                if self.config.desktop.history_enabled
                else "History saving is off. Existing entries can still be deleted or exported."
            )
            for widget, value in zip(
                self.home_metrics,
                (
                    summary["today_words"],
                    summary["sessions"],
                    f"{summary['duration_ms'] / 60000:.1f}",
                ),
                strict=True,
            ):
                widget.set_text(str(value))
            signature = (rows, recent, self.search.get_text(), self.config.desktop.history_enabled, hotkey)
            changed = signature != self.history_signature
            if changed:
                self.history_signature = signature
                self.clear(self.recent)
                self.clear(self.history_rows)
            if changed and not rows:
                message = (
                    "No matching dictations."
                    if self.search.get_text()
                    else ("No dictations yet." if self.config.desktop.history_enabled
                          else "History saving is off. New dictations are not saved.")
                )
                self.history_rows.append(self.label(message, "muted", True))
            for row in recent if changed else []:
                self.recent.append(self.recent_row(row))
            if changed and not recent:
                empty = self.label(f"Nothing yet. Hold {hotkey} and start talking.", "recent-empty", True)
                self.recent.append(empty)
            for row in rows if changed else []:
                self.history_rows.append(self.history_card(row))
            for key, widget in self.stats_labels.items():
                value = summary[key]
                widget.set_text(
                    f"{value / 1000:.2f} s"
                    if key == "latency_ms"
                    else f"{value:.0f}"
                    if key == "wpm"
                    else f"{value:,}"
                )
            self.daily = summary["daily"]
            self.chart.queue_draw()

        def history_card(self, row, compact=False):
            card = self.box(spacing=10)
            card.add_css_class("panel")
            date = datetime.fromisoformat(row["created_at"]).astimezone().strftime("%b %d · %H:%M")
            card.append(
                self.label(
                    f"{date}    {row['word_count']} words    {row['duration_ms'] / 1000:.0f}s",
                    "muted",
                )
            )
            text = row["final_transcript"]
            label = self.label(
                (text[:160] + "…") if compact and len(text) > 160 else text, wrap=True
            )
            label.set_selectable(True)
            card.append(label)
            actions = self.flow()
            actions.append(self.button("Copy text", lambda: self.copy_text(text)))
            if not compact:
                actions.append(
                    self.button(
                        "Delete",
                        lambda: self.work(
                            lambda: self.history.delete(row["id"]), lambda _: self.refresh()
                        ),
                    )
                )
                if row["copied"] or not row["refined"]:
                    actions.append(
                        self.label(
                            "Clipboard recovery" if row["copied"] else "Unrefined transcript",
                            "muted",
                        )
                    )
            if not row["refined"]:
                card.append(
                    self.label(
                        "Raw transcription · refinement skipped or unavailable", "muted", True
                    )
                )
            card.append(actions)
            return card

        def copy_text(self, text, announce=True):
            self.window.get_clipboard().set(text)
            if announce:
                self.message("Copied to clipboard. Clipboard managers may retain this text.")

        def confirm_delete_all(self):
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                text="Delete all saved dictations?",
                secondary_text="This permanently deletes local transcripts and "
                "recalculates all statistics. Clipboard copies and exports are not erased.",
                buttons=Gtk.ButtonsType.CANCEL,
            )
            dialog.add_button("Delete all", Gtk.ResponseType.ACCEPT)
            dialog.set_default_response(Gtk.ResponseType.CANCEL)

            def response(widget, result):
                widget.destroy()
                if result == Gtk.ResponseType.ACCEPT:
                    self.work(self.history.delete, lambda _: self.refresh())

            dialog.connect("response", response)
            dialog.present()

        def export_history(self):
            dialog = Gtk.FileChooserNative.new(
                "Export sensitive transcript history",
                self.window,
                Gtk.FileChooserAction.SAVE,
                "Export sensitive text",
                "Cancel",
            )
            dialog.set_current_name("caelum-history.jsonl")
            self.message(
                "Exports contain private transcripts in plain text. Choose a trusted "
                "location. Deleting Caelum history will not delete exported copies."
            )

            def response(widget, result):
                if result == Gtk.ResponseType.ACCEPT:
                    destination = widget.get_file().get_path()
                    if destination:
                        self.work(
                            lambda: self.history.export(destination),
                            lambda _: self.message("History exported. Keep this file private."),
                        )
                widget.destroy()

            dialog.connect("response", response)
            dialog.show()

        def shutdown(self, _):
            self.closed = True
            if getattr(self, "setup_window", None):
                self.setup_window.finish_setup()
            # Drain a pending debounce before the window exits. Wait for older writes first.
            if hasattr(self, "autosave_source"):
                if self.autosave_source:
                    GLib.source_remove(self.autosave_source)
                self.pool.shutdown(wait=True)
                try:
                    updated = self.settings_draft()
                    save(updated, self.path)
                    login = self.login_button.get_active()
                    if entry_path(True).exists() != login:
                        install(self.path, autostart=True, enabled=login)
                    try:
                        request("reload")
                    except (OSError, RuntimeError):
                        pass
                except (ValueError, OSError, RuntimeError):
                    pass  # Invalid inline drafts never replace the last valid configuration.
            self.closed = True
            if hasattr(self, "theme_signals"):
                for handler in self.theme_signals:
                    Gtk.Settings.get_default().disconnect(handler)
            if hasattr(self, "service_menu"):
                self.service_menu.unparent()
            if hasattr(self, "timer"):
                GLib.source_remove(self.timer)
            self.pool.shutdown(wait=False, cancel_futures=True)

    return Desktop().run([])
