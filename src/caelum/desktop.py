"""Native GTK desktop shell; slow work stays outside the GTK main thread."""

import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .config import config_path, load, save
from .history import History
from .launcher import entry_path, install


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


def microphones():
    import sounddevice as sound

    return [
        (device["name"], device["name"])
        for device in sound.query_devices()
        if device["max_input_channels"] > 0
    ]


def run(path=None, *, on_activate=None):
    if os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("GDK_BACKEND", "wayland")
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, GLib, Gtk

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
            self.config.desktop.theme = "dark"
            self.history = History(self.path)
            self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="caelum-desktop")
            self.process = None
            self.refreshing = False
            self.closed = False
            self.refresh_generation = 0
            self.devices = [("System default", None)]
            self.history_signature = None
            self.paused = False
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

        def activate(self, _):
            if hasattr(self, "window"):
                self.window.present()
                return
            self.window = Gtk.ApplicationWindow(application=self, title="Caelum")
            self.window.set_default_size(1080, 760)
            self.window.set_size_request(820, 600)
            self.window.add_css_class("caelum")
            header = Gtk.HeaderBar()
            # Keep the brand above the sidebar, independent of the centered title slot.
            header.set_title_widget(Gtk.Box())
            self.brand = self.label("Caelum", "wordmark")
            header.pack_start(self.brand)
            self.window.set_titlebar(header)
            outer = self.box(False, 0)
            self.navigation = self.box(spacing=6)
            navigation = self.navigation
            navigation.add_css_class("navigation")
            navigation.set_size_request(208, -1)
            self.sidebar_toggle = Gtk.ToggleButton(active=True)
            self.sidebar_toggle.set_icon_name("sidebar-show-symbolic")
            self.sidebar_toggle.add_css_class("sidebar-toggle")
            self.sidebar_toggle.set_halign(Gtk.Align.START)
            self.sidebar_toggle.set_tooltip_text("Collapse sidebar")
            self.sidebar_toggle.update_property(
                [Gtk.AccessibleProperty.LABEL], ["Collapse sidebar"]
            )
            self.sidebar_toggle.connect("toggled", self.toggle_sidebar)
            navigation.append(self.sidebar_toggle)
            self.stack = Gtk.Stack()
            self.stack.set_hexpand(True)
            self.stack.set_vexpand(True)
            self.nav_buttons = {}
            self.nav_labels = []
            for name, title, icon in (
                ("home", "Overview", "go-home-symbolic"),
                ("history", "History", "document-open-recent-symbolic"),
                ("stats", "Statistics", "view-grid-symbolic"),
                ("settings", "Settings", "preferences-system-symbolic"),
            ):
                button = Gtk.ToggleButton()
                button.add_css_class("nav-item")
                button.connect("clicked", lambda _, name=name: self.navigate(name))
                row = self.box(False, 12)
                row.append(Gtk.Image.new_from_icon_name(icon))
                label = self.label(title)
                row.append(label)
                button.set_child(row)
                button.set_tooltip_text(title)
                button.update_property([Gtk.AccessibleProperty.LABEL], [title])
                self.nav_labels.append(label)
                self.nav_buttons[name] = button
                navigation.append(button)
            spacer = self.box()
            spacer.set_vexpand(True)
            navigation.append(spacer)
            self.sidebar_footer = self.label("Your voice.\nYour workspace.", "muted", True)
            navigation.append(self.sidebar_footer)
            outer.append(navigation)
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
            self.timer = GLib.timeout_add_seconds(3, self.refresh)
            self.work(microphones, self.set_devices)
            if on_activate:
                on_activate(self)

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

        def toggle_sidebar(self, toggle):
            expanded = toggle.get_active()
            self.navigation.set_size_request(208 if expanded else 88, -1)
            for label in self.nav_labels:
                label.set_visible(expanded)
            self.sidebar_footer.set_visible(expanded)
            action = "Collapse sidebar" if expanded else "Expand sidebar"
            toggle.set_tooltip_text(action)
            toggle.update_property([Gtk.AccessibleProperty.LABEL], [action])
            toggle.set_icon_name("sidebar-show-symbolic" if expanded else "sidebar-hide-symbolic")

        def navigate(self, name):
            self.stack.set_visible_child_name(name)
            for key, button in self.nav_buttons.items():
                button.set_active(key == name)
                if key == name:
                    button.add_css_class("selected")
                else:
                    button.remove_css_class("selected")

        def message(self, text):
            self.notice.set_text(text)
            self.notice.set_visible(bool(text))

        def build_home(self):
            page = self.page(
                "home", "Overview", "Hold your shortcut to speak. Release to insert your words."
            )
            hero = self.box(spacing=18)
            hero.add_css_class("panel")
            self.status_label = self.label("Checking dictation service…", "section-title")
            hero.append(self.status_label)
            self.shortcut_label = self.label(self.config.app.hotkey, "shortcut")
            hero.append(self.shortcut_label)
            hero.append(
                self.label("Hold to speak. Release to insert. Escape to cancel.", "muted", True)
            )
            actions = self.box(False)
            self.start_button = self.button("Start service", self.start_service, "primary")
            actions.append(self.start_button)
            self.stop_button = self.button("Stop service", self.stop_service)
            self.stop_button.set_visible(False)
            actions.append(self.stop_button)
            self.pause_button = self.button("Pause", self.toggle_pause)
            self.pause_button.set_sensitive(False)
            actions.append(self.pause_button)
            actions.append(
                self.button("Cancel recording", lambda: self.work(lambda: request("cancel")))
            )
            hero.append(actions)
            page.append(hero)
            metrics = self.box(False)
            self.home_metrics = []
            for title in ("Words today", "Recording minutes", "Saved sessions"):
                card = self.box(spacing=8)
                card.add_css_class("metric-panel")
                card.set_hexpand(True)
                card.append(self.label(title, "muted"))
                value = self.label("—", "metric")
                self.home_metrics.append(value)
                card.append(value)
                metrics.append(card)
            page.append(metrics)
            row = self.box(False)
            title = self.label("Recent dictations", "section-title")
            title.set_hexpand(True)
            row.append(title)
            row.append(self.button("View history", lambda: self.navigate("history")))
            page.append(row)
            self.recent = self.box()
            page.append(self.recent)

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
                    ("latency_ms", "Mean output dispatch"),
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
            foreground = 0.72
            maximum = max([1, *self.daily.values()])
            column = width / 7
            context.select_font_face("Adwaita Sans")
            context.set_font_size(11)
            for index, (day, words) in enumerate(self.daily.items()):
                left = index * column + 10
                top = (height - 46) * words / maximum
                context.set_source_rgb(foreground, foreground, foreground)
                context.rectangle(left, height - 28 - top, max(1, column - 22), max(1, top))
                context.fill()
                context.move_to(left, height - 34 - top)
                context.show_text(str(words))
                context.set_source_rgb(0.5, 0.5, 0.5)
                context.move_to(left, height - 8)
                context.show_text(datetime.fromisoformat(day).strftime("%a"))

        def field(self, page, title, widget, description=None):
            group = self.box(spacing=8)
            group.append(self.label(title, "field-title"))
            if description:
                group.append(self.label(description, "muted", True))
            group.append(widget)
            page.append(group)
            return widget

        def entry(self, text):
            widget = Gtk.Entry()
            widget.set_text(str(text))
            return widget

        def build_settings(self):
            page = self.page(
                "settings",
                "Settings",
                "Tune your recording, text cleanup, and local history.",
            )
            self.entries = {}

            def settings_section(title):
                group = self.box(spacing=20)
                group.add_css_class("panel")
                group.append(self.label(title, "section-title"))
                page.append(group)
                return group

            input_settings = settings_section("Recording")
            self.hotkey = self.entry(self.config.app.hotkey)
            hotkey_row = self.box(False)
            self.hotkey.set_hexpand(True)
            hotkey_row.append(self.hotkey)
            self.record_key = self.button("Record shortcut", self.begin_shortcut)
            hotkey_row.append(self.record_key)
            self.field(
                input_settings,
                "Push-to-talk shortcut",
                hotkey_row,
                "Use at least one modifier. Conflicts are checked when the service applies it.",
            )
            controller = Gtk.EventControllerKey()
            controller.connect("key-pressed", self.capture_shortcut)
            controller.connect("key-released", self.release_shortcut)
            self.hotkey.add_controller(controller)
            self.recording_key = False
            self.pending_modifiers = []
            self.mic = Gtk.DropDown.new_from_strings(["System default"])
            self.field(input_settings, "Microphone", self.mic)
            mic_test = self.box(False)
            self.meter = Gtk.LevelBar(min_value=0, max_value=1)
            self.meter.set_hexpand(True)
            self.meter.set_valign(Gtk.Align.CENTER)
            mic_test.append(self.meter)
            self.test_button = self.button("Test input · 3 seconds", self.test_microphone)
            mic_test.append(self.test_button)
            input_settings.append(mic_test)
            input_settings.append(
                self.label(
                    "The test stays in memory; it is not uploaded, played, or saved.", "muted", True
                )
            )
            provider_groups = {
                "stt": settings_section("Transcription"),
                "cleanup": settings_section("Text cleanup"),
            }
            for section, key, title in (
                ("stt", "language", "Language · blank for automatic detection"),
                ("stt", "base_url", "Transcription API URL"),
                ("stt", "model", "Transcription model"),
                ("stt", "key_env", "Transcription credential environment variable"),
                ("cleanup", "base_url", "Cleanup API URL"),
                ("cleanup", "model", "Cleanup model · blank to disable refinement"),
                ("cleanup", "key_env", "Cleanup credential environment variable"),
                ("cleanup", "reasoning_effort", "Cleanup reasoning effort"),
            ):
                widget = self.entry(getattr(getattr(self.config, section), key))
                self.entries[(section, key)] = widget
                self.field(provider_groups[section], title, widget)
            page.append(
                self.label(
                    "Credentials stay in the launch environment, never in these fields. "
                    "Changing provider sends future recordings or text to that provider.",
                    "muted",
                    True,
                )
            )
            storage_settings = self.box(spacing=20)
            storage_settings.add_css_class("panel")
            storage_settings.append(self.label("History & desktop", "section-title"))
            page.append(storage_settings)
            self.retention = Gtk.SpinButton.new_with_range(1, 3650, 1)
            self.retention.set_value(self.config.desktop.retention_days)
            self.field(storage_settings, "Keep history for this many days", self.retention)
            self.save_button = self.button("Save settings", self.save_settings, "primary")
            self.save_button.set_halign(Gtk.Align.START)
            desktop_actions = self.box(False)
            desktop_actions.append(
                self.button(
                    "Add to app launcher",
                    lambda: self.work(
                        lambda: install(self.path),
                        lambda _: self.message("Caelum added to your app launcher."),
                    ),
                )
            )
            self.login_button = self.button("", self.toggle_login)
            self.login_label()
            desktop_actions.append(self.login_button)
            storage_settings.append(desktop_actions)
            storage_settings.append(
                self.label(
                    "Starting at login runs the dictation service, not this window. "
                    "Closing the window leaves dictation running. Use Stop service to stop it.",
                    "muted",
                    True,
                )
            )

            page.append(self.save_button)

        def set_devices(self, devices):
            selected = self.config.app.microphone
            self.devices = [("System default", None), *dict.fromkeys(devices)]
            if selected is not None and not any(value == selected for _, value in self.devices):
                self.devices.append((f"{selected} · configured, not detected", selected))
            self.mic.set_model(Gtk.StringList.new([name for name, _ in self.devices]))
            self.mic.set_selected(
                next(
                    (index for index, (_, value) in enumerate(self.devices) if value == selected), 0
                )
            )

        def begin_shortcut(self):
            self.recording_key = True
            self.pending_modifiers = []
            self.record_key.set_label("Press shortcut…")
            self.hotkey.grab_focus()

        def capture_shortcut(self, _, keyval, keycode, state):
            if not self.recording_key:
                return False
            if keyval == Gdk.KEY_Escape:
                self.recording_key = False
                self.record_key.set_label("Record shortcut")
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
                self.hotkey.set_text(" + ".join([*modifiers, name.upper()]))
                self.recording_key = False
                self.record_key.set_label("Record shortcut")
            return True

        def release_shortcut(self, _, keyval, keycode, state):
            if self.recording_key and len(self.pending_modifiers) >= 2:
                self.hotkey.set_text(" + ".join(self.pending_modifiers))
                self.recording_key = False
                self.record_key.set_label("Record shortcut")

        def test_microphone(self):
            self.test_button.set_sensitive(False)
            device = self.devices[self.mic.get_selected()][1]

            def test():
                import time

                import numpy as np
                import sounddevice as sound

                def level(data, frames, timing, status):
                    value = min(1, float(np.sqrt(np.mean(data**2))) * 8)
                    GLib.idle_add(self.meter.set_value, value)

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
                    GLib.idle_add(self.meter.set_value, 0)

            self.work(test)

        def save_settings(self):
            updated = deepcopy(self.config)
            updated.app.hotkey = self.hotkey.get_text().strip().upper()
            updated.app.microphone = self.devices[self.mic.get_selected()][1]
            for (section, key), widget in self.entries.items():
                setattr(getattr(updated, section), key, widget.get_text().strip())
            updated.desktop.retention_days = self.retention.get_value_as_int()
            self.save_button.set_sensitive(False)

            def persist():
                try:
                    save(updated, self.path)
                    try:
                        request("reload")
                    except (FileNotFoundError, ConnectionRefusedError):
                        return "Settings saved. They will apply when dictation starts."
                    except (RuntimeError, OSError):
                        return (
                            "Settings saved, but not applied to the running service. Finish or "
                            "cancel dictation, check shortcut conflicts, then save again."
                        )
                    return "Settings saved and applied."
                finally:
                    GLib.idle_add(self.save_button.set_sensitive, True)

            def saved(message):
                self.config = updated
                self.shortcut_label.set_text(updated.app.hotkey)
                self.message(message)
                self.refresh()

            self.work(persist, saved)

        def apply_theme(self):
            css = """
            window.caelum, .caelum headerbar, .caelum .background {
              background: #000000; color: #e7e7e7; background-image: none;
            }
            .caelum { font-family: 'Adwaita Sans', 'Noto Sans', sans-serif; font-size: 14px; }
            .caelum headerbar { min-height: 52px; padding: 0 20px;
              box-shadow: none; border: none; }
            .caelum .wordmark { font-weight: 700; font-size: 20px; letter-spacing: -0.6px; }
            .caelum .navigation { padding: 8px 16px 24px; background: #000000; }
            .caelum .sidebar-toggle { margin-bottom: 24px; }
            .caelum .page { padding: 28px 36px 40px; }
            .caelum .title { font-size: 30px; font-weight: 600; letter-spacing: -0.8px; }
            .caelum .section-title { font-size: 16px; font-weight: 600; }
            .caelum .muted { color: #a1a1a1; font-size: 13px; }
            .caelum .metric { font-size: 30px; font-weight: 500; }
            .caelum .shortcut { font-size: 34px; font-weight: 500; letter-spacing: -0.6px; }
            .caelum .field-title { font-size: 13px; font-weight: 600; }
            .caelum .panel { background: #111111; border: none; border-radius: 16px;
              box-shadow: none; padding: 22px; }
            .caelum .metric-panel { padding: 8px 0 12px; }
            .caelum button, .caelum button:hover, .caelum button:active {
              background: #232323; color: #e7e7e7; background-image: none;
              box-shadow: none; text-shadow: none; border: none;
              border-radius: 10px; padding: 10px 14px; }
            .caelum button:disabled { opacity: 0.4; }
            .caelum button.nav-item, .caelum button.nav-item:hover,
            .caelum button.sidebar-toggle, .caelum button.sidebar-toggle:hover,
            .caelum headerbar button, .caelum headerbar button:hover {
              background: transparent; color: #a1a1a1; }
            .caelum button.nav-item { padding: 12px; }
            .caelum button.nav-item.selected, .caelum button.nav-item.selected:hover {
              background: #1b1b1b; color: #e7e7e7; font-weight: 600; }
            .caelum button.primary, .caelum button.primary:hover,
            .caelum button.primary:active { background: #d8d8d8; color: #111111; }
            .caelum entry, .caelum entry:hover, .caelum entry:focus-within,
            .caelum dropdown, .caelum dropdown:hover,
            .caelum spinbutton, .caelum spinbutton:hover {
              background: #202020; color: #e7e7e7; background-image: none;
              border: none; border-radius: 10px; box-shadow: none; padding: 8px; }
            .caelum dropdown button, .caelum dropdown button:hover,
            .caelum spinbutton button, .caelum spinbutton button:hover,
            .caelum spinbutton entry, .caelum spinbutton entry:hover {
              background: transparent; border: none; box-shadow: none; }
            .caelum .notice { background: #1b1b1b; border-radius: 10px;
              margin: 12px 36px 0; padding: 12px 16px; }
            .caelum levelbar trough { background: #232323; border-radius: 4px; min-height: 6px; }
            .caelum levelbar block { border: none; border-radius: 4px; }
            .caelum levelbar block.filled { background: #a1a1a1; }
            .caelum *:focus-visible { outline: 2px solid #777777; outline-offset: 2px; }
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
            settings = Gtk.Settings.get_default()
            if settings.find_property("gtk-interface-color-scheme"):
                settings.set_property(
                    "gtk-interface-color-scheme",
                    Gtk.InterfaceColorScheme.DARK,
                )
            else:
                settings.set_property("gtk-application-prefer-dark-theme", True)
            self.chart.queue_draw()

        def start_service(self):
            if self.process and self.process.poll() is None:
                return
            self.process = subprocess.Popen(
                [sys.executable, "-m", "caelum.cli", "--config", str(self.path), "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.message("Starting dictation… Provider access is checked before it becomes ready.")

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
            if status:
                state = status["state"]
                self.paused = status.get("paused", False)
                self.status_label.set_text(
                    "Dictation is paused"
                    if self.paused
                    else "Ready when you are"
                    if state == "hidden"
                    else f"Dictation · {state.replace('_', ' ')}"
                )
                self.shortcut_label.set_text(status.get("hotkey", self.config.app.hotkey))
                if status.get("storage_error"):
                    self.message(
                        "Dictation works, but history could not be saved. Check disk permissions."
                    )
            else:
                self.status_label.set_text("Dictation is stopped")
                if self.process and self.process.poll() is not None and self.process.returncode:
                    self.message(
                        "Service could not start. Run caelum doctor to check credentials, "
                        "models, shortcut conflicts, and desktop access."
                    )
            self.start_button.set_visible(not bool(status))
            self.stop_button.set_visible(bool(status))
            self.pause_button.set_sensitive(bool(status))
            self.pause_button.set_label("Resume" if self.paused else "Pause")
            self.history_note.set_text(
                f"Saved automatically on this device · Kept for {self.config.desktop.retention_days} days"
            )
            for widget, value in zip(
                self.home_metrics,
                (
                    summary["today_words"],
                    f"{summary['duration_ms'] / 60000:.1f}",
                    summary["sessions"],
                ),
                strict=True,
            ):
                widget.set_text(str(value))
            signature = (rows, recent, self.search.get_text())
            changed = signature != self.history_signature
            if changed:
                self.history_signature = signature
                self.clear(self.recent)
                self.clear(self.history_rows)
            if changed and not rows:
                message = (
                    "No matching dictations."
                    if self.search.get_text()
                    else "No dictations yet. Your next completed dictation will appear here."
                )
                self.history_rows.append(self.label(message, "muted", True))
            for row in recent if changed else []:
                self.recent.append(self.history_card(row, compact=True))
            if changed and not recent:
                self.recent.append(
                    self.label(
                        "Your next completed dictation will appear here.",
                        "muted",
                        True,
                    )
                )
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
            if not compact:
                actions = self.box(False)
                actions.append(self.button("Copy text", lambda: self.copy_text(text)))
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
                card.append(actions)
            return card

        def copy_text(self, text):
            self.window.get_clipboard().set(text)
            self.message("Copied to clipboard. Clipboard managers may retain this text.")

        def confirm_delete_all(self):
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                text="Delete all saved dictations?",
                secondary_text="This permanently deletes local transcripts and "
                "recalculates all statistics. Clipboard copies are not erased.",
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

        def login_label(self):
            self.login_button.set_label(
                "Disable start at login" if entry_path(True).exists() else "Enable start at login"
            )

        def toggle_login(self):
            enabled = not entry_path(True).exists()

            def saved(_):
                self.login_label()
                self.message("Start at login enabled." if enabled else "Start at login disabled.")

            self.work(lambda: install(self.path, autostart=True, enabled=enabled), saved)

        def shutdown(self, _):
            self.closed = True
            if hasattr(self, "timer"):
                GLib.source_remove(self.timer)
            self.pool.shutdown(wait=False, cancel_futures=True)

    return Desktop().run([])
