"""Windows desktop adapter. The control endpoint never leaves the sidecar process."""

import asyncio
import ctypes
import time
from contextlib import suppress
from ctypes import wintypes
from types import SimpleNamespace

import pywintypes
import win32api
import win32clipboard
import win32con
import win32gui
import win32process

from .desktop_services import SettingsBusy
from .hud import ERRORS, LABELS, presentation

endpoint = None
registered = None


class RecordingMedia:
    """Resume only sessions we paused, and only while the same track is paused."""

    def __init__(self):
        self.paused = []

    async def pause(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )

        with suppress(OSError, RuntimeError, TimeoutError):
            async with asyncio.timeout(0.8):
                manager = await Manager.request_async()
                for session in manager.get_sessions():
                    if session.get_playback_info().playback_status != Status.PLAYING:
                        continue
                    media = await session.try_get_media_properties_async()
                    if await session.try_pause_async():
                        self.paused.append((session, media.title, media.artist))

    async def resume(self):
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )

        paused, self.paused = self.paused, []
        for session, title, artist in paused:
            with suppress(OSError, RuntimeError, TimeoutError):
                async with asyncio.timeout(0.4):
                    if session.get_playback_info().playback_status == Status.PAUSED:
                        media = await session.try_get_media_properties_async()
                        if (media.title, media.artist) == (title, artist):
                            await session.try_play_async()


def request(action, **params):
    current = endpoint
    if not current:
        raise FileNotFoundError("Dictation is stopped")
    loop, dispatch = current
    future = asyncio.run_coroutine_threadsafe(dispatch({"action": action, **params}), loop)
    result = future.result(timeout=310 if params.get("config") else 10)
    if "error" in result:
        if result.get("error_code") == "settings_busy":
            raise SettingsBusy(result["error"])
        raise RuntimeError(result["error"])
    return result


def shortcut(value):
    names = {"SUPER": (0x5B, 0x5C), "CTRL": (0x11,), "SHIFT": (0x10,), "ALT": (0x12,),
             "SPACE": (0x20,), **{f"F{i}": (0x6F + i,) for i in range(1, 25)}}
    keys = []
    for key in map(str.strip, value.split("+")):
        if key in names:
            keys.append(names[key])
        elif len(key) == 1 and key.isascii() and key.isalnum():
            keys.append((ord(key),))
        else:
            raise ValueError(f"Unsupported Windows shortcut key: {key}")
    return keys


def reserve(value, hwnd, identifier):
    keys = shortcut(value)
    parts = list(map(str.strip, value.split("+")))
    modifiers = {"ALT": 1, "CTRL": 2, "SHIFT": 4, "SUPER": 8}
    if parts[-1] in modifiers:
        return False  # Modifier-only shortcuts need physical press/release detection.
    mask = sum(modifiers[m] for m in parts[:-1]) | 0x4000  # MOD_NOREPEAT
    if not ctypes.windll.user32.RegisterHotKey(wintypes.HWND(hwnd), identifier, mask, keys[-1][0]):
        raise ValueError("This Windows shortcut is in use. Choose another shortcut.")
    return True


def check_shortcut(value):
    if value != registered and reserve(value, None, 2):
        ctypes.windll.user32.UnregisterHotKey(None, 2)
    return "Windows shortcut is available."


class GuiThreadInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("flags", wintypes.DWORD),
                *((name, wintypes.HWND) for name in ("active", "focus", "capture",
                                                     "menu", "move", "caret")),
                ("rect", wintypes.RECT)]


def focused_target():
    top = win32gui.GetForegroundWindow()
    info = GuiThreadInfo()
    info.size = ctypes.sizeof(info)
    try:
        thread, pid = win32process.GetWindowThreadProcessId(top) if top else (0, 0)
    except pywintypes.error:  # The foreground window closed during capture.
        thread, pid = 0, 0
    child = info.focus if thread and ctypes.windll.user32.GetGUIThreadInfo(
        thread, ctypes.byref(info)
    ) else None
    return SimpleNamespace(top=top, address=child, pid=pid, output="")


def selection_start(window):
    # The packed EM_GETSEL return value overflows at 65,535. Request the full offset.
    offset = wintypes.DWORD()
    win32gui.SendMessageTimeout(window, win32con.EM_GETSEL, ctypes.addressof(offset), 0,
                                win32con.SMTO_ABORTIFHUNG, 300)
    return offset.value


def replace_selection(text, target):
    window = target.address
    if not window or target != focused_target():
        return False
    name = win32gui.GetClassName(window).lower()
    if name != "edit" and not name.startswith("richedit"):
        return False
    style = win32gui.GetWindowLong(window, win32con.GWL_STYLE)
    if style & win32con.ES_READONLY or not win32gui.IsWindowEnabled(window):
        return False
    if not text.isascii() and not ctypes.windll.user32.IsWindowUnicode(wintypes.HWND(window)):
        return False
    start = selection_start(window)
    lines = text.replace("\r\n", "\n")
    native_text = lines.replace("\n", "\r\n")
    if target != focused_target():
        return False
    # EM_REPLACESEL is a system-marshalled Unicode message addressed to one edit control.
    win32gui.SendMessageTimeout(window, win32con.EM_REPLACESEL, True, native_text,
                                win32con.SMTO_ABORTIFHUNG, 300)
    # A restricted field can silently truncate a successful dispatch. Modern RichEdit
    # counts a paragraph break as one UTF-16 code unit, classic Edit and RichEdit 1.0 as two.
    positions = native_text if name in ("edit", "richedit") else lines
    expected = start + len(positions.encode("utf-16-le")) // 2
    try:
        if selection_start(window) == expected:
            return True
    except pywintypes.error:
        pass
    raise RuntimeError("The field did not confirm full insertion")


class Bindings:
    mode = "native"

    def __init__(self, hotkey, recording_mode):
        self.hotkey, self.recording_mode = hotkey, recording_mode
        self.keys = []

    @property
    def description(self):
        return self.hotkey

    async def install(self):
        global registered
        self.keys = shortcut(self.hotkey)
        self.reserved = reserve(self.hotkey, self.core.hud.window, 1)
        self.core.hud.presses = 0
        registered = self.hotkey

    async def remove(self):
        global registered
        if getattr(self, "reserved", False):
            ctypes.windll.user32.UnregisterHotKey(wintypes.HWND(self.core.hud.window), 1)
        self.reserved = False
        registered = None
        self.keys = []

    async def active(self, enabled):
        pass

    async def locked(self):
        # Read the input desktop name; never activate or switch desktops.
        user = ctypes.windll.user32
        user.OpenInputDesktop.restype = wintypes.HANDLE
        desktop = user.OpenInputDesktop(0, False, 1)
        if not desktop:
            return True
        try:
            name = ctypes.create_unicode_buffer(256)
            needed = wintypes.DWORD()
            return not user.GetUserObjectInformationW(
                wintypes.HANDLE(desktop), 2, name, ctypes.sizeof(name), ctypes.byref(needed)
            ) or name.value.casefold() != "default"
        finally:
            user.CloseDesktop(wintypes.HANDLE(desktop))

    async def monitor(self):
        down = escape = False
        last = time.monotonic()
        while True:
            win32gui.PumpWaitingMessages()
            fired = self.core.hud.presses
            self.core.hud.presses = 0
            now = time.monotonic()
            if now - last > 2 and (self.core.capture or self.core.pcm is not None):
                await self.core.handle("cancel")
            last = now
            pressed = bool(self.keys) and all(any(win32api.GetAsyncKeyState(key) & 0x8000
                                                  for key in group) for group in self.keys)
            cancel = bool(win32api.GetAsyncKeyState(win32con.VK_ESCAPE) & 0x8000)
            if cancel and not escape and (self.core.capture or self.core.pcm is not None
                                           or self.core.work and not self.core.work.done()):
                await self.core.handle("cancel")
            elif fired or (not self.reserved and pressed and not down):
                await self.core.handle("toggle" if self.recording_mode == "toggle" else "start")
                if not pressed and self.recording_mode == "hold":
                    await self.core.handle("stop")
            elif down and not pressed and self.recording_mode == "hold":
                await self.core.handle("stop")
            down, escape = pressed, cancel
            last = time.monotonic()
            await asyncio.sleep(0.025)

    async def target(self, address=None):
        self.clipboard_sequence = win32clipboard.GetClipboardSequenceNumber()
        return focused_target()

    async def insert(self, text, target):
        try:
            if replace_selection(text, target):
                return True
        except pywintypes.error:
            pass  # The control closed, denied access or timed out.
        await self.copy_result(text, self.clipboard_sequence)
        return False

    async def copy_result(self, text, expected_sequence=None):
        # Explicit Retry authorizes copying over the clipboard as it is now.
        if expected_sequence is None:
            expected_sequence = win32clipboard.GetClipboardSequenceNumber()
        for attempt in range(6):
            try:
                win32clipboard.OpenClipboard(self.core.hud.window)
                break
            except pywintypes.error:
                if attempt == 5:
                    raise RuntimeError("Clipboard is busy") from None
                await asyncio.sleep(0.025)
        try:
            # Check while holding the clipboard, including after any busy retries.
            try:
                current = win32clipboard.GetClipboardSequenceNumber()
                # A new window station also reports zero for its untouched, empty clipboard.
                if current != expected_sequence or (not current and win32clipboard.EnumClipboardFormats(0)):
                    raise RuntimeError("Clipboard changed or unavailable")
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        except pywintypes.error:
            raise RuntimeError("Clipboard unavailable") from None


class HUD:
    process = None

    def __init__(self, config):
        self.config = config
        self.message = {"state": "hidden"}
        self.timer = None
        self.presses = 0

    def hotkey(self, *_):
        self.presses += 1
        return 0

    def paint(self, hwnd, *_):
        dc, ps = win32gui.BeginPaint(hwnd)
        brush = win32gui.CreateSolidBrush(win32api.RGB(24, 24, 27))
        try:
            rect = win32gui.GetClientRect(hwnd)
            win32gui.FillRect(dc, rect, brush)
            state = self.message["state"]
            win32gui.SetBkMode(dc, win32con.TRANSPARENT)
            win32gui.SetTextColor(dc, 0xFFFFFF if self.config.high_contrast else 0xEFEDED)
            if state in ("recording", "listening"):
                label = "×                       ✓"
                for i, level in enumerate(self.message["history"][2:15]):
                    half = 2 if self.config.reduced_motion else 2 + int(10 * level)
                    x = 40 + 5 * i
                    win32gui.FillRect(dc, (x, 18-half, x+2, 18+half),
                                      win32gui.GetStockObject(win32con.WHITE_BRUSH))
            else:
                label = ERRORS.get(self.message.get("error_code"), LABELS.get(state, state))
            win32gui.DrawText(dc, label, -1, rect,
                              win32con.DT_CENTER | win32con.DT_VCENTER | win32con.DT_SINGLELINE)
        finally:
            win32gui.DeleteObject(brush)
            win32gui.EndPaint(hwnd, ps)
        return 0

    def click(self, hwnd, msg, wp, lp):
        actions = presentation(self.message["state"])["actions"]
        if actions and endpoint:
            right = (lp & 0xFFFF) >= win32gui.GetClientRect(hwnd)[2] // 2
            asyncio.create_task(endpoint[1]({"action": actions[int(right)]}))
        return 0

    async def start(self):
        style = win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOPMOST
        cls = win32gui.WNDCLASS()
        cls.lpszClassName = "CaelumRecordingPill"
        cls.hInstance = win32api.GetModuleHandle(None)
        cls.lpfnWndProc = {win32con.WM_HOTKEY: self.hotkey, win32con.WM_PAINT: self.paint, win32con.WM_LBUTTONUP: self.click,
                           win32con.WM_MOUSEACTIVATE: lambda *_: win32con.MA_NOACTIVATE}
        self.atom = win32gui.RegisterClass(cls)
        self.window = win32gui.CreateWindowEx(style, self.atom, "Caelum", win32con.WS_POPUP,
                                              0, 0, 184, 36, 0, 0, cls.hInstance, None)
        self.width = 0

    async def emit(self, message):
        if self.timer:
            self.timer.cancel()
        state = message["state"]
        self.message = message
        if state == "hidden":
            win32gui.ShowWindow(self.window, win32con.SW_HIDE)
            return
        layout = presentation(state)
        width = layout["width"]
        if width != self.width:
            ctypes.windll.gdi32.CreateRoundRectRgn.restype = wintypes.HANDLE
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width+1, 37, 36, 36)
            ctypes.windll.user32.SetWindowRgn(wintypes.HWND(self.window), wintypes.HANDLE(region), True)
            self.width = width
        monitor = win32api.MonitorFromWindow(win32gui.GetForegroundWindow(), win32con.MONITOR_DEFAULTTONEAREST)
        left, _, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
        win32gui.SetWindowPos(self.window, win32con.HWND_TOPMOST, (left + right - width) // 2,
                              bottom - 60, width, 36, win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)
        win32gui.InvalidateRect(self.window, None, False)
        if layout["dwell"] is not None:
            self.timer = asyncio.get_running_loop().call_later(
                layout["dwell"], win32gui.ShowWindow, self.window, win32con.SW_HIDE)

    async def close(self):
        if getattr(self, "timer", None):
            self.timer.cancel()
        if getattr(self, "window", None):
            win32gui.DestroyWindow(self.window)
        if getattr(self, "atom", None):
            win32gui.UnregisterClass(self.atom, win32api.GetModuleHandle(None))
