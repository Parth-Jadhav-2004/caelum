"""Shared desktop contract, using a deliberately small JSON Schema vocabulary.

This is also generated into the frontend. No eval/code generation at runtime,
network schema loading, credential values, or provider response bodies.
"""

import math
from dataclasses import fields

from .config import STT, App, Cleanup, Desktop

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
                field.name: {str: STRING, int: NUMBER, float: NUMBER, bool: BOOL}.get(
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
        "storage_error": BOOL,
        "backend": STRING,
        "feedback": obj(
            {"state": STRING, "elapsed_ms": NUMBER, "history": array(NUMBER), "level": NUMBER},
            extra=True,
        ),
    },
    optional=("pending_audio", "storage_error", "backend", "feedback"),
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
            "credentials": STRINGS,
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
            "action": {"enum": ["start", "stop", "cancel", "retry", "pause", "resume"]},
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
method("practice", obj({"consent": BOOL}), obj({"text": STRING, "refined": BOOL}))
method("sample.cancel")
method(
    "setup.validate",
    obj({"consent": BOOL, "keys": STRINGS}, optional=("keys",)),
    obj({"storage": STRINGS}),
)
method("shortcut.check", result=STRING)
method("setup.finish")
method(
    "launcher", obj({"autostart": BOOL, "enabled": BOOL}, optional=("autostart", "enabled")), STRING
)
method("updates.check", result=union(obj({"version": STRING}), NULL))
method("updates.stage", result=STRING)
method("updates.apply", result=BOOL)
method("updates.discard")
method("updates.pending", result=BOOL)
method("shutdown", obj({"discard": BOOL}, optional=("discard",)))


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
