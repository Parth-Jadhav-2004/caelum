"""Shared desktop contract, using a deliberately small JSON Schema vocabulary.

This is also generated into the frontend. No eval/code generation at runtime,
network schema loading, credential values, or provider response bodies.
"""

import math
from dataclasses import fields

from .config import STT, App, Cleanup, Desktop, InvalidConfig

STRING = {"type": "string"}
NUMBER = {"type": "number"}
BOOL = {"type": "boolean"}
NULL = {"type": "null"}


def obj(properties=None, optional=(), extra=False):
    properties = properties or {}
    return {
        "type": "object",
        "properties": properties,
        "required": [key for key in properties if key not in optional],
        "additionalProperties": extra,
    }


def array(items):
    return {"type": "array", "items": items}


def union(*items):
    return {"anyOf": items}


CONFIG = obj(
    {
        name: obj(
            {
                field.name: {str: STRING, int: NUMBER, float: NUMBER, bool: BOOL,
                             dict: {"type": "object", "additionalProperties": STRING}}.get(
                    field.type, union(STRING, NUMBER, NULL)
                )
                for field in fields(cls)
            }
        )
        for name, cls in (("app", App), ("stt", STT), ("cleanup", Cleanup), ("desktop", Desktop))
    }
)
# Existing JSONL clients may patch a subset of configuration. Bootstrap still
# requires the complete shape; Python's semantic validation applies after merge.
PATCH_CONFIG = obj(
    {section: {**schema, "required": []} for section, schema in CONFIG["properties"].items()},
    optional=tuple(CONFIG["properties"]),
)
STATUS = obj(
    {
        "running": BOOL,
        "state": STRING,
        "title": STRING,
        "detail": STRING,
        "paused": BOOL,
        "pending_audio": BOOL,
        "can_copy": BOOL,
        "storage_error": BOOL,
        "notice": STRING,
        "backend": STRING,
        "hotkey": STRING,
        "shortcut_mode": STRING,
        "shortcut_description": STRING,
        "engine": obj({
            "kind": {"enum": ["online", "local"]}, "model": union(STRING, NULL),
            "state": {"enum": ["ready", "loading", "error", "missing", "unloaded"]}, "message": STRING,
        }),
        "feedback": obj(
            {"state": STRING, "elapsed_ms": NUMBER, "history": array(NUMBER), "level": NUMBER},
            extra=True,
        ),
    },
    optional=(
        "pending_audio", "can_copy", "storage_error", "notice", "backend", "hotkey",
        "shortcut_mode", "shortcut_description", "feedback", "engine",
    ),
    extra=True,
)
ACK = obj({"ok": {"enum": [True]}})
STRINGS = {"type": "object", "additionalProperties": STRING}
METHODS = {}


def method(name, params=None, result=ACK):
    METHODS[name] = {"params": params or obj(), "result": result}


method(
    "bootstrap",
    result=obj(
        {
            "version": {"enum": [1]},
            "config": CONFIG,
            "privacy": STRING,
            "setup": obj({"stage": NUMBER, "complete": BOOL}),
            "autostart": BOOL,
            "credentials": {
                "type": "object",
                "additionalProperties": union(
                    STRING, obj({"description": STRING, "storage": STRING})
                ),
            },
        }
    ),
)
method("status", result=STATUS)
method(
    "history",
    obj({"query": STRING}, optional=("query",)),
    array(
        obj(
            {
                "id": STRING,
                "created_at": STRING,
                "final_transcript": STRING,
                "duration_ms": NUMBER,
                "word_count": NUMBER,
                "refined": NUMBER,
                "copied": NUMBER,
            },
            extra=True,
        )
    ),
)
method(
    "summary",
    result=obj(
        {
            **{
                key: NUMBER
                for key in ("total_words", "today_words", "month_words", "wpm", "duration_ms")
            },
            "daily": {"type": "object", "additionalProperties": NUMBER},
            "activity": {"type": "object", "additionalProperties": NUMBER},
        },
        extra=True,
    ),
)
method("devices", result=array(obj({"label": STRING, "value": union(STRING, NUMBER, NULL)})))
method("history.delete", obj({"id": STRING}, optional=("id",)))
method("history.export", obj({"path": STRING}))
method("settings.reset_invalid", result=obj({"backup_path": STRING}))
method(
    "settings.save",
    obj({"config": PATCH_CONFIG}),
    obj({"saved": BOOL, "warning": STRING}, optional=("warning",)),
)
method("service.start")
method("service.stop", obj({"discard": BOOL}, optional=("discard",)))
# The daemon replies with an acknowledgment, sometimes accompanied by status.
method(
    "control",
    obj(
        {
            "action": {"enum": ["start", "stop", "cancel", "retry", "pause", "resume", "copy"]},
            "discard": BOOL,
        },
        optional=("discard",),
    ),
    obj({"ok": BOOL}, extra=True),
)
method("providers.check", result=STRING)
method("credentials.store", obj({"name": STRING, "value": STRING}), STRING)
method("credentials.delete", obj({"name": STRING}))
method("microphone.test")
method("practice", obj({"consent": BOOL, "interactive": BOOL, "insert": BOOL},
                       optional=("interactive", "insert")),
       obj({"text": STRING, "refined": BOOL, "inserted": BOOL}, optional=("inserted",)))
method("sample.cancel", obj({"finish": BOOL}, optional=("finish",)))
method(
    "setup.validate",
    obj({"consent": BOOL, "keys": STRINGS}, optional=("keys",)),
    obj({"storage": STRINGS}),
)
method("shortcut.check", obj({"accept_manual": BOOL}, optional=("accept_manual",)),
       obj({"state": {"enum": ["available", "pending", "manual"]}, "message": STRING}))
method("setup.finish", obj({"skip_practice": BOOL}, optional=("skip_practice",)))
method("setup.stage", obj({"stage": {"enum": [0, 1, 2, 3]}}))
method("setup.skip")
method(
    "launcher", obj({"autostart": BOOL, "enabled": BOOL}, optional=("autostart", "enabled")), STRING
)
method("updates.check", result=union(obj({"version": STRING}), NULL))
method("updates.testing", result=union(obj({"version": STRING, "installed": BOOL}), NULL))
method("updates.stage", result=STRING)
method("updates.apply", result={"enum": ["installed", "installer_launched", "no_update"]})
method("updates.discard")
method("updates.pending", result=union(
    NULL, obj({"state": {"enum": ["unverified"]}, "version": NULL}),
    obj({"state": {"enum": ["queued", "installed"]}, "version": STRING}),
))
method("shutdown", obj({"discard": BOOL}, optional=("discard",)))

MODEL_PROGRESS = obj({
    "id": STRING,
    "state": {"enum": ["queued", "downloading", "stalled", "paused", "verifying", "installing",
                       "ready", "failed", "cancelled"]},
    "received_bytes": NUMBER, "total_bytes": NUMBER, "bytes_per_sec": NUMBER,
    "eta_seconds": union(NUMBER, NULL),
    "error": union(obj({"code": STRING, "message": STRING}), NULL),
}, extra=True)
MODEL = obj({
    "id": STRING, "tier": STRING, "label": STRING, "blurb": STRING,
    "languages": array(STRING), "auto_language": BOOL, "download_bytes": NUMBER,
    "disk_bytes": NUMBER, "licence": obj({"id": STRING, "url": STRING, "attribution": STRING}),
    "wer": obj(extra=True),
    "state": {"enum": ["not_installed", "queued", "downloading", "stalled", "paused", "verifying",
                       "installing", "installed", "failed", "cancelled", "ready"]},
    "received_bytes": NUMBER, "total_bytes": NUMBER, "bytes_per_sec": NUMBER,
    "eta_seconds": union(NUMBER, NULL),
    "error": union(obj({"code": STRING, "message": STRING}), NULL),
    "in_use": BOOL, "visible": BOOL, "disabled_reason": union(STRING, NULL),
    "requires_extra": union(STRING, NULL), "stored_in": STRING,
    "decode_ms": union(NUMBER, NULL),
}, extra=True)
method("models.list", obj({"language": STRING}, optional=("language",)), result=obj({
    "hardware": obj(extra=True),
    "recommended": obj({"id": union(STRING, NULL), "reason_code": STRING, "reason_text": STRING}),
    "models": array(MODEL), "pending_use": union(STRING, NULL), "storage_bytes": NUMBER,
}))
for operation in ("download", "pause", "resume", "cancel"):
    method(f"models.{operation}", obj({"id": STRING}))
method("models.remove", obj({"id": STRING}), obj({"freed_bytes": NUMBER}))
method("models.verify", obj({"id": STRING}), obj({"ok": BOOL, "bad_files": array(STRING)}))
method("models.use", obj({"id": STRING, "when_ready": BOOL}, optional=("when_ready",)),
       obj({"saved": BOOL}))


def matches(schema, value):
    if "anyOf" in schema:
        return any(matches(item, value) for item in schema["anyOf"])
    if "enum" in schema:
        return any(type(item) is type(value) and item == value for item in schema["enum"])
    kind = schema["type"]
    if kind == "null":
        return value is None
    if kind == "boolean":
        return type(value) is bool
    if kind == "string":
        return isinstance(value, str)
    if kind == "number":
        return type(value) in (int, float) and math.isfinite(value)
    if kind == "array":
        return isinstance(value, list) and all(matches(schema["items"], item) for item in value)
    if kind != "object" or not isinstance(value, dict):
        return False
    properties = schema.get("properties", {})
    if any(key not in value for key in schema.get("required", ())):
        return False
    extra = schema.get("additionalProperties", False)
    return all(
        matches(properties[key], item)
        if key in properties
        else extra
        if isinstance(extra, bool)
        else matches(extra, item)
        for key, item in value.items()
    )


def validate_request(method_name, params):
    if method_name not in METHODS:
        raise ValueError("Unknown method")
    if not matches(METHODS[method_name]["params"], params):
        raise ValueError("Invalid request parameters")


def error_payload(error):
    from .providers import ProviderError

    if isinstance(error, ProviderError):
        return {
            "code": error.kind,
            "message": str(error)[:2048],
            "retryable": error.kind in {"timeout", "offline", "rate_limit", "unavailable"},
        }
    if isinstance(error, InvalidConfig):
        # Parser messages may contain hand-edited values. Only disclose the file path.
        message = f"Invalid settings file: {error.path}".encode("utf-8", "replace")[:2048].decode(
            "utf-8", "ignore"
        )
        return {"code": "invalid_config", "message": message, "retryable": False}
    if isinstance(error, ValueError):
        return {"code": "invalid_request", "message": str(error)[:2048], "retryable": False}
    if isinstance(error, PermissionError):
        return {
            "code": "permission",
            "message": "Permission denied; check local desktop access",
            "retryable": False,
        }
    if isinstance(error, TimeoutError):
        return {
            "code": "timeout",
            "message": "Operation timed out; check status before retrying",
            "retryable": False,
        }
    if isinstance(error, RuntimeError):
        return {"code": "operation_blocked", "message": str(error)[:2048], "retryable": False}
    return {
        "code": "internal",
        "message": "Operation failed; check local permissions and desktop access",
        "retryable": False,
    }
