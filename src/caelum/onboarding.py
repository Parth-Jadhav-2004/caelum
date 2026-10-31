"""Resumable setup and explicitly consented, bounded practice recording."""

import asyncio
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .audio import Capture
from .config import validate
from .portable import backend_name
from .providers import ProviderError, Providers

PRIVACY = (
    "Audio is sent to your transcription provider. When refinement is on, text is sent "
    "to your refinement provider. Regular dictations save final text in local history when "
    "Save dictation history is on (disable it in Settings → History & desktop) "
    "and may use the clipboard. Practice text stays in this setup window unless you copy it. "
    "History is not encrypted by Caelum. Exports and clipboard managers keep independent copies. "
    "Groq free usage has provider limits."
)


@dataclass
class Progress:
    stage: int = 0
    complete: bool = False

    @classmethod
    def load(cls, config_path):
        path = Path(config_path).with_name("onboarding.json")
        try:
            data = json.loads(path.read_text())
            return cls(max(0, min(4, int(data["stage"]))), data["complete"] is True)
        except (OSError, ValueError, KeyError, TypeError):
            return cls()

    def save(self, config_path):
        path = Path(config_path).with_name("onboarding.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".setup-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(asdict(self), stream)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


async def validate_providers(config):
    validate(config)
    provider = Providers(config)
    try:
        for title, settings in (("Transcription", config.stt), ("Refinement", config.cleanup)):
            if not settings.model:
                if title == "Transcription":
                    raise ValueError("Choose a transcription model")
                continue
            if settings.model not in await provider.models(settings):
                raise ProviderError(f"{title} model unavailable; choose another model", "model")
    finally:
        await provider.client.aclose()


async def check_shortcut(config):
    validate(config)
    if backend_name(config) == "hyprland":
        from .linux import hypr_json, shortcut_keys

        if (await hypr_json("status")).get("configProvider") != "lua":
            raise RuntimeError("This Hyprland session needs Lua integration; use portable mode")
        starts, _ = shortcut_keys(config.app.hotkey)
        binds = await hypr_json("binds")
        if any(
            item["key"].upper() == key.upper()
            and item["modmask"] == mask
            and not item.get("description", "").startswith("Caelum")
            for _, key, mask in starts
            for item in binds
        ):
            raise RuntimeError("Shortcut is already in use. Choose another shortcut")
        return "Shortcut is available on Hyprland."
    from .portable import portal_trigger

    if portal_trigger(config.app.hotkey) is None:
        raise ValueError("Choose a shortcut with a non-modifier key on this desktop")
    return (
        "Your desktop checks conflicts and may ask permission when the service starts. "
        "If permission is declined or shortcuts are unavailable, use Record / Finish recording."
    )


def record_sample(config, seconds, cancelled, level=lambda value: None):
    capture = Capture(config.app)
    try:
        capture.start()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if cancelled.is_set():
                raise RuntimeError("Recording cancelled; sample discarded")
            if capture.error:
                raise RuntimeError("Microphone interrupted; choose an input and test again")
            level(capture.level)
            time.sleep(0.04)
        if cancelled.is_set():
            raise RuntimeError("Recording cancelled; sample discarded")
        capture.stop()
        return capture.snapshot() if capture.speech_ms >= 80 else b""
    finally:
        try:
            capture.stop()
        finally:
            capture.discard()
            level(0)


async def practice(config, pcm, cancelled):
    provider = Providers(config)

    async def transcribe():
        raw = (await provider.stt(pcm)).text
        if not raw:
            raise RuntimeError("No speech detected. Try the practice recording again")
        text, refined = await provider.cleanup(raw)
        return text, refined

    task = asyncio.create_task(transcribe())
    try:
        while not task.done():
            if cancelled.is_set():
                raise RuntimeError("Practice cancelled; sample discarded")
            await asyncio.sleep(0.05)
        return await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await provider.client.aclose()
