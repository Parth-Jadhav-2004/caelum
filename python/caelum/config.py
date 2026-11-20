import json
import os
import re
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_HOTKEY = "CTRL + SUPER"
PORTAL_HOTKEY = "SUPER + ALT + V"


def resolve_backend(backend="auto"):
    if os.name == "nt":
        return "windows"
    if backend != "auto":
        return backend
    return "hyprland" if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") else "portable"


def default_hotkey(backend="auto"):
    return PORTAL_HOTKEY if resolve_backend(backend) == "portable" else DEFAULT_HOTKEY


@dataclass
class App:
    backend: str = "auto"
    hotkey: str = field(default_factory=default_hotkey)
    recording_mode: str = "hold"
    strategy: str = "single"
    max_recording_seconds: int = 180
    minimum_recording_ms: int = 200
    retry_expiry_seconds: int = 60
    reduced_motion: bool = False
    high_contrast: bool = False
    microphone: str | int | None = None
    silence_dbfs: float = -60.0


@dataclass
class STT:
    engine: str = "online"
    local_model: str = ""
    local_threads: int = 0
    fallback: str = "none"
    local_device: str = "auto"
    local_idle_seconds: int = 300
    local_timeout_seconds: float = 300.0
    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "whisper-large-v3-turbo"
    key_env: str = "GROQ_API_KEY"
    language: str = ""
    vocabulary: str = ""
    timeout_seconds: float = 15.0
    chunk_seconds: float = 7.0
    overlap_seconds: float = 0.8
    concurrency: int = 2


@dataclass
class Cleanup:
    style: str = "light"
    replacements: dict = field(default_factory=dict)
    base_url: str = "https://api.groq.com/openai/v1"
    key_env: str = "GROQ_API_KEY"
    model: str = ""
    contributor_consent: str = ""
    reasoning_effort: str = ""
    timeout_seconds: float = 1.8


@dataclass
class Desktop:
    history_enabled: bool = True
    auto_copy: bool = True
    check_updates: bool = True
    theme: str = "dark"
    color_theme: str = "caelum"
    sidebar_visible: bool = True
    history_forever: bool = False
    retention_days: int = 30
    stt_usd_per_hour: float = 0.0


@dataclass
class Config:
    app: App = field(default_factory=App)
    stt: STT = field(default_factory=STT)
    cleanup: Cleanup = field(default_factory=Cleanup)
    desktop: Desktop = field(default_factory=Desktop)


def config_path():
    if os.name == "nt":
        return Path(os.environ["APPDATA"]) / "Caelum/config.toml"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "caelum/config.toml"


def data_dir():
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "Caelum"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "caelum"


def load(path=None):
    path = Path(path) if path else config_path()
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    if set(data) - {"app", "stt", "cleanup", "desktop"}:
        raise ValueError("Unknown configuration section")
    config = Config()
    for section, cls in (("app", App), ("stt", STT), ("cleanup", Cleanup), ("desktop", Desktop)):
        values = data.get(section, {}).copy()
        if section == "app" and "hotkey" not in values:
            values["hotkey"] = default_hotkey(values.get("backend", "auto"))
        if section == "stt":
            # Ignore retired preview settings when upgrading; never execute them.
            for retired in ("local_binary", "local_model_path"):
                values.pop(retired, None)
        if set(values) - {f.name for f in fields(cls)}:
            raise ValueError(f"Unknown option in {section}")
        if section == "cleanup" and "style" not in values:
            values["style"] = "thorough" if values.get("reasoning_effort") == "high" else "light"
        defaults = cls()
        for key, value in values.items():
            expected = getattr(defaults, key)
            if expected is None:
                valid = isinstance(value, (str, int)) and not isinstance(value, bool)
            elif isinstance(expected, float):
                valid = type(value) in (int, float)
            else:
                valid = type(value) is type(expected)
            if not valid:
                raise ValueError(f"Invalid type for {section}.{key}")
        setattr(config, section, cls(**values))
    return validate(config)


def validate(config):
    a, s, c = config.app, config.stt, config.cleanup
    # The pre-catalog preview called Online "cloud". Preserve those configs.
    if s.engine == "cloud":
        s.engine = "online"
    if s.engine not in ("online", "local"):
        raise ValueError("Transcription engine must be online or local")
    if s.fallback not in ("none", "online", "local") or s.fallback == s.engine:
        raise ValueError("Fallback must be none or the other transcription engine")
    if type(s.local_threads) is not int or not 0 <= s.local_threads <= 256:
        raise ValueError("Local thread count must be between 0 and 256")
    if s.local_model:
        from .models import ModelError, get_model

        try:
            get_model(s.local_model)
        except ModelError:
            raise ValueError("Choose a known local speech model") from None
    if s.local_device not in ("auto", "gpu", "cpu"):
        raise ValueError("Local device must be auto, gpu, or cpu")
    if type(s.local_idle_seconds) is not int or not 0 <= s.local_idle_seconds <= 3600:
        raise ValueError("Idle unload must be between 0 and 3600 seconds")
    if not 10 <= s.local_timeout_seconds <= 1800:
        raise ValueError("Local timeout is invalid")
    if (not isinstance(c.replacements, dict) or len(c.replacements) > 200
            or any(not isinstance(key, str) or not key.strip() or len(key) > 200
                   or not isinstance(value, str) or len(value) > 1000
                   for key, value in c.replacements.items())):
        raise ValueError("Dictionary replacements must contain up to 200 text pairs")
    if len(s.vocabulary) > 4000:
        raise ValueError("Custom vocabulary must be at most 4000 characters")
    if c.style not in ("light", "thorough", "email", "casual", "code"):
        raise ValueError("Unknown cleanup style")
    if a.backend not in ("auto", "hyprland", "portable"):
        raise ValueError("backend must be auto, hyprland, or portable")
    if config.desktop.theme not in ("system", "light", "dark"):
        raise ValueError("Theme must be system, light, or dark")
    if config.desktop.color_theme not in ("t3-code", "t3-chat", "grove", "ocean", "ember", "iris", "caelum", "caelum-iris", "caelum-ochre"):
        raise ValueError("Unknown color theme")
    if not 1 <= config.desktop.retention_days <= 3650:
        raise ValueError("Retention must be between 1 and 3650 days")
    if not 0 <= config.desktop.stt_usd_per_hour <= 1000:
        raise ValueError("STT hourly rate must be between 0 and 1000 USD")
    if a.recording_mode not in ("hold", "toggle"):
        raise ValueError("recording_mode must be hold or toggle")
    if a.strategy not in ("single", "chunked"):
        raise ValueError("strategy must be single or chunked")
    if not 1 <= a.max_recording_seconds <= 600 or not 100 <= a.minimum_recording_ms <= 2000:
        raise ValueError("Recording bounds are invalid")
    if not 1 <= a.retry_expiry_seconds <= 300 or not -90 <= a.silence_dbfs <= -30:
        raise ValueError("Retry/silence bounds are invalid")
    if not 2 <= s.chunk_seconds <= 15 or not 0.2 <= s.overlap_seconds < s.chunk_seconds / 2:
        raise ValueError("Chunk/overlap bounds are invalid")
    if not 1 <= s.concurrency <= 3 or not 1 <= s.timeout_seconds <= 60:
        raise ValueError("STT timeout/concurrency out of bounds")
    if not 0.2 <= c.timeout_seconds <= 10:
        raise ValueError("Cleanup timeout must be between 0.2 and 10 seconds")
    if c.reasoning_effort not in ("", "none", "minimal", "low", "medium", "high", "xhigh", "max"):
        raise ValueError("Invalid cleanup reasoning_effort")
    if not re.fullmatch(r"(?:[A-Z0-9_]+\s*\+\s*)*[A-Z0-9_]+", a.hotkey):
        raise ValueError("hotkey must use uppercase key names")
    pieces = [piece.strip() for piece in a.hotkey.split("+")]
    if len(pieces) < 2 or any(
        piece not in {"SUPER", "ALT", "CTRL", "SHIFT"} for piece in pieces[:-1]
    ):
        raise ValueError("Hotkey needs a SUPER, ALT, CTRL, or SHIFT modifier")
    modifier_only = pieces[-1] in {"SUPER", "ALT", "CTRL", "SHIFT"}
    modifiers = pieces if modifier_only else pieces[:-1]
    if len(set(modifiers)) != len(modifiers):
        raise ValueError("Hotkey modifiers must not repeat")
    for provider in (s, c):
        if s.engine == "local" and s.fallback != "online":
            continue  # Neither audio nor cleanup text can leave this machine.
        url = urlparse(provider.base_url)
        if url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1")
        ):
            raise ValueError("Provider URL must use HTTPS (except localhost)")
        if url.username or url.password or url.query or url.fragment or not url.hostname:
            raise ValueError("Invalid provider URL")
    return config


def save(config, path=None):
    path = Path(path) if path else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, values in asdict(config).items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            if value is not None:
                encoded = ("{ " + ", ".join(json.dumps(k, ensure_ascii=False) + " = " +
                           json.dumps(v, ensure_ascii=False) for k, v in value.items()) + " }"
                           if isinstance(value, dict) else json.dumps(value, ensure_ascii=False))
                lines.append(f"{key} = {encoded}")
        lines.append("")
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".caelum-")
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write("\n".join(lines))
            output.flush()
            os.fsync(output.fileno())
        load(temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
