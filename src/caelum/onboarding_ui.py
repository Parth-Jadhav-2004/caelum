"""Embedded GTK setup page. Slow microphone, keyring and provider work stays off GTK."""

import asyncio
import threading
from copy import deepcopy

from . import credentials
from .config import save, validate
from .onboarding import Progress, check_shortcut, practice, record_sample, validate_providers


def show(host, key_name=None):
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk

    from .desktop import PRESETS, apply_provider_preset, microphones, provider_preset, request

    if getattr(host, "setup_window", None):
        host.navigate("setup")
        return host.setup_window

    class Setup(Gtk.Box):
        def __init__(self):
            super().__init__(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
            self.add_css_class("sentence-page")
            self.add_css_class("setup-page")
            self.config = deepcopy(host.config)
            self.progress = Progress.load(host.path)
            # Resume by revalidating access; no separate welcome screen.
            self.stage = 1
            self.validated = self.tested = self.succeeded = False
            self.closed = self.busy = self.recording_key = False
            self.cancelled = threading.Event()
            self.key_name = key_name
            self.pending_modifiers = []
            self.pending_shortcut = None
            top = host.box(False, 16)
            progress = host.box(False, 6)
            progress.set_valign(Gtk.Align.CENTER)
            self.progress_bars = []
            for index in range(4):
                bar = host.box(spacing=0)
                bar.add_css_class("setup-progress")
                bar.set_size_request(36, 4)
                bar.update_property([Gtk.AccessibleProperty.LABEL], [f"Step {index + 1}"])
                self.progress_bars.append(bar)
                progress.append(bar)
            top.append(progress)
            spacer = host.box()
            spacer.set_hexpand(True)
            top.append(spacer)
            self.later = host.button("Resume later", self.resume_later, "text-link")
            top.append(self.later)
            self.append(top)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_hexpand(True)
            scroll.set_vexpand(True)
            center = host.box(spacing=16)
            center.set_valign(Gtk.Align.CENTER)
            center.set_halign(Gtk.Align.FILL)
            center.set_hexpand(True)
            self.column = center
            self.pages = Gtk.Stack()
            self.pages.set_vhomogeneous(False)
            self.pages.set_hhomogeneous(False)
            center.append(self.pages)
            self.notice = host.label("", "setup-note", True)
            center.append(self.notice)
            scroll.set_child(host.clamp(center, vertical_center=True))
            self.append(scroll)
            bottom = host.box(False, 16)
            self.back = host.button("Back", self.go_back, "text-link")
            bottom.append(self.back)
            spacer = host.box()
            spacer.set_hexpand(True)
            bottom.append(spacer)
            self.next = host.button("Continue", self.advance, "setup-primary")
            bottom.append(self.next)
            self.append(bottom)
            self.providers()
            self.microphone()
            self.shortcut()
            self.practice_page()
            self.practice_keys = Gtk.EventControllerKey()
            self.practice_keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            self.practice_keys.connect("key-pressed", self.practice_pressed)
            self.practice_keys.connect("key-released", self.practice_released)
            self.practice_held = False
            host.window.add_controller(self.practice_keys)
            self.render()
            host.work(microphones, self.devices_loaded)

        def page(self, index):
            page = host.box(spacing=24)
            self.pages.add_named(page, str(index))
            return page

        def headline(self, page, *parts):
            host.sentence(page, *parts)
            page.get_first_child().add_css_class("setup-headline")

        def work(self, operation, done):
            self.busy = True
            self.render()

            def safe():
                try:
                    return True, operation()
                except Exception as error:
                    return False, (
                        str(error) if isinstance(error, (ValueError, RuntimeError))
                        else "Check the microphone, keyring, or network and retry."
                    )

            def delivered(result):
                if self.closed:
                    return
                self.busy = False
                ok, value = result
                if ok:
                    done(value)
                else:
                    self.notice.set_text(value)
                self.render()

            host.work(safe, delivered)

        def providers(self):
            page = self.page(1)
            self.preset = Gtk.DropDown.new_from_strings(PRESETS)
            self.preset.set_selected(provider_preset(self.config))
            self.provider_token = host.token_menu(
                self.preset, lambda: ["Groq", "Groq · transcription only", "Custom"]
            )
            self.headline(page, "Use", self.provider_token, "to turn your voice into text.")
            self.key_entry = Gtk.PasswordEntry()
            self.key_entry.set_show_peek_icon(True)
            self.key_entry.set_property("placeholder-text", "Paste your API key")
            self.key_entry.add_css_class("setup-key")
            self.key_entry.update_property([Gtk.AccessibleProperty.LABEL], ["Provider API key"])
            self.key_entry.connect("activate", lambda _: self.advance())
            page.append(self.key_entry)
            self.key_note = host.label("Stored in your system keyring.", "setup-note", True)
            page.append(self.key_note)
            links = host.flow()
            self.get_key = Gtk.LinkButton.new_with_label(
                "https://console.groq.com/keys", "Get a free key ↗"
            )
            self.get_key.add_css_class("text-link")
            links.append(self.get_key)
            links.append(host.button("Custom provider", self.open_settings, "text-link"))
            self.remove_key = host.button("Remove saved key", self.delete_key, "text-link")
            links.append(self.remove_key)
            page.append(links)
            self.consent = Gtk.CheckButton()
            self.consent.set_child(host.label(
                "Allow selected providers to process audio and text.",
                "setup-note", True,
            ))
            self.consent.get_child().set_hexpand(True)
            self.consent.update_property(
                [Gtk.AccessibleProperty.LABEL], ["Consent to send audio and text to selected providers"]
            )
            self.consent.connect("toggled", lambda _: self.render())
            page.append(self.consent)
            self.contributor_row = host.box(False, 16)
            label = host.label("Allow Contributor training use of my text", "setup-note", True)
            label.set_hexpand(True)
            self.contributor_row.append(label)
            self.contributor = Gtk.Switch()
            self.contributor.add_css_class("settings-switch")
            self.contributor.set_valign(Gtk.Align.CENTER)
            self.contributor.update_property(
                [Gtk.AccessibleProperty.LABEL], ["Allow Contributor training use of my text"]
            )
            self.contributor_row.append(self.contributor)
            page.append(self.contributor_row)
            self.preset.connect("notify::selected", self.change_provider)
            self.change_provider()

        def refresh_key(self):
            description = credentials.describe(self.key_name)
            stored = "saved" in description or "present" in description
            self.remove_key.set_visible(stored and "unavailable" not in description)
            self.key_note.set_text(
                "Stored in an owner-only private file; not encrypted."
                if "private file" in description else
                "Key available from your environment." if "environment" in description else
                "Stored in your system keyring."
            )
            self.key_entry.set_property(
                "placeholder-text", "Paste your API key" if self.key_name == self.config.stt.key_env
                else f"Paste your refinement key ({self.key_name})"
            )

        def change_provider(self, *_):
            self.config = apply_provider_preset(self.config, self.preset.get_selected())
            self.provider_token.set_label(
                ("Groq ▾", "Groq ▾", "Custom ▾")[self.preset.get_selected()]
            )
            self.validated = self.succeeded = False
            self.progress.complete = False
            self.key_names = list(dict.fromkeys(
                [self.config.stt.key_env]
                + ([self.config.cleanup.key_env] if self.config.cleanup.model else [])
            ))
            if self.key_name not in self.key_names:
                self.key_name = self.key_names[0]
            self.key_entry.set_text("")
            from .providers import needs_contributor_consent

            self.contributor_row.set_visible(needs_contributor_consent(self.config.cleanup))
            self.contributor.set_active(False)
            self.get_key.set_visible("groq.com" in self.config.stt.base_url)
            self.refresh_key()

        def delete_key(self):
            if self.busy:
                return
            self.key_entry.set_text("")
            self.validated = self.succeeded = False
            self.progress.complete = False
            self.progress.save(host.path)

            def deleted(_):
                self.refresh_key()
                self.notice.set_text("Saved key removed.")

            self.work(lambda: credentials.delete(self.key_name), deleted)

        def open_settings(self):
            self.finish_setup()
            host.navigate("advanced")

        def microphone(self):
            page = self.page(2)
            self.mic = Gtk.DropDown.new_from_strings(["System default"])
            self.devices = [("System default", None)]
            microphone = host.token_menu(self.mic, lambda: [name for name, _ in self.devices])
            self.headline(page, "Say something through", microphone)
            self.mic.connect("notify::selected", self.mic_changed)
            card = host.box(False, 6)
            card.add_css_class("setup-card")
            card.add_css_class("setup-meter")
            card.set_halign(Gtk.Align.FILL)
            self.meter_bars = []
            bars = host.box(False, 6)
            bars.set_halign(Gtk.Align.CENTER)
            bars.set_hexpand(True)
            bars.update_property([Gtk.AccessibleProperty.LABEL], ["Microphone input level"])
            for index in range(18):
                bar = host.box(spacing=0)
                bar.add_css_class("mic-bar")
                bar.set_size_request(6, 6 + (index * 7 % 17))
                bar.set_valign(Gtk.Align.CENTER)
                bars.append(bar)
                self.meter_bars.append(bar)
            card.append(bars)
            page.append(card)
            self.mic_note = host.label("The test stays on this device. Nothing is saved.", "setup-note", True)
            page.append(self.mic_note)
            self.test_again = host.button("Test again", self.test_mic, "text-link")
            self.test_again.set_halign(Gtk.Align.END)
            page.append(self.test_again)

        def devices_loaded(self, devices):
            if self.closed:
                return
            self.devices = [("System default", None), *dict.fromkeys(devices)]
            selected = self.config.app.microphone
            if selected is not None and not any(value == selected for _, value in self.devices):
                self.devices.append((f"{selected} · not detected", selected))
            self.mic.set_model(Gtk.StringList.new([name for name, _ in self.devices]))
            self.mic.set_selected(next(
                (index for index, (_, value) in enumerate(self.devices) if value == selected), 0
            ))

        def mic_changed(self, *_):
            self.tested = self.succeeded = False
            index = self.mic.get_selected()
            if index < len(self.devices):
                self.config.app.microphone = self.devices[index][1]
            self.mic_note.set_text("The test stays on this device. Nothing is saved.")
            self.render()

        def level(self, value):
            def display():
                if not self.closed:
                    for index, bar in enumerate(self.meter_bars):
                        bar.set_size_request(6, 6 + int(value * (24 + index * 7 % 58)))
                return False

            GLib.idle_add(display)

        def ensure_idle(self):
            try:
                status = request("status")
            except (FileNotFoundError, ConnectionRefusedError):
                return
            if status.get("pending_audio") or status.get("state") in (
                "starting", "listening", "recording", "processing", "refining",
            ):
                raise RuntimeError("Finish or cancel dictation before testing in setup")

        def test_mic(self):
            if self.busy:
                return
            self.tested = False
            self.cancelled.clear()
            self.notice.set_text("Listening for three seconds…")

            def tested(pcm):
                self.tested = bool(pcm)
                self.mic_note.set_text(
                    "Heard you clearly. Nothing is saved." if pcm else "No speech detected. Try again."
                )
                self.notice.set_text("")

            def local_test():
                self.ensure_idle()
                return record_sample(self.config, 3, self.cancelled, self.level)

            self.work(local_test, tested)

        def shortcut(self):
            page = self.page(3)
            self.hotkey = host.entry(self.config.app.hotkey)
            self.shortcut_token = host.button(
                self.config.app.hotkey.title(), self.begin_shortcut, "token"
            )
            self.headline(page, "Hold", self.shortcut_token, "to talk.")
            page.append(host.label("Release to insert. Esc to cancel.", "setup-note", True))
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self.capture_shortcut)
            keys.connect("key-released", self.release_shortcut)
            self.shortcut_token.add_controller(keys)

        def begin_shortcut(self):
            self.recording_key = True
            self.pending_modifiers = []
            self.pending_shortcut = None
            self.shortcut_token.set_label("Press keys…")
            self.shortcut_token.grab_focus()

        def capture_shortcut(self, _, keyval, keycode, state):
            if not self.recording_key:
                return False
            if keyval == Gdk.KEY_Escape:
                self.recording_key = False
                self.shortcut_token.set_label(self.hotkey.get_text().title())
                return True
            modifiers, key = self.chord(keyval, state)
            self.pending_modifiers = modifiers
            if key and modifiers:
                self.pending_shortcut = " + ".join([*modifiers, key])
            return True

        def chord(self, keyval, state):
            name = Gdk.keyval_name(keyval) or ""
            modifiers = [name for mask, name in (
                (Gdk.ModifierType.SUPER_MASK, "SUPER"),
                (Gdk.ModifierType.CONTROL_MASK, "CTRL"),
                (Gdk.ModifierType.ALT_MASK, "ALT"),
                (Gdk.ModifierType.SHIFT_MASK, "SHIFT"),
            ) if state & mask]
            modifier = {"Control": "CTRL", "Super": "SUPER", "Alt": "ALT", "Shift": "SHIFT"}.get(
                name.removesuffix("_L").removesuffix("_R")
            )
            return (list(dict.fromkeys([*modifiers, modifier])), None) if modifier else (modifiers, name.upper())

        def release_shortcut(self, _, keyval, keycode, state):
            if self.recording_key:
                combo = self.pending_shortcut or (
                    " + ".join(self.pending_modifiers) if len(self.pending_modifiers) >= 2 else None
                )
                if combo:
                    self.hotkey.set_text(combo)
                    self.shortcut_token.set_label(combo.title())
                    self.recording_key = False

        def practice_page(self):
            page = self.page(4)
            self.practice_button = host.button(self.config.app.hotkey.title(), self.run_practice, "token")
            self.headline(page, "Hold", self.practice_button, "and say hello.")
            self.upload = Gtk.CheckButton()
            self.upload.set_child(host.label("Allow this practice upload.", "setup-note", True))
            self.upload.get_child().set_hexpand(True)
            self.upload.update_property([Gtk.AccessibleProperty.LABEL], ["Consent to upload practice sample"])
            page.append(self.upload)
            card = host.box(False, 12)
            card.add_css_class("setup-card")
            self.result = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            self.result.set_hexpand(True)
            self.result.set_size_request(-1, 100)
            self.result.update_property([Gtk.AccessibleProperty.LABEL], ["Practice dictation result"])
            card.append(self.result)
            self.copy_button = host.button("", self.copy_practice, "icon-button")
            self.copy_button.set_child(host.line_icon("copy"))
            self.copy_button.set_valign(Gtk.Align.START)
            self.copy_button.update_property([Gtk.AccessibleProperty.LABEL], ["Copy practice text"])
            self.copy_button.set_sensitive(False)
            card.append(self.copy_button)
            page.append(card)
            self.practice_note = host.label("Click the shortcut or hold it to record five seconds.", "setup-note", True)
            page.append(self.practice_note)

        def practice_pressed(self, _, keyval, keycode, state):
            if self.closed or self.stage != 4 or host.stack.get_visible_child_name() != "setup":
                return False
            if keyval == Gdk.KEY_Escape and self.busy:
                self.cancelled.set()
                return True
            modifiers, key = self.chord(keyval, state)
            keys = set(modifiers + ([key] if key else []))
            if keys == {key.strip() for key in self.config.app.hotkey.split("+")}:
                if not self.practice_held:
                    self.practice_held = True
                    self.run_practice()
                return True
            return False

        def practice_released(self, *_):
            self.practice_held = False

        def run_practice(self):
            if self.busy:
                return
            if not self.upload.get_active():
                self.notice.set_text("Allow the practice upload before recording.")
                return
            if not (self.validated and self.tested):
                self.stage = 1
                self.notice.set_text("Validate providers and test the microphone first.")
                self.render()
                return
            self.succeeded = False
            self.result.get_buffer().set_text("")
            self.copy_button.set_sensitive(False)
            self.cancelled.clear()
            self.notice.set_text("Recording for five seconds… Speak now.")

            def run_sample():
                self.ensure_idle()
                pcm = record_sample(self.config, 5, self.cancelled)
                if not pcm:
                    raise RuntimeError("No speech detected. Try again")
                return asyncio.run(practice(self.config, pcm, self.cancelled))

            def completed(result):
                text, refined = result
                self.result.get_buffer().set_text(text)
                self.succeeded = bool(text)
                self.copy_button.set_sensitive(self.succeeded)
                self.notice.set_text("")
                self.practice_note.set_text(
                    "It works. Practice text stays here unless you copy it." if refined
                    else "It works. Plain transcript; refinement was unavailable or off."
                )

            self.work(run_sample, completed)

        def copy_practice(self):
            buffer = self.result.get_buffer()
            host.copy_text(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False))

        def go_back(self):
            if not self.busy:
                self.stage = max(1, self.stage - 1)
                self.notice.set_text("")
                self.render()

        def advance(self):
            if self.busy:
                return
            if self.stage == 1:
                if not self.consent.get_active():
                    self.notice.set_text("Allow provider processing before continuing.")
                    return
                if self.contributor_row.get_visible() and not self.contributor.get_active():
                    self.notice.set_text("Accept Contributor training use or choose another provider.")
                    return
                from .providers import contributor_scope

                self.config.cleanup.contributor_consent = (
                    contributor_scope(self.config.cleanup) if self.contributor.get_active() else ""
                )
                self.config.desktop = deepcopy(host.config.desktop)
                self.validated = False
                name, value = self.key_name, self.key_entry.get_text().strip()
                self.key_entry.set_text("")
                self.cancelled.clear()

                def validated(result):
                    storage, missing = result
                    if storage == "file":
                        host.message("Keyring unavailable; key stored in an owner-only private file, not encrypted.")
                    if missing:
                        self.key_name = missing
                        self.refresh_key()
                        self.notice.set_text(f"Add the key for {missing} to continue.")
                        return
                    self.refresh_key()
                    self.validated = True
                    self.stage = 2
                    self.notice.set_text("")
                    self.config.desktop = deepcopy(host.config.desktop)
                    host.config = deepcopy(self.config)
                    host.sync_setup_settings()

                def verify_and_save():
                    storage = credentials.store(name, value) if value else None
                    missing = next((key for key in self.key_names if not credentials.get(key)), None)
                    if missing:
                        return storage, missing
                    asyncio.run(validate_providers(self.config))
                    if self.cancelled.is_set():
                        raise RuntimeError("Setup paused")
                    save(self.config, host.path)
                    return storage, None

                self.work(verify_and_save, validated)
            elif self.stage == 2:
                if not self.tested:
                    self.test_mic()
                    return
                self.stage = 3
                self.notice.set_text("")
                self.render()
            elif self.stage == 3:
                self.config.app.hotkey = self.hotkey.get_text().strip().upper()
                self.config.desktop = deepcopy(host.config.desktop)
                self.cancelled.clear()

                def checked(message):
                    self.config.desktop = deepcopy(host.config.desktop)
                    host.config = deepcopy(self.config)
                    host.sync_setup_settings()
                    self.stage = 4
                    self.practice_button.set_label(self.config.app.hotkey.title())
                    self.notice.set_text("")

                def check_and_save():
                    message = asyncio.run(check_shortcut(self.config))
                    if self.cancelled.is_set():
                        raise RuntimeError("Setup paused")
                    save(self.config, host.path)
                    return message

                self.work(check_and_save, checked)
            elif self.succeeded and self.validated and self.tested:
                self.progress.complete = True
                self.progress.stage = 4
                self.progress.save(host.path)
                host.config = deepcopy(self.config)
                self.finish_setup()
                host.navigate("home")

                def apply_runtime():
                    try:
                        request("reload")
                        return "Setup complete."
                    except (FileNotFoundError, ConnectionRefusedError):
                        return "Setup complete. Start the service to dictate."
                    except (RuntimeError, OSError):
                        return "Setup complete. Restart the service to apply settings."

                host.work(apply_runtime, host.message)

        def render(self):
            if self.closed:
                return
            self.pages.set_visible_child_name(str(self.stage))
            self.pages.set_sensitive(not self.busy)
            self.back.set_sensitive(not self.busy and self.stage > 1)
            self.next.set_label(
                "Finish" if self.stage == 4 else
                "Test microphone" if self.stage == 2 and not self.tested else "Continue"
            )
            self.next.set_sensitive(not self.busy and (
                (self.stage != 1 or self.consent.get_active())
                and (self.stage != 4 or self.succeeded)
            ))
            for index, bar in enumerate(self.progress_bars):
                if index < self.stage:
                    bar.add_css_class("active")
                else:
                    bar.remove_css_class("active")
            self.progress.stage = self.stage
            self.progress.save(host.path)

        def resume_later(self):
            self.finish_setup()
            host.navigate("home")

        def finish_setup(self, *_):
            if self.closed:
                return
            self.cancelled.set()
            if not self.busy:
                try:
                    self.config.app.hotkey = self.hotkey.get_text().strip().upper()
                    self.config.desktop = deepcopy(host.config.desktop)
                    validate(self.config)
                    save(self.config, host.path)
                    host.config = deepcopy(self.config)
                except (ValueError, OSError):
                    host.message("Setup paused. Settings could not be saved.")
            self.closed = True
            self.key_entry.set_text("")
            self.result.get_buffer().set_text("")
            host.window.remove_controller(self.practice_keys)
            host.stack.remove(self)
            host.setup_window = None
            host.sync_setup_settings()

    page = Setup()
    host.stack.add_named(page, "setup")
    host.setup_window = page
    host.navigate("setup")
    GLib.idle_add(page.key_entry.grab_focus)
    return page
