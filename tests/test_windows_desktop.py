import ctypes
import multiprocessing
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

if sys.platform == "win32":
    from caelum import windows_desktop as desktop
else:
    pytest.skip("Windows desktop adapter", allow_module_level=True)

win32con = desktop.win32con
win32gui = desktop.win32gui
TEXT = "Dictation \u0928\U0001f680"


@pytest.fixture
def clipboard(monkeypatch):
    # Even a failing regression test must leave the developer's clipboard alone.
    clipboard = Mock(spec=desktop.win32clipboard)
    clipboard.GetClipboardSequenceNumber.return_value = 17
    monkeypatch.setattr(desktop, "win32clipboard", clipboard)
    return clipboard


@pytest.fixture
def bindings():
    result = desktop.Bindings("CTRL+SUPER", "hold")
    result.core = SimpleNamespace(hud=SimpleNamespace(window=123))
    return result


@pytest.fixture
def control(request, monkeypatch):
    library = ctypes.WinDLL("Msftedit.dll", winmode=0x800)  # System32
    window = win32gui.CreateWindow(getattr(request, "param", "Edit"), "before AFTER",
                                   win32con.ES_MULTILINE, 0, 0, 240, 80, 0, 0, 0, None)
    monkeypatch.setattr(desktop, "focused_target",
                        lambda: SimpleNamespace(top=window, address=window, pid=1, output=""))
    try:
        yield window
    finally:
        win32gui.DestroyWindow(window)
        del library


@pytest.mark.parametrize("control", ["Edit", "RICHEDIT50W"], indirect=True)
@pytest.mark.parametrize("auto_copy", [True, False])
async def test_direct_insert_replaces_selection_without_opening_clipboard(bindings, clipboard, control, auto_copy):
    target = await bindings.target()
    clipboard.GetClipboardSequenceNumber.return_value += 1  # Another app copied while dictating.
    win32gui.SendMessage(control, win32con.EM_SETSEL, 7, -1)
    assert await bindings.insert(TEXT + "\nNext line", target, auto_copy=auto_copy)
    assert win32gui.GetWindowText(control) == "before " + TEXT + "\r\nNext line"
    assert win32gui.SendMessage(control, win32con.EM_GETLINECOUNT, 0, 0) == 2
    assert clipboard.mock_calls == [call.GetClipboardSequenceNumber()]
    assert win32gui.SendMessage(control, win32con.EM_CANUNDO, 0, 0)


async def test_truncated_dispatch_preserves_clipboard_for_explicit_retry(bindings, clipboard, control):
    target = await bindings.target()
    win32gui.SendMessage(control, win32con.EM_SETLIMITTEXT, 3, 0)
    win32gui.SendMessage(control, win32con.EM_SETSEL, 0, -1)
    with pytest.raises(RuntimeError, match="full insertion"):
        await bindings.insert(TEXT, target)
    assert win32gui.GetWindowText(control) == TEXT[:3]
    assert clipboard.mock_calls == [call.GetClipboardSequenceNumber()]


@pytest.mark.parametrize("failure", [
    "focus", "late-focus", "unsupported", "readonly", "ansi", "denied", "no-target",
])
@pytest.mark.parametrize("auto_copy", [True, False])
async def test_failed_dispatch_respects_clipboard_preference(bindings, clipboard, control, monkeypatch, failure, auto_copy):
    target = await bindings.target()
    real_send = win32gui.SendMessageTimeout
    denied = Mock(side_effect=desktop.pywintypes.error(5, "SendMessageTimeout", "denied"))

    def send(window, message, *args):
        if message == win32con.EM_REPLACESEL:
            return denied(window, message, *args)
        return real_send(window, message, *args)

    monkeypatch.setattr(win32gui, "SendMessageTimeout", send)
    if failure in ("focus", "late-focus"):
        other = SimpleNamespace(address=control + 1)
        focus = [target, other] if failure == "late-focus" else [other]
        monkeypatch.setattr(desktop, "focused_target", Mock(side_effect=focus))
    elif failure == "unsupported":
        monkeypatch.setattr(win32gui, "GetClassName", lambda _: "Chrome_WidgetWin_1")
    elif failure == "readonly":
        win32gui.SendMessage(control, win32con.EM_SETREADONLY, 1, 0)
    elif failure == "ansi":
        monkeypatch.setattr(ctypes.windll.user32, "IsWindowUnicode", lambda _: 0)
    elif failure == "no-target":
        target.address = None
    assert not await bindings.insert(TEXT, target, auto_copy=auto_copy)
    assert denied.call_count == int(failure == "denied")
    if not auto_copy:
        assert clipboard.mock_calls == [call.GetClipboardSequenceNumber()]
        return
    assert clipboard.mock_calls == [
        call.GetClipboardSequenceNumber(), call.OpenClipboard(123),
        call.GetClipboardSequenceNumber(), call.EmptyClipboard(),
        call.SetClipboardText(TEXT, win32con.CF_UNICODETEXT), call.CloseClipboard(),
    ]


@pytest.mark.parametrize("initial,current", [(17, 18), (0, 0)])
async def test_fallback_rechecks_sequence_under_lock(bindings, clipboard, monkeypatch, initial, current):
    monkeypatch.setattr(desktop, "focused_target", lambda: SimpleNamespace(address=None))
    clipboard.GetClipboardSequenceNumber.side_effect = [initial, current]
    clipboard.EnumClipboardFormats.return_value = win32con.CF_UNICODETEXT
    target = await bindings.target()
    clipboard.OpenClipboard.side_effect = [desktop.pywintypes.error(), None]
    with pytest.raises(RuntimeError, match="changed or unavailable"):
        await bindings.insert(TEXT, target)
    assert clipboard.mock_calls == [
        call.GetClipboardSequenceNumber(), call.OpenClipboard(123), call.OpenClipboard(123),
        call.GetClipboardSequenceNumber(), *([call.EnumClipboardFormats(0)] if not current else []),
        call.CloseClipboard(),
    ]


async def test_explicit_copy_guards_changes_while_waiting(bindings, clipboard):
    clipboard.GetClipboardSequenceNumber.side_effect = [21, 22, 22, 22]
    with pytest.raises(RuntimeError):
        await bindings.copy_result(TEXT)
    clipboard.EmptyClipboard.assert_not_called()
    await bindings.copy_result(TEXT)
    clipboard.SetClipboardText.assert_called_once_with(TEXT, win32con.CF_UNICODETEXT)


async def test_clipboard_errors_allow_retry(bindings, clipboard):
    clipboard.OpenClipboard.side_effect = desktop.pywintypes.error()
    with pytest.raises(RuntimeError, match="busy"):
        await bindings.copy_result(TEXT, 17)
    clipboard.EmptyClipboard.assert_not_called()
    clipboard.OpenClipboard.side_effect = None
    clipboard.SetClipboardText.side_effect = desktop.pywintypes.error()
    with pytest.raises(RuntimeError, match="unavailable"):
        await bindings.copy_result(TEXT, 17)
    clipboard.CloseClipboard.assert_called_once_with()


def check_private_clipboard():
    import asyncio

    import win32service

    # A separate process and window station give this test its own real clipboard.
    station = win32service.CreateWindowStation(uuid.uuid4().hex, 1, win32con.MAXIMUM_ALLOWED, None)
    station.SetProcessWindowStation()
    private = win32service.CreateDesktop("Test", 0, win32con.MAXIMUM_ALLOWED, None)
    private.SetThreadDesktop()
    clip = desktop.win32clipboard
    window = win32gui.CreateWindow("Edit", "", win32con.ES_AUTOHSCROLL, 0, 0, 240, 40, 0, 0, 0, None)
    target = SimpleNamespace(top=window, address=window, pid=1, output="")
    bindings = desktop.Bindings("CTRL+SUPER", "hold")
    bindings.core = SimpleNamespace(hud=SimpleNamespace(window=window))
    rich = clip.RegisterClipboardFormat("HTML Format")
    try:
        with patch.object(desktop, "focused_target", return_value=target):
            for multiple_formats in [False, True]:
                at_press = asyncio.run(bindings.target())
                if multiple_formats:  # Simulate a rich copy made during dictation.
                    clip.OpenClipboard(window)
                    try:
                        clip.EmptyClipboard()
                        clip.SetClipboardText("example", win32con.CF_UNICODETEXT)
                        clip.SetClipboardData(rich, b"<b>example</b>\0")
                    finally:
                        clip.CloseClipboard()
                sequence = clip.GetClipboardSequenceNumber()
                assert asyncio.run(bindings.insert(TEXT, at_press))
                assert clip.GetClipboardSequenceNumber() == sequence
                clip.OpenClipboard(window)
                try:
                    if multiple_formats:
                        assert clip.GetClipboardData(win32con.CF_UNICODETEXT) == "example"
                        assert clip.GetClipboardData(rich).startswith(b"<b>example</b>\0")
                    else:
                        assert clip.EnumClipboardFormats(0) == 0
                finally:
                    clip.CloseClipboard()
                if not multiple_formats:
                    # The first manual paste on a fresh window station starts at sequence zero.
                    assert not asyncio.run(bindings.insert(TEXT, SimpleNamespace(address=None)))
                    clip.OpenClipboard(window)
                    try:
                        assert clip.GetClipboardData(win32con.CF_UNICODETEXT) == TEXT
                    finally:
                        clip.CloseClipboard()
    finally:
        win32gui.DestroyWindow(window)


def test_preserves_empty_and_multiformat_windows_clipboard():
    worker = multiprocessing.get_context("spawn").Process(target=check_private_clipboard)
    worker.start()
    try:
        worker.join(15)
        assert worker.exitcode == 0
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join()
