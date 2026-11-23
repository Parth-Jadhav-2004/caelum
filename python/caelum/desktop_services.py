"""UI-independent desktop operations shared by the sidecar and CLI."""

import json
import os
import socket
import time
from copy import deepcopy
from pathlib import Path

from .config import validate

# A valid replacement dictionary can exceed 64 KiB (200 entries, Unicode
# keys/values). Keep the local control channel bounded even for escaped JSON.
CONTROL_FRAME_LIMIT = 4 * 1024 * 1024


class SettingsBusy(RuntimeError):
    """Transient: the active session cannot accept a model switch yet."""


def request(action, *, config=None, progress=None):
    if os.name == "nt":
        from .windows_desktop import request as windows_request

        return windows_request(action, config=config, progress=progress)
    root = os.environ.get("XDG_RUNTIME_DIR")
    if not root:
        raise RuntimeError("Open Caelum inside your desktop session")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(310 if config is not None else 2)
        client.connect(str(Path(root) / "caelum/control.sock"))
        client.sendall(json.dumps({"action": action, **({"config": config} if config is not None else {}),
                                 **({"progress": progress} if progress is not None else {})}).encode() + b"\n")
        result = json.loads(client.makefile("r").readline(65536))
        if "error" in result:
            if result.get("error_code") == "settings_busy":
                raise SettingsBusy(result["error"])
            raise RuntimeError(result["error"])
        return result


def install_queued_update():
    from .updates import apply_pending

    try:
        request("prepare-update")
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
        return apply_pending()


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

    if os.name == "nt":
        # MME, WASAPI and DirectSound frequently expose the same friendly name.
        apis = sound.query_hostapis()
        return [(f"{device['name']} · {apis[device['hostapi']]['name']}", index)
                for index, device in enumerate(sound.query_devices()) if device["max_input_channels"]]
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
            if title == "Transcription" and config.stt.engine == "local":
                try:
                    await provider.models(settings)
                    results.append("Transcription: speech model found (offline)")
                except ProviderError as error:
                    results.append(f"Transcription: {error}")
                continue
            if title == "Refinement" and config.stt.engine == "local":
                results.append("Refinement: off (offline mode)")
                continue
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
                    f"{title}: key missing; open Settings → Transcription → Manage keys"
                    if error.kind == "missing_key"
                    else f"{title}: {error}"
                )
    finally:
        await provider.aclose()
    return "\n".join(results)


def service_presentation(status):
    if not status:
        return "Stopped", "Start the service to record."
    if status.get("paused"):
        return "Paused", "Resume to use the recording shortcut."
    state = status.get("state", "hidden")
    engine = status.get("engine")
    if state in ("hidden", "success", "unrefined", "no_speech", "model_ready") and engine:
        if engine["state"] == "loading":
            return "Getting ready…", "Your speech model is loading."
        if engine["state"] == "unloaded":
            return "Model resting", "The model will load when you next dictate."
        if engine["state"] in ("error", "missing"):
            return "Speech model needs attention", engine["message"] or "Open Settings to download a model."
        if state == "hidden":
            return ("Ready · On this computer" if engine["kind"] == "local" else "Ready · Online",
                    "Your local speech model is selected." if engine["kind"] == "local" else
                    "Audio is sent to your provider.")
    if state == "error":
        if status.get("pending_audio"):
            if status.get("error_kind") == "clipboard":
                return "Awaiting retry", "Choose Retry to copy the finished text, then paste it in your app."
            guidance = {
                "invalid_key": "Replace the key in Settings → Transcription → Manage keys, then retry.",
                "missing_key": "Add the key in Settings → Transcription → Manage keys, then retry.",
                "quota": "Check provider usage or billing before retrying.",
                "rate_limit": "Wait for the provider rate limit to reset, then retry.",
                "offline": "Check your network connection, then retry.",
                "timeout": "The provider timed out. Retry when the connection is stable.",
                "model": "Choose an available model in Settings.",
                "local_setup": "Speech model needs attention. Open Settings and check files.",
            }.get(status.get("error_kind"), "Retry or cancel before the recording expires.")
            return "Awaiting retry", guidance + " Pending audio stays in memory only."
        if status.get("error_kind") in ("microphone", "capture"):
            return "Microphone unavailable", "Open Settings to choose a microphone and test input."
        return "Recording failed", "Check Settings and try recording again."
    labels = {
        "model_downloading": ("Downloading speech model", "The download continues in the background."),
        "model_stalled": ("Download stalled", "Waiting for the connection. Open Settings for details."),
        "model_loading": ("Loading speech model", "Getting the local model ready."),
        "model_ready": ("Model ready", "Local dictation is ready."),
        "model_failed": ("Model failed", "Open Settings to retry. Your previous model is unchanged."),
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
        "recording": (
            "Recording",
            "Choose Finish recording to transcribe." if status.get("backend") == "portable"
            else "Press your shortcut again to finish." if status.get("recording_mode") == "toggle"
            else "Release your shortcut to transcribe.",
        ),
        "processing": ("Processing", "Transcribing your recording."),
        "loading": ("Getting ready…", "Your speech model is loading."),
        "missing_model": ("Speech model not downloaded", "Open Caelum to download a speech model."),
        "success_fallback_online": ("Done · used Online", "This dictation used your online provider."),
        "success_fallback_local": ("Done · used this computer", "Your local model transcribed the recording after an online attempt."),
        "refining": ("Processing", "Refining punctuation and formatting."),
        "success": ("Done", "Refined text was sent to the original application."),
        "unrefined": (
            "Done · unrefined",
            "Raw transcription was sent to the original application.",
        ),
        "copied": ("Copied", "Paste manually in the intended application."),
        "ready_to_copy": ("Transcript ready", "Choose Copy transcript to paste it into your app."),
        "saved": ("Saved", "Use Copy text below, then paste into your chosen app."),
        "no_speech": ("No speech detected", "Nothing inserted. Try recording again."),
    }
    title, detail = labels.get(state, ("Ready", "Use your shortcut or Record to begin."))
    metrics = status.get("metrics") or []
    completed = state in ("success", "unrefined", "saved", "copied", "ready_to_copy", "success_fallback_local")
    last = metrics[-1] if metrics else {}
    if completed and last.get("cleanup_error") == "local_refinement_fallback":
        if state == "unrefined":
            title, detail = "Done", "Transcription was sent to the original application."
        detail += " Used built-in formatting; the local text model did not return a usable edit."
    elif state == "unrefined" and last.get("cleanup_mode") == "local_rules":
        title, detail = "Done", "Local formatting finished. No edits were needed."
    elif state in ("saved", "copied") and metrics and not last.get("cleanup_refined") and last.get("cleanup_mode") != "local_rules":
        detail += " Raw transcription; refinement was skipped or unavailable."
    if state in ("saved", "copied") and metrics and metrics[-1].get("fallback"):
        title = "Done · used Online" if metrics[-1]["fallback"] == "online" else "Done · used this computer"
    return title, detail
