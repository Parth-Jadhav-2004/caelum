"""UI-independent desktop operations shared by the sidecar and CLI."""

import json
import os
import socket
import time
from copy import deepcopy
from pathlib import Path

from .config import validate


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
    from .pulse import microphones as server_microphones

    devices = server_microphones()
    if devices is not None:
        return devices
    import sounddevice as sound

    return [
        (device["name"], device["name"])
        for device in sound.query_devices()
        if device["max_input_channels"] > 0
    ]


PRESETS = ("Groq", "Transcription only", "Custom provider")


def microphone_selection(selected, devices):
    if selected is None or any(value == selected for _, value in devices):
        return selected
    matches = [value for label, value in devices if label == selected]
    return matches[0] if len(matches) == 1 else selected


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
            else "Press your shortcut to start; press again to stop."
            if status.get("recording_mode") == "toggle"
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
