from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from caelum.linux import Bindings, insert, shortcut_keys


async def test_focus_change_copies_without_paste(monkeypatch):
    command = AsyncMock(return_value="ok")
    monkeypatch.setattr("caelum.linux.command", command)
    monkeypatch.setattr(
        "caelum.linux.hypr_json", AsyncMock(return_value={"address": "0xdef", "pid": 2})
    )
    target = SimpleNamespace(address="0xabc", pid=1, terminal=False)
    assert await insert("words", target) is False
    assert command.await_count == 1
    assert command.call_args.args[0] == "wl-copy"


async def test_paste_is_addressed_and_terminal_aware(monkeypatch):
    command = AsyncMock(return_value="ok")
    monkeypatch.setattr("caelum.linux.command", command)
    monkeypatch.setattr(
        "caelum.linux.hypr_json", AsyncMock(return_value={"address": "0xabc", "pid": 1})
    )
    assert await insert("words", SimpleNamespace(address="0xabc", pid=1, terminal=True))
    assert command.call_args.args == (
        "hyprctl",
        "dispatch",
        'hl.dsp.send_key_state({mods="SHIFT",key="Insert",state="up",window="address:0xabc"})',
    )


async def test_pid_change_rejects_reused_window_address(monkeypatch):
    command = AsyncMock(return_value="ok")
    monkeypatch.setattr("caelum.linux.command", command)
    monkeypatch.setattr(
        "caelum.linux.hypr_json", AsyncMock(return_value={"address": "0xabc", "pid": 2})
    )
    assert not await insert("words", SimpleNamespace(address="0xabc", pid=1, terminal=False))
    assert command.await_count == 1


def test_modifier_only_shortcut_covers_both_orders_and_sides():
    starts, modifier_only = shortcut_keys("CTRL + SUPER")
    assert modifier_only
    assert set(starts) == {
        ("SUPER + Control_L", "Control_L", 64),
        ("SUPER + Control_R", "Control_R", 64),
        ("CTRL + Super_L", "Super_L", 4),
        ("CTRL + Super_R", "Super_R", 4),
    }
    assert shortcut_keys("SUPER + ALT + V") == ([("SUPER + ALT + V", "V", 72)], False)


async def test_modifier_only_registration_releases_either_key_without_shadowing(monkeypatch):
    monkeypatch.setattr(
        "caelum.linux.hypr_json", AsyncMock(side_effect=[{"configProvider": "lua"}, []])
    )
    command = AsyncMock(return_value="ok")
    monkeypatch.setattr("caelum.linux.command", command)
    bindings = Bindings("CTRL + SUPER")
    await bindings.install()
    code = command.call_args.args[-1]
    assert code.count('description="Caelum hold to dictate"') == 4
    assert code.count("release=true,ignore_mods=true,non_consuming=true,transparent=true") == 4
    assert 'hl.bind("Control_L", stop' in code
    assert 'hl.bind("Super_R", stop' in code
    assert bindings.installed
    await bindings.remove()


async def test_modifier_shortcut_collision_leaves_other_bindings_untouched(monkeypatch):
    monkeypatch.setattr(
        "caelum.linux.hypr_json",
        AsyncMock(side_effect=[{"configProvider": "lua"}, [{"key": "Super_L", "modmask": 4}]]),
    )
    command = AsyncMock()
    monkeypatch.setattr("caelum.linux.command", command)
    with pytest.raises(RuntimeError, match="collision"):
        await Bindings("CTRL + SUPER").install()
    command.assert_not_awaited()
