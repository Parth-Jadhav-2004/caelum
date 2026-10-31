"""Native GTK desktop shell; slow work stays outside the GTK main thread."""

import asyncio
import json
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
                    f"{title}: key missing; add {settings.key_env} to the launch environment"
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
                "invalid_key": "Update the key in the launch environment and restart Caelum.",
                "missing_key": "Add the provider key to the launch environment and restart Caelum.",
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
            self.window.set_default_size(1080, 760)
            self.window.set_size_request(480, 480)
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
            self.compact_window = False

            def adapt_layout(widget, _clock):
                compact = 0 < widget.get_width() < 800
                if compact and not self.compact_window:
                    self.sidebar_toggle.set_active(False)
                self.compact_window = compact
                return True

            self.window.add_tick_callback(adapt_layout)
            self.build_home()
            self.build_history()
            self.build_stats()
            self.build_settings()
            self.apply_theme()
            self.navigate("home")
            if Gdk.Display.get_default().get_monitors().get_item(0).get_geometry().width < 1000:
                self.sidebar_toggle.set_active(False)
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
                "home",
                "Overview",
                "Record your voice, then copy your words into any app."
                if self.portable
                else "Hold your shortcut to speak. Release to insert your words.",
            )
            hero = self.box(spacing=18)
            hero.add_css_class("panel")
            self.status_label = self.label("Checking dictation service…", "section-title")
            hero.append(self.status_label)
            self.status_label.set_wrap(True)
            self.status_detail = self.label("", "muted", True)
            hero.append(self.status_detail)
            self.delivery_note = self.label(
                "Manual paste: completed text appears here. Choose Copy text, then paste."
                if self.portable
                else "Automatic paste on this Hyprland session. If focus changes, copy and paste manually.",
                "muted",
                True,
            )
            hero.append(self.delivery_note)
            self.shortcut_label = self.label(
                "Record. Copy. Paste." if self.portable else self.config.app.hotkey, "shortcut"
            )
            self.shortcut_label.set_wrap(True)
            hero.append(self.shortcut_label)
            hero.append(
                self.label(
                    "Use Record, then Finish recording. Copy your completed text below."
                    if self.portable
                    else "Hold to speak. Release to insert. Escape to cancel.",
                    "muted",
                    True,
                )
            )
            actions = self.flow()
            self.start_button = self.button("Start service", self.start_service, "primary")
            actions.append(self.start_button)
            self.stop_button = self.button("Stop service", self.stop_service)
            self.stop_button.set_visible(False)
            actions.append(self.stop_button)
            self.pause_button = self.button("Pause", self.toggle_pause)
            self.pause_button.set_sensitive(False)
            actions.append(self.pause_button)
            self.record_button = self.button("Record", self.toggle_recording, "primary")
            self.record_button.set_visible(self.portable)
            self.record_button.set_sensitive(False)
            actions.append(self.record_button)
            self.retry_button = self.button(
                "Retry",
                lambda: self.work(lambda: request("retry"), lambda _: self.refresh()),
                "primary",
            )
            self.retry_button.set_visible(False)
            actions.append(self.retry_button)
            self.cancel_button = self.button(
                "Cancel recording",
                lambda: self.work(lambda: request("cancel"), lambda _: self.refresh()),
            )
            self.cancel_button.set_visible(False)
            actions.append(self.cancel_button)
            self.settings_action = self.button("Open Settings", lambda: self.navigate("settings"))
            self.settings_action.set_visible(False)
            actions.append(self.settings_action)
            hero.append(actions)
            page.append(hero)
            metrics = self.flow()
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

        def build_settings(self):
            page = self.page(
                "settings",
                "Settings",
                "Tune your recording, text cleanup, and local history.",
            )
            page.append(self.button("Open setup / Manage keys", self.open_setup))
            self.entries = {}

            def settings_section(title):
                group = self.box(spacing=20)
                group.add_css_class("panel")
                group.append(self.label(title, "section-title"))
                page.append(group)
                return group

            input_settings = settings_section("Recording")
            self.hotkey = self.entry(self.config.app.hotkey)
            hotkey_row = self.box()
            self.hotkey.set_hexpand(True)
            hotkey_row.append(self.hotkey)
            self.record_key = self.button("Record shortcut", self.begin_shortcut)
            hotkey_row.append(self.record_key)
            self.field(
                input_settings,
                "Push-to-talk shortcut",
                hotkey_row,
                "Your desktop may ask you to approve or change this shortcut. Restart the service "
                "after changing a portal shortcut. Modifier-only shortcuts require Hyprland.",
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
            providers = settings_section("Providers")
            self.preset = Gtk.DropDown.new_from_strings(PRESETS)
            self.preset.set_selected(provider_preset(self.config))
            self.field(providers, "Provider preset", self.preset)
            providers.append(
                self.label(
                    "Groq uses one GROQ_API_KEY for transcription and refinement. Free usage has "
                    "provider limits. Refinement is optional; its quality and speed still need live "
                    "qualification. Transcription only sends no text to a refinement provider.",
                    "muted",
                    True,
                )
            )
            self.connection_label = self.label(self.key_status(self.config), "muted", True)
            providers.append(self.connection_label)
            self.check_button = self.button("Check connection", self.check_connection)
            self.check_button.set_halign(Gtk.Align.START)
            providers.append(self.check_button)
            providers.append(
                self.label(
                    "Connection checks contact the provider's model list, without audio or transcript. "
                    "A listed model does not guarantee available quota. Keys come from the launch "
                    "environment; restart the app after replacing a key.",
                    "muted",
                    True,
                )
            )
            self.advanced = Gtk.Expander(label="Advanced provider settings")
            advanced_body = self.box(spacing=16)
            self.advanced.set_child(advanced_body)
            providers.append(self.advanced)
            for section, key, title in (
                ("stt", "language", "Language · blank for automatic detection"),
                ("stt", "base_url", "Transcription API URL"),
                ("stt", "model", "Transcription model"),
                ("stt", "key_env", "Transcription credential environment variable"),
                ("cleanup", "base_url", "Refinement API URL"),
                ("cleanup", "model", "Refinement model · blank to disable"),
                ("cleanup", "key_env", "Refinement credential environment variable"),
                ("cleanup", "reasoning_effort", "Refinement reasoning effort"),
            ):
                widget = self.entry(getattr(getattr(self.config, section), key))
                self.entries[(section, key)] = widget
                self.field(advanced_body, title, widget)
                widget.connect("changed", self.provider_edited)
            self.advanced.set_expanded(self.preset.get_selected() == 2)
            self.preset.connect("notify::selected", self.select_preset)
            providers.append(
                self.label(
                    "Changing provider sends future recordings or text to that provider. "
                    "Save settings to apply your selection.",
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
            desktop_actions = self.flow()
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
            self.build_updates(page)

        def build_updates(self, page):
            from .updates import cache_dir, installed

            panel = self.box(spacing=12)
            panel.add_css_class("panel")
            panel.append(self.label("Updates", "section-title"))
            info = installed()
            pending = (cache_dir() / "pending").is_dir()
            description = (
                f"Caelum {info['version']}. Checks GitHub when this window opens. "
                "Downloads require your approval. Signed updates install on the next app "
                "launch with administrator authorization; active dictation is never interrupted."
                if info
                else "This installation is managed by your package manager or source checkout. "
                "In-app updates require an official native package with a pinned release key."
            )
            panel.append(self.label(description, "muted", True))
            self.update_automatic = Gtk.CheckButton(label="Check for updates when Caelum opens")
            self.update_automatic.set_active(self.config.desktop.check_updates)
            self.update_automatic.set_sensitive(bool(info))
            panel.append(self.update_automatic)
            self.update_status = self.label(
                "Update queued. Close and reopen Caelum to install it." if pending else "",
                wrap=True,
            )
            panel.append(self.update_status)
            actions = self.flow()
            self.update_check = self.button("Check for updates", self.check_updates)
            self.update_check.set_sensitive(bool(info) and not pending)
            actions.append(self.update_check)
            self.update_download = self.button(
                "Download & install on next launch", self.prompt_update
            )
            self.update_download.set_sensitive(False)
            actions.append(self.update_download)
            self.update_discard = self.button("Discard queued update", self.discard_update)
            self.update_discard.set_sensitive(pending)
            actions.append(self.update_discard)
            panel.append(actions)
            page.append(panel)

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
                self.update_download.set_sensitive(bool(self.available_update) and not pending)
                self.update_discard.set_sensitive(pending)
                value, error = result
                if error:
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

                self.update_work(install_queued_update, applied)
            elif self.config.desktop.check_updates:
                self.check_updates()

        def check_updates(self):
            from .updates import check

            self.update_status.set_text("Checking for updates…")

            def checked(update):
                self.available_update = update
                self.update_download.set_sensitive(bool(update))
                self.update_status.set_text(
                    f"Caelum {update['version']} is available."
                    if update
                    else "Caelum is up to date."
                )
                if update:
                    self.prompt_update()

            self.update_work(check, checked)

        def prompt_update(self):
            if not self.available_update or self.update_busy:
                return
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.NONE,
                text=f"Download Caelum {self.available_update['version']}?",
                secondary_text=(
                    "The signed package will be downloaded from GitHub. Installation happens "
                    "the next time you open Caelum and requires administrator authorization. "
                    "Your settings, keys, and history are kept."
                ),
            )
            dialog.add_button("Later", Gtk.ResponseType.CANCEL)
            dialog.add_button("Download update", Gtk.ResponseType.ACCEPT)
            dialog.set_default_response(Gtk.ResponseType.CANCEL)

            def responded(window, response):
                window.destroy()
                if response == Gtk.ResponseType.ACCEPT:
                    from .updates import stage

                    self.update_status.set_text("Downloading and verifying update…")
                    self.update_work(
                        lambda: stage(self.available_update),
                        lambda version: self.update_status.set_text(
                            f"Caelum {version} is ready. Close and reopen this window to install."
                        ),
                    )

            dialog.connect("response", responded)
            dialog.present()

        def discard_update(self):
            from .updates import discard_pending

            self.update_work(
                discard_pending,
                lambda _: self.update_status.set_text("Queued update discarded."),
            )

        def open_setup(self):
            from .onboarding_ui import show

            try:
                show(self)
            except (OSError, RuntimeError, ValueError):
                self.message(
                    "Could not open setup. Check permissions on your Caelum config directory."
                )

        def sync_setup_settings(self):
            self.selecting_preset = True
            for (section, key), widget in self.entries.items():
                widget.set_text(str(getattr(getattr(self.config, section), key)))
            self.preset.set_selected(provider_preset(self.config))
            self.selecting_preset = False
            self.hotkey.set_text(self.config.app.hotkey)
            self.set_devices([(name, value) for name, value in self.devices if value is not None])
            self.connection_label.set_text(self.key_status(self.config))
            self.connection_generation = getattr(self, "connection_generation", 0) + 1

        def key_status(self, config):
            return "\n".join(
                f"{title}: "
                + (
                    "off (raw transcription)"
                    if not provider.model
                    else credential_status(provider.key_env) + "; check connection"
                )
                for title, provider in (
                    ("Transcription", config.stt),
                    ("Refinement", config.cleanup),
                )
            )

        def provider_draft(self):
            updated = deepcopy(self.config)
            for (section, key), widget in self.entries.items():
                setattr(getattr(updated, section), key, widget.get_text().strip())
            return updated

        def provider_edited(self, _):
            if getattr(self, "selecting_preset", False):
                return
            self.selecting_preset = True
            self.preset.set_selected(2)
            self.advanced.set_expanded(True)
            self.selecting_preset = False
            self.connection_generation = getattr(self, "connection_generation", 0) + 1
            self.connection_label.set_text(self.key_status(self.provider_draft()))

        def select_preset(self, *_):
            if getattr(self, "selecting_preset", False):
                return
            selected = self.preset.get_selected()
            if selected == 2:
                self.advanced.set_expanded(True)
                return
            updated = apply_provider_preset(self.provider_draft(), selected)
            self.selecting_preset = True
            for (section, key), widget in self.entries.items():
                widget.set_text(str(getattr(getattr(updated, section), key)))
            self.selecting_preset = False
            self.connection_generation = getattr(self, "connection_generation", 0) + 1
            self.connection_label.set_text(self.key_status(updated))

        def check_connection(self):
            updated = self.provider_draft()
            generation = getattr(self, "connection_generation", 0)
            self.check_button.set_sensitive(False)
            self.connection_label.set_text("Checking connection…")

            def checked(text):
                self.check_button.set_sensitive(True)
                if generation == getattr(self, "connection_generation", 0):
                    self.connection_label.set_text(text)

            def check():
                try:
                    return asyncio.run(connection_status(updated))
                finally:
                    GLib.idle_add(self.check_button.set_sensitive, True)

            self.work(check, checked)

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
            updated.desktop.check_updates = self.update_automatic.get_active()
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
                if not self.portable:
                    self.shortcut_label.set_text(updated.app.hotkey)
                self.message(message)
                self.refresh()

            self.work(persist, saved)

        def apply_theme(self):
            css = """
            window.caelum, .caelum headerbar, .caelum .background {
              background: #000000; color: #e7e7e7; background-image: none;
            }
            .caelum { font-family: 'Adwaita Sans', 'Noto Sans', sans-serif; font-size: 1em; }
            .caelum headerbar { min-height: 52px; padding: 0 20px;
              box-shadow: none; border: none; }
            .caelum .wordmark { font-weight: 700; font-size: 1.4em; letter-spacing: -0.6px; }
            .caelum .navigation { padding: 8px 16px 24px; background: #000000; }
            .caelum .sidebar-toggle { margin-bottom: 24px; }
            .caelum .page { padding: 24px 20px 32px; }
            .caelum .title { font-size: 2em; font-weight: 600; letter-spacing: -0.8px; }
            .caelum .section-title { font-size: 1.15em; font-weight: 600; }
            .caelum .muted { color: #b3b3b3; font-size: 0.95em; }
            .caelum .metric { font-size: 2em; font-weight: 500; }
            .caelum .shortcut { font-size: 2em; font-weight: 500; letter-spacing: -0.6px; }
            .caelum .field-title { font-size: 1em; font-weight: 600; }
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
            /* GTK propagates focus-visible to ancestors when Alt reveals focus.
               Only controls should draw an outline, never layout containers. */
            .caelum button:focus-visible, .caelum entry:focus-visible,
            .caelum spinbutton:focus-visible, .caelum checkbutton:focus-visible,
            .caelum textview:focus-visible {
              outline: 2px solid #d8d8d8; outline-offset: 2px;
            }
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
            if status:
                self.paused = status.get("paused", False)
                title, detail = service_presentation(status)
                self.status_label.set_text(title)
                self.status_detail.set_text(detail)
                if status.get("backend", "hyprland") == "portable":
                    self.shortcut_label.set_text(
                        status.get("shortcut_description", "Record. Copy. Paste.")
                        if status.get("shortcut_mode") == "portal"
                        else "Record. Copy. Paste."
                    )
                else:
                    self.shortcut_label.set_text(status.get("hotkey", self.config.app.hotkey))
                if status.get("storage_error"):
                    self.message(
                        "Dictation works, but history could not be saved. Check disk permissions."
                    )
            else:
                title, detail = service_presentation(None)
                self.status_label.set_text(title)
                self.status_detail.set_text(detail)
                if self.process and self.process.poll() is not None and self.process.returncode:
                    self.message(
                        "Service could not start. Run caelum doctor to check credentials, "
                        "models, shortcut conflicts, and desktop access."
                    )
            self.start_button.set_visible(not bool(status))
            self.stop_button.set_visible(bool(status))
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
            self.cancel_button.set_label(
                "Discard recording" if retry_available else "Cancel recording"
            )
            self.settings_action.set_visible(not status or status["state"] == "error")
            self.record_button.set_visible(self.portable and not retry_available)
            self.record_button.set_sensitive(
                bool(status)
                and not self.paused
                and status["state"] not in ("processing", "refining")
                and not status.get("pending_audio", False)
            )
            self.record_button.set_label(
                "Finish recording"
                if status and status["state"] in ("listening", "recording", "starting")
                else "Record"
            )
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
            if getattr(self, "setup_window", None):
                self.setup_window.close()
            if hasattr(self, "timer"):
                GLib.source_remove(self.timer)
            self.pool.shutdown(wait=False, cancel_futures=True)

    return Desktop().run([])
