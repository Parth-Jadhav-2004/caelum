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
    direct, typed, clipboard = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(fi, "insert_field", direct)
    monkeypatch.setattr("caelum.wayland_input.type_text", typed)
    monkeypatch.setattr("caelum.linux.command", clipboard)
    assert not await insert("Only here", target, auto_copy=False)
    direct.assert_not_awaited()
    typed.assert_not_awaited()
    clipboard.assert_not_awaited()


async def test_hyprland_falls_back_to_wayland_typing_without_atspi_or_clipboard(monkeypatch):
    from caelum.linux import Target, insert

    target = Target("0xabc", 12, 0, "", terminal=False, field=None)
    monkeypatch.setattr("caelum.linux.hypr_json", AsyncMock(return_value={"address": "0xabc", "pid": 12}))
    typed = AsyncMock(return_value=True)
    clipboard = AsyncMock()
    monkeypatch.setattr("caelum.wayland_input.type_text", typed)
    monkeypatch.setattr("caelum.linux.command", clipboard)

    assert await insert("Direct into VS Code", target, auto_copy=False) is True
    typed.assert_awaited_once()
    assert typed.call_args.args == ("Direct into VS Code",)
    assert typed.call_args.kwargs["terminal"] is False
    assert await typed.call_args.kwargs["verify_focus"]() is True
    clipboard.assert_not_awaited()


async def test_hyprland_respects_atspi_refusal_password_and_self_window(monkeypatch):
    from caelum.linux import Target, insert

    monkeypatch.setattr("caelum.linux.hypr_json", AsyncMock(return_value={"address": "0xabc", "pid": 12}))
    typed = AsyncMock(return_value=True)
    monkeypatch.setattr("caelum.wayland_input.type_text", typed)

    # Known AT-SPI field refused (e.g. active selection or widget focus moved): do not bypass.
    monkeypatch.setattr(fi, "insert_field", AsyncMock(return_value=False))
    atspi_target = Target("0xabc", 12, 0, "", field=fi.Field("bus-1", ":1.5", "/field", "/window"))
    assert await insert("Skip fallback", atspi_target, auto_copy=False) is False

    # Detected AT-SPI password field: never type into it.
    password_target = Target("0xabc", 12, 0, "", blocked_field=True)
    assert await insert("secret", password_target, auto_copy=False) is False

    # Caelum's own Home window without an editable field: keep Copy transcript on Home.
    self_target = Target("0xabc", 12, 0, "", self_window=True)
    assert await insert("From Home", self_target, auto_copy=False) is False
    typed.assert_not_awaited()


async def test_probe_focused_field_detects_active_password_field(monkeypatch):
    @asynccontextmanager
    async def connection():
        yield object()

    async def call(_, owner, path, interface, member, signature="", body=None):
        if member == "GetId":
            return ["bus-1"]
        if member == "GetChildren":
            return [[(":1.9", "/org/a11y/atspi/accessible/root")]]
        if member == "GetConnectionUnixProcessID":
            return [42]
        if member == "GetItems":
            return [[
                [(":1.9", "/win"), (":1.9", "/app"), (":1.9", "/app"), 0, 0, [fi.ACCESSIBLE], "", 23, "", [1 << fi.ACTIVE, 0]],
                [(":1.9", "/pw"), (":1.9", "/app"), (":1.9", "/win"), 0, 0, [fi.ACCESSIBLE, fi.EDITABLE], "", fi.PASSWORD_TEXT, "", [(1 << fi.FOCUSED) | (1 << fi.EDITABLE_STATE), 0]],
            ]]
        raise AssertionError(f"unexpected call: {member}")

    monkeypatch.setattr(fi, "connection", connection)
    monkeypatch.setattr(fi, "call", call)
    assert await fi.probe_focused_field(42) == (None, True)
    assert await fi.focused_field(42) is None
