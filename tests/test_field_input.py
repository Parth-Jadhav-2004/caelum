from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from caelum import field_input as fi
from dbus_next import Variant


@pytest.mark.parametrize("changed", ["none", "bus", "focus", "window", "readonly", "password", "selection"])
async def test_addresses_original_editable_field_or_preserves_result(monkeypatch, changed):
    field = fi.Field("bus-1", ":1.5", "/field", "/window")
    edits = []

    @asynccontextmanager
    async def connection():
        yield object()

    async def call(_, owner, path, interface, member, signature="", body=None):
        if member == "GetId":
            return ["other" if changed == "bus" else field.bus_id]
        assert owner == field.owner
        if member == "GetRole":
            return [fi.PASSWORD_TEXT if changed == "password" else 61]
        if member == "GetNSelections":
            return [int(changed == "selection")]
        if member == "Get":
            return [Variant("i", 3)]
        if member == "SetCaretOffset":
            assert edits and body == [3 + len(text)]
            return [True]
        if member == "GetState":
            if path == field.window:
                return [[0 if changed == "window" else 1 << fi.ACTIVE, 0]]
            return [[(1 << fi.EDITABLE_STATE) | (0 if changed == "focus" else 1 << fi.FOCUSED),
                     1 << (fi.READ_ONLY - 32) if changed == "readonly" else 0]]
        assert path == field.path and member == "InsertText" and interface == fi.EDITABLE
        edits.append(body)
        return [True]

    monkeypatch.setattr(fi, "connection", connection)
    monkeypatch.setattr(fi, "call", call)
    text = "Café 🛒\n2. Rice"
    assert await fi.insert_field(text, field) is (changed == "none")
    assert edits == ([[3, text, len(text.encode())]] if changed == "none" else [])


async def test_hyprland_changed_target_skips_both_insertion_and_clipboard(monkeypatch):
    from caelum.linux import Target, insert

    target = Target("0xabc", 12, 0, "", field=fi.Field("bus-1", ":1.5", "/field", "/window"))
    monkeypatch.setattr("caelum.linux.hypr_json", AsyncMock(return_value={"address": "0xabc", "pid": 13}))
    direct, clipboard = AsyncMock(), AsyncMock()
    monkeypatch.setattr(fi, "insert_field", direct)
    monkeypatch.setattr("caelum.linux.command", clipboard)
    assert not await insert("Only here", target, auto_copy=False)
    direct.assert_not_awaited()
    clipboard.assert_not_awaited()
