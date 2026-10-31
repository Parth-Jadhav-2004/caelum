"""GTK setup window. No microphone or provider work runs on the GTK thread."""

import asyncio
import threading
from copy import deepcopy

from . import credentials
from .config import save, validate
from .onboarding import (
    PRIVACY,
    Progress,
    check_shortcut,
    practice,
    record_sample,
    validate_providers,
)


def show(host):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk

    from .desktop import PRESETS, apply_provider_preset, microphones, provider_preset, request

    if getattr(host, "setup_window", None):
        host.setup_window.present()
        return host.setup_window

    class Setup(Gtk.Window):
        def __init__(self):
            super().__init__(title="Set up Caelum", transient_for=host.window, modal=True)
            self.set_default_size(640, 680)
            self.set_size_request(420, 440)
            self.add_css_class("caelum")
            self.config = deepcopy(host.config)
            self.progress = Progress.load(host.path)
            self.stage = 0 if self.progress.complete else min(1, self.progress.stage)
            self.validated = self.tested = self.succeeded = False
            self.closed = self.busy = False
            self.cancelled = threading.Event()
            self.connect("close-request", self.close_setup)
            root = host.box(spacing=16)
            root.add_css_class("page")
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.set_child(root)
            self.set_child(scroll)
            self.heading = host.label("", "title", True)
            root.append(self.heading)
            self.pages = Gtk.Stack()
            self.pages.set_vhomogeneous(False)
            root.append(self.pages)
            self.notice = host.label("", "notice", True)
            root.append(self.notice)
            buttons = host.flow()
            self.back = host.button("Back", self.go_back)
            self.later = host.button("Resume later", self.close)
            self.next = host.button("Continue", self.advance, "primary")
            for button in (self.back, self.later, self.next):
                buttons.append(button)
            root.append(buttons)
            self.welcome(host)
            self.providers(host)
            self.microphone(host)
            self.shortcut(host)
            self.practice_page(host)
            self.render()
            host.work(microphones, self.devices_loaded)

        def page(self, index):
            box = host.box(spacing=16)
            self.pages.add_named(box, str(index))
            return box

        def work(self, operation, done):
            self.busy = True
            self.render()

            def safe():
                try:
                    return True, operation()
                except Exception as error:
                    return False, (
                        str(error)
                        if isinstance(error, (ValueError, RuntimeError))
                        else "Could not complete this step. Check the microphone, keyring, or network and retry."
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

        def welcome(self, host):
            page = self.page(0)
            page.append(
                host.label(
                    "Set up your provider, test your microphone, choose a shortcut, and try one dictation. "
                    "You can close this window and resume later.",
                    wrap=True,
                )
            )
            page.append(host.label(PRIVACY, "muted", True))
            page.append(
                host.label(
                    "Keys are stored in your desktop keyring. If it is unavailable, Caelum uses an "
                    "owner-only private file. The file is not encrypted. You can replace or delete keys here.",
                    "muted",
                    True,
                )
            )
            self.consent = Gtk.CheckButton(label="I understand where my audio and text go")
            consent_text = self.consent.get_label()
            self.consent.set_child(host.label(consent_text, wrap=True))
            self.consent.update_property([Gtk.AccessibleProperty.LABEL], [consent_text])
            self.consent.connect("toggled", lambda _: self.render())
            page.append(self.consent)

        def providers(self, host):
            page = self.page(1)
            self.preset = Gtk.DropDown.new_from_strings(PRESETS)
            self.preset.set_selected(provider_preset(self.config))
            host.field(page, "Provider preset", self.preset)
            page.append(
                Gtk.LinkButton.new_with_label(
                    "https://console.groq.com/keys",
                    "Create a Groq API key",
                )
            )
            page.append(
                host.label(
                    "Groq free usage has rate and quota limits. Transcription only uses one Groq key. "
                    "The Groq refinement preset is optional and still needs live quality qualification. "
                    "For a custom endpoint, use Advanced provider settings in the main window, save, "
                    "then reopen setup.",
                    "muted",
                    True,
                )
            )
            self.key_choice = Gtk.DropDown()
            host.field(page, "Key to manage", self.key_choice)
            self.key_entry = Gtk.PasswordEntry()
            self.key_entry.set_show_peek_icon(True)
            host.field(page, "Enter or replace key", self.key_entry)
            actions = host.flow()
            actions.append(host.button("Save key", self.save_key))
            actions.append(host.button("Delete key", self.delete_key))
            actions.append(host.button("Edit provider in Settings", self.open_settings))
            page.append(actions)
            self.contributor = Gtk.CheckButton(
                label="Allow Contributor provider training use of my text"
            )
            contributor_text = self.contributor.get_label()
            self.contributor.set_child(host.label(contributor_text, wrap=True))
            self.contributor.update_property([Gtk.AccessibleProperty.LABEL], [contributor_text])
            page.append(self.contributor)
            self.contributor_note = host.label(
                "Contributor models may use submitted text to train models. This is separate from "
                "Caelum history. Choose Transcription only if you do not accept that use.",
                "muted",
                True,
            )
            page.append(self.contributor_note)
            self.key_note = host.label("", "muted", True)
            page.append(self.key_note)
            self.preset.connect("notify::selected", self.change_provider)
            self.change_provider()

        def change_provider(self, *_):
            self.config = apply_provider_preset(self.config, self.preset.get_selected())
            self.validated = self.succeeded = False
            self.progress.complete = False
            self.key_names = list(
                dict.fromkeys(
                    [self.config.stt.key_env]
                    + ([self.config.cleanup.key_env] if self.config.cleanup.model else [])
                )
            )
            self.key_choice.set_model(Gtk.StringList.new(self.key_names))
            self.key_choice.set_selected(0)
            self.key_entry.set_text("")
            from .providers import needs_contributor_consent

            contributor = needs_contributor_consent(self.config.cleanup)
            self.contributor.set_visible(contributor)
            self.contributor_note.set_visible(contributor)
            self.contributor.set_active(False)
            self.key_note.set_text(
                "Continue checks the key and every selected model. No audio or transcript is sent. "
                "Saving or deleting a key takes effect for future requests, including the service."
            )

        def save_key(self):
            if self.busy:
                return
            name = self.key_names[self.key_choice.get_selected()]
            value = self.key_entry.get_text().strip()
            self.key_entry.set_text("")
            self.validated = self.succeeded = False
            self.progress.complete = False
            self.progress.save(host.path)

            def saved(storage):
                self.key_note.set_text(
                    "Key saved in the desktop keyring."
                    if storage == "keyring"
                    else "Desktop keyring unavailable. Key saved in an owner-only private file "
                    "(not encrypted). You can delete or replace it here."
                )

            self.work(lambda: credentials.store(name, value), saved)

        def delete_key(self):
            if self.busy:
                return
            name = self.key_names[self.key_choice.get_selected()]
            self.key_entry.set_text("")
            self.validated = self.succeeded = False
            self.progress.complete = False
            self.progress.save(host.path)
            self.work(
                lambda: credentials.delete(name),
                lambda _: self.key_note.set_text(
                    "Key deleted from Caelum. Existing environment keys are ignored until you save a new key. "
                    "Copies in your shell or environment file are managed separately."
                ),
            )

        def open_settings(self):
            self.close()
            host.navigate("settings")

        def microphone(self, host):
            page = self.page(2)
            self.mic = Gtk.DropDown.new_from_strings(["System default"])
            self.devices = [("System default", None)]
            host.field(page, "Microphone", self.mic)
            self.mic.connect("notify::selected", self.mic_changed)
            self.meter = Gtk.LevelBar(min_value=0, max_value=1)
            self.meter.update_property([Gtk.AccessibleProperty.LABEL], ["Microphone input level"])
            page.append(self.meter)
            page.append(
                host.label(
                    "Test input for three seconds. This is local only: nothing is uploaded, saved, or played. "
                    "Speak and check the meter. Practice dictation in the last step is a separate cloud test.",
                    "muted",
                    True,
                )
            )
            page.append(host.button("Test microphone locally · 3 seconds", self.test_mic))

        def devices_loaded(self, devices):
            if self.closed:
                return
            self.devices = [("System default", None), *dict.fromkeys(devices)]
            selected = self.config.app.microphone
            if selected is not None and not any(value == selected for _, value in self.devices):
                self.devices.append((f"{selected} · configured, not detected", selected))
            self.mic.set_model(Gtk.StringList.new([name for name, _ in self.devices]))
            self.mic.set_selected(
                next(
                    (index for index, (_, value) in enumerate(self.devices) if value == selected),
                    0,
                )
            )

        def mic_changed(self, *_):
            self.tested = self.succeeded = False
            index = self.mic.get_selected()
            if index < len(self.devices):
                self.config.app.microphone = self.devices[index][1]

        def level(self, value):
            def display():
                if not self.closed:
                    self.meter.set_value(value)
                return False

            GLib.idle_add(display)

        def ensure_idle(self):
            try:
                status = request("status")
            except (FileNotFoundError, ConnectionRefusedError):
                return
            if status.get("pending_audio") or status.get("state") in (
                "starting",
                "listening",
                "recording",
                "processing",
                "refining",
            ):
                raise RuntimeError("Finish or cancel the current dictation before testing in setup")

        def test_mic(self):
            if self.busy:
                return
            self.tested = False
            self.cancelled.clear()
            self.notice.set_text("Testing locally… Speak and watch the input meter.")

            def tested(pcm):
                self.tested = bool(pcm)
                self.notice.set_text(
                    "Microphone test passed. Audio discarded."
                    if pcm
                    else "No speech detected. Check the input and try again."
                )

            def local_test():
                self.ensure_idle()
                return record_sample(self.config, 3, self.cancelled, self.level)

            self.work(local_test, tested)

        def shortcut(self, host):
            page = self.page(3)
            self.hotkey = host.entry(self.config.app.hotkey)
            host.field(page, "Hold-to-talk shortcut", self.hotkey)
            page.append(
                host.label(
                    "Enter a chord such as SUPER + ALT + V. Hyprland conflicts are checked before "
                    "continuing. Other desktops check conflicts in their permission dialog when "
                    "the service starts. You can decline and use Record / Finish recording instead. "
                    "A shortcut recorder is also available in Settings.",
                    "muted",
                    True,
                )
            )

        def practice_page(self, host):
            page = self.page(4)
            page.append(
                host.label(
                    "Record a five-second practice sample. Say a short sentence after pressing Record. "
                    "The result appears below. It is not pasted into another app or saved to history.",
                    wrap=True,
                )
            )
            self.upload = Gtk.CheckButton(
                label="Send this practice sample to my selected providers"
            )
            upload_text = self.upload.get_label()
            self.upload.set_child(host.label(upload_text, wrap=True))
            self.upload.update_property([Gtk.AccessibleProperty.LABEL], [upload_text])
            page.append(self.upload)
            self.practice_button = host.button(
                "Record practice · 5 seconds", self.run_practice, "primary"
            )
            page.append(self.practice_button)
            self.result = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            self.result.set_size_request(-1, 130)
            self.result.update_property(
                [Gtk.AccessibleProperty.LABEL], ["Practice dictation result"]
            )
            page.append(self.result)
            self.copy_button = host.button("Copy practice text", self.copy_practice)
            self.copy_button.set_sensitive(False)
            page.append(self.copy_button)

        def run_practice(self):
            if self.busy:
                return
            if not self.upload.get_active():
                self.notice.set_text("Select the practice upload consent before recording.")
                return
            if not (self.validated and self.tested):
                self.stage = 1
                self.notice.set_text(
                    "Validate providers and test the microphone before practicing."
                )
                self.render()
                return
            self.succeeded = False
            self.result.get_buffer().set_text("")
            self.copy_button.set_sensitive(False)
            self.cancelled.clear()
            self.notice.set_text("Recording for five seconds… Speak now. Close setup to cancel.")

            def run_sample():
                self.ensure_idle()
                pcm = record_sample(self.config, 5, self.cancelled)
                if not pcm:
                    raise RuntimeError("No speech detected. Try recording again")
                return asyncio.run(practice(self.config, pcm, self.cancelled))

            def completed(result):
                text, refined = result
                self.result.get_buffer().set_text(text)
                self.succeeded = bool(text)
                self.copy_button.set_sensitive(self.succeeded)
                self.notice.set_text(
                    "Practice succeeded. Text is shown here only; no history or automatic paste. "
                    + (
                        "Refinement applied."
                        if refined
                        else "Raw transcription; refinement skipped or unavailable."
                    )
                )

            self.work(run_sample, completed)

        def copy_practice(self):
            buffer = self.result.get_buffer()
            host.copy_text(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False))
            self.notice.set_text(
                "Copied. Paste into your chosen app. Clipboard managers may retain it."
            )

        def go_back(self):
            if not self.busy:
                self.stage = max(0, self.stage - 1)
                self.render()

        def advance(self):
            if self.busy:
                return
            if self.stage == 0:
                if self.consent.get_active():
                    self.stage = 1
                    self.render()
            elif self.stage == 1:
                if self.contributor.get_visible() and not self.contributor.get_active():
                    self.notice.set_text(
                        "Accept Contributor training use or choose another provider."
                    )
                    return

                from .providers import contributor_scope

                self.config.cleanup.contributor_consent = (
                    contributor_scope(self.config.cleanup) if self.contributor.get_active() else ""
                )
                self.validated = False

                def validated(_):
                    self.validated = True
                    self.stage = 2
                    self.notice.set_text("Provider key and selected models validated.")
                    host.config = deepcopy(self.config)
                    host.sync_setup_settings()

                def verify_and_save():
                    asyncio.run(validate_providers(self.config))
                    save(self.config, host.path)

                self.work(verify_and_save, validated)
            elif self.stage == 2:
                if not self.tested:
                    self.notice.set_text("Pass the local microphone test before continuing.")
                    return
                self.stage = 3
                self.render()
            elif self.stage == 3:
                self.config.app.hotkey = self.hotkey.get_text().strip().upper()

                def checked(message):
                    host.config = deepcopy(self.config)
                    self.stage = 4
                    self.notice.set_text(message)

                def check_and_save():
                    message = asyncio.run(check_shortcut(self.config))
                    save(self.config, host.path)
                    return message

                self.work(check_and_save, checked)
            elif self.succeeded and self.validated and self.tested:
                self.progress.complete = True
                self.progress.stage = 4
                self.progress.save(host.path)
                host.config = deepcopy(self.config)
                host.set_devices(
                    [(name, value) for name, value in self.devices if value is not None]
                )
                self.close()

                def apply_runtime():
                    try:
                        request("reload")
                        return "Setup complete. Settings applied to the running service."
                    except (FileNotFoundError, ConnectionRefusedError):
                        return "Setup complete. Start the service when you are ready to dictate."
                    except (RuntimeError, OSError):
                        return "Setup complete. Stop and restart the service to apply your new settings."

                host.work(apply_runtime, host.message)

        def render(self):
            if self.closed:
                return
            self.heading.set_text(
                (
                    "Welcome to Caelum",
                    "Connect your provider",
                    "Test your microphone",
                    "Choose your shortcut",
                    "Try a dictation",
                )[self.stage]
            )
            self.pages.set_visible_child_name(str(self.stage))
            self.pages.set_sensitive(not self.busy)
            self.back.set_sensitive(not self.busy and self.stage > 0)
            self.next.set_label("Finish setup" if self.stage == 4 else "Continue")
            self.next.set_sensitive(
                not self.busy
                and (
                    (self.stage != 0 or self.consent.get_active())
                    and (self.stage != 4 or self.succeeded)
                )
            )
            self.progress.stage = self.stage
            self.progress.save(host.path)

        def close_setup(self, _):
            if not self.busy:
                try:
                    self.config.app.hotkey = self.hotkey.get_text().strip().upper()
                    validate(self.config)
                    save(self.config, host.path)
                    host.config = deepcopy(self.config)
                except (ValueError, OSError):
                    host.message("Setup paused. Invalid or unwritable settings were not saved.")
            self.closed = True
            self.cancelled.set()
            self.key_entry.set_text("")
            self.result.get_buffer().set_text("")
            host.setup_window = None
            host.sync_setup_settings()
            return False

    window = Setup()
    host.setup_window = window
    window.present()
    return window
