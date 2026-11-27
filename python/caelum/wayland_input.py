"""Clipboard-free Wayland text insertion via zwp_virtual_keyboard_manager_v1."""

import array
import asyncio
import os
import socket
import struct
import time
from contextlib import suppress

# Pure printable Linux evdev keycodes (never Esc, Tab, Enter, modifiers, Fn, or media/browser keys).
# Chromium/Electron intercept raw hardware scancodes for special/media keys before XKB lookup.
PRINTABLE_EVDEV = (
    tuple(range(2, 14))     # KEY_1 .. KEY_EQUAL (12)
    + tuple(range(16, 28))  # KEY_Q .. KEY_RIGHTBRACE (12)
    + tuple(range(30, 42))  # KEY_A .. KEY_GRAVE (12)
    + tuple(range(43, 54))  # KEY_BACKSLASH .. KEY_SLASH (11)
    + (57,)                 # KEY_SPACE (1)
)
XKB_KEYMAP_FORMAT_V1 = 1
KEY_RELEASED = 0
KEY_PRESSED = 1
VIRTUAL_KEYBOARD_MANAGER = "zwp_virtual_keyboard_manager_v1"
UNAVAILABLE = (OSError, EOFError, RuntimeError, TimeoutError, ValueError)


def wayland_socket_path():
    display = os.environ.get("WAYLAND_DISPLAY")
    if not display:
        return None
    if os.path.isabs(display):
        return display
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return None
    return os.path.join(runtime, display)


def can_type_text(text):
    # A window without an accessible field can be a terminal. Never synthesize Return.
    return bool(text) and all(
        ord(ch) >= 0x20 and not 0x7F <= ord(ch) <= 0x9F
        and not 0xD800 <= ord(ch) <= 0xDFFF and ch not in ("\u2028", "\u2029")
        for ch in text
    )


def build_batches(text):
    batches = []
    batch_text = []
    batch_chars = []
    seen = set()
    limit = len(PRINTABLE_EVDEV)
    for ch in text:
        if ch not in seen and len(batch_chars) >= limit:
            batches.append(("".join(batch_text), batch_chars))
            batch_text, batch_chars, seen = [], [], set()
        if ch not in seen:
            seen.add(ch)
            batch_chars.append(ch)
        batch_text.append(ch)
    if batch_text:
        batches.append(("".join(batch_text), batch_chars))
    return batches


def build_keymap(chars):
    keycodes = []
    symbols = []
    mapping = {}
    for index, ch in enumerate(chars):
        evdev = PRINTABLE_EVDEV[index]
        xkb = evdev + 8
        mapping[ch] = evdev
        keycodes.append(f"<K{index}> = {xkb};")
        symbols.append(f"key <K{index}> {{ [ U{ord(ch):04X} ] }};")
    keymap = (
        'xkb_keymap {\n'
        'xkb_keycodes "(unnamed)" {\n'
        'minimum = 8;\n'
        f'maximum = {max(PRINTABLE_EVDEV) + 8};\n'
        + "\n".join(keycodes)
        + '\n};\n'
        'xkb_types "(unnamed)" { include "complete" };\n'
        'xkb_compatibility "(unnamed)" { include "complete" };\n'
        'xkb_symbols "(unnamed)" {\n'
        + "\n".join(symbols)
        + '\n};\n'
        '};\n\x00'
    ).encode("utf-8")
    return keymap, mapping


def _pad4(data):
    rem = len(data) & 3
    return data if rem == 0 else data + b"\x00" * (4 - rem)


def _wl_string(value):
    raw = value.encode("utf-8") + b"\x00"
    return struct.pack("<I", len(raw)) + _pad4(raw)


class _WaylandVirtualKeyboardClient:
    def __init__(self, path, *, settle_seconds=0.015, drain_seconds=0.02):
        self.path = path
        self.settle_seconds = settle_seconds
        self.drain_seconds = drain_seconds
        self.sock = None
        self.buf = b""
        self.globals = {}
        self.next_id = 3
        self.seat_id = 0
        self.vkm_id = 0
        self.started = time.monotonic()

    def _alloc(self):
        obj_id = self.next_id
        self.next_id += 1
        return obj_id

    def _send(self, obj_id, opcode, payload=b"", fds=()):
        packet = struct.pack("<IHH", obj_id, opcode, 8 + len(payload)) + payload
        if fds:
            self.sock.sendmsg([packet], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))])
        else:
            self.sock.sendall(packet)

    def _roundtrip(self):
        callback_id = self._alloc()
        self._send(1, 0, struct.pack("<I", callback_id))  # wl_display.sync
        while True:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("Wayland compositor closed connection")
            self.buf += chunk
            while len(self.buf) >= 8:
                obj_id, opcode, size = struct.unpack_from("<IHH", self.buf, 0)
                if size < 8:
                    raise RuntimeError("Invalid Wayland frame")
                if len(self.buf) < size:
                    break
                payload = self.buf[8:size]
                self.buf = self.buf[size:]
                if obj_id == 1 and opcode == 0:  # wl_display.error
                    raise RuntimeError("Wayland protocol error")
                if obj_id == 2 and opcode == 0:  # wl_registry.global
                    name, str_len = struct.unpack_from("<II", payload, 0)
                    iface = payload[8:8 + max(str_len - 1, 0)].decode("utf-8", "replace")
                    padded = (str_len + 3) & ~3
                    version, = struct.unpack_from("<I", payload, 8 + padded)
                    self.globals[iface] = (name, version)
                elif obj_id == callback_id and opcode == 0:  # wl_callback.done
                    return

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(self.path)
        self.sock = sock
        self._send(1, 1, struct.pack("<I", 2))  # wl_display.get_registry(2)
        self._roundtrip()
        if "wl_seat" not in self.globals or VIRTUAL_KEYBOARD_MANAGER not in self.globals:
            return False
        seat_name, seat_version = self.globals["wl_seat"]
        vkm_name, _ = self.globals[VIRTUAL_KEYBOARD_MANAGER]
        self.seat_id = self._alloc()
        self._send(
            2, 0, struct.pack("<I", seat_name) + _wl_string("wl_seat") + struct.pack("<II", min(seat_version, 1), self.seat_id)
        )
        self.vkm_id = self._alloc()
        self._send(
            2, 0, struct.pack("<I", vkm_name) + _wl_string(VIRTUAL_KEYBOARD_MANAGER) + struct.pack("<II", 1, self.vkm_id)
        )
        self._roundtrip()
        return True

    def _timestamp(self):
        return int((time.monotonic() - self.started) * 1000) & 0xFFFFFFFF

    def start_keyboard(self, batch_chars):
        # A fresh virtual keyboard per batch makes compositors send its new keymap to clients.
        vk_id = self._alloc()
        self._send(self.vkm_id, 0, struct.pack("<II", self.seat_id, vk_id))
        keymap, mapping = build_keymap(batch_chars)
        fd = os.memfd_create("caelum-keymap", os.MFD_CLOEXEC)
        try:
            os.write(fd, keymap)
            os.lseek(fd, 0, os.SEEK_SET)
            self._send(vk_id, 0, struct.pack("<II", XKB_KEYMAP_FORMAT_V1, len(keymap)), fds=(fd,))
        finally:
            os.close(fd)
        self._send(vk_id, 2, struct.pack("<IIII", 0, 0, 0, 0))
        self._roundtrip()
        return vk_id, mapping

    def type_key(self, vk_id, code):
        self._send(vk_id, 1, struct.pack("<III", self._timestamp(), code, KEY_PRESSED))
        self._send(vk_id, 1, struct.pack("<III", self._timestamp(), code, KEY_RELEASED))
        self._roundtrip()

    def destroy_keyboard(self, vk_id):
        self._send(vk_id, 3)
        self._roundtrip()

    def close(self):
        if self.sock is not None:
            with suppress(OSError):
                self.sock.close()
            self.sock = None


async def type_text(text, *, verify_focus=None):
    if not can_type_text(text):
        return False
    path = wayland_socket_path()
    if not path:
        return False
    batches = build_batches(text)
    timeout = min(max(3.0, len(text) * 0.02 + 2.0), 30.0)
    client = _WaylandVirtualKeyboardClient(path)
    try:
        async with asyncio.timeout(timeout):
            if not await asyncio.to_thread(client.connect):
                return False
            for batch_text, batch_chars in batches:
                vk_id, mapping = await asyncio.to_thread(client.start_keyboard, batch_chars)
                await asyncio.sleep(client.settle_seconds)
                for ch in batch_text:
                    if verify_focus is not None and not await verify_focus():
                        await asyncio.to_thread(client.destroy_keyboard, vk_id)
                        return False
                    await asyncio.to_thread(client.type_key, vk_id, mapping[ch])
                await asyncio.sleep(client.drain_seconds)
                await asyncio.to_thread(client.destroy_keyboard, vk_id)
            return True
    except UNAVAILABLE:
        return False
    finally:
        client.close()
