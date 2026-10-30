import json
import os
import re
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class App:
    hotkey: str = "SUPER + ALT + V"
    strategy: str = "single"
    max_recording_seconds: int = 120
    minimum_recording_ms: int = 200
    retry_expiry_seconds: int = 60
    reduced_motion: bool = False
    high_contrast: bool = False
    microphone: str | int | None = None
    silence_dbfs: float = -60.0


@dataclass
class STT:
    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "whisper-large-v3-turbo"
    key_env: str = "GROQ_API_KEY"
    language: str = ""
    vocabulary: str = "Caelum, Omarchy, Hyprland"
    timeout_seconds: float = 15.0
    chunk_seconds: float = 7.0
    overlap_seconds: float = 0.8
    concurrency: int = 2


@dataclass
class Cleanup:
    base_url: str = "https://api.openai.com/v1"
    key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-6-luna"
    reasoning_effort: str = "none"
    timeout_seconds: float = 1.8


@dataclass
class Desktop:
    theme: str = "dark"
    retention_days: int = 30
    stt_usd_per_hour: float = 0.0


@dataclass
class Config:
    app: App = field(default_factory=App)
    stt: STT = field(default_factory=STT)
    cleanup: Cleanup = field(default_factory=Cleanup)
    desktop: Desktop = field(default_factory=Desktop)


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "caelum/config.toml"


def load(path=None):
    path = Path(path) if path else config_path()
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    if set(data) - {"app", "stt", "cleanup", "desktop"}:
        raise ValueError("Unknown configuration section")
    config = Config()
    for section, cls in (("app", App), ("stt", STT), ("cleanup", Cleanup), ("desktop", Desktop)):
        values = data.get(section, {}).copy()
        if section == "desktop" and "history_enabled" in values:
            if type(values.pop("history_enabled")) is not bool:
                raise ValueError("Invalid type for desktop.history_enabled")
        if set(values) - {f.name for f in fields(cls)}:
            raise ValueError(f"Unknown option in {section}")
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
    a, s, c = config.app, config.stt, config.cleanup
    if config.desktop.theme not in ("light", "dark"):
        raise ValueError("Theme must be light or dark")
    if not 1 <= config.desktop.retention_days <= 3650:
        raise ValueError("Retention must be between 1 and 3650 days")
    if not 0 <= config.desktop.stt_usd_per_hour <= 1000:
        raise ValueError("STT hourly rate must be between 0 and 1000 USD")
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
        raise ValueError("hotkey must use uppercase Hyprland key names")
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
                lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
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
