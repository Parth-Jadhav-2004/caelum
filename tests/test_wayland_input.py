import array
import ctypes
import ctypes.util
import os
import re
import socket
import struct
import threading

from caelum import wayland_input as wi


def _pad4(data):
    rem = len(data) & 3
    return data if rem == 0 else data + b"\x00" * (4 - rem)


def _wl_string(value):
    raw = value.encode("utf-8") + b"\x00"
    return struct.pack("<I", len(raw)) + _pad4(raw)


def _frame(obj_id, opcode, payload=b""):
    return struct.pack("<IHH", obj_id, opcode, 8 + len(payload)) + payload


class MockWaylandServer:
    """Minimal Wayland server implementing wl_display, wl_registry, and zwp_virtual_keyboard_v1."""

    def __init__(self, path, *, advertise_vk=True, error_on_key=False):
        self.path = path
        self.advertise_vk = advertise_vk
        self.error_on_key = error_on_key
        self.vk_objects = []
        self.keymaps = {}
        self.events = []
        self.destroyed = []
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(path))
        self._sock.listen(1)
        self._sock.settimeout(5.0)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def close(self):
        self._thread.join(timeout=3.0)
        self._sock.close()

    def _run(self):
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(3.0)
            buf = b""
            fds = []
            vkm_id = None
            registry_id = None
            while True:
                try:
                    data, ancdata, _, _ = conn.recvmsg(65536, socket.CMSG_SPACE(16))
                except OSError:
                    break
                if not data:
                    break
                for level, typ, raw in ancdata:
                    if level == socket.SOL_SOCKET and typ == socket.SCM_RIGHTS:
                        arr = array.array("i")
                        arr.frombytes(raw[: len(raw) - (len(raw) % arr.itemsize)])
                        fds.extend(arr)
                buf += data
                while len(buf) >= 8:
                    obj_id, opcode, size = struct.unpack_from("<IHH", buf, 0)
                    if len(buf) < size:
                        break
                    payload = buf[8:size]
                    buf = buf[size:]
                    if obj_id == 1 and opcode == 1:  # get_registry
                        registry_id, = struct.unpack_from("<I", payload, 0)
                        conn.sendall(
                            _frame(registry_id, 0, struct.pack("<I", 1) + _wl_string("wl_seat") + struct.pack("<I", 7))
                        )
                        if self.advertise_vk:
                            conn.sendall(
                                _frame(
                                    registry_id,
                                    0,
                                    struct.pack("<I", 2)
                                    + _wl_string(wi.VIRTUAL_KEYBOARD_MANAGER)
                                    + struct.pack("<I", 1),
                                )
                            )
                    elif obj_id == 1 and opcode == 0:  # sync
                        cb_id, = struct.unpack_from("<I", payload, 0)
                        conn.sendall(_frame(cb_id, 0, struct.pack("<I", 0)))
                    elif registry_id and obj_id == registry_id and opcode == 0:  # bind
                        _, str_len = struct.unpack_from("<II", payload, 0)
                        iface = payload[8:8 + str_len - 1].decode()
                        padded = (str_len + 3) & ~3
                        _, new_id = struct.unpack_from("<II", payload, 8 + padded)
                        if iface == wi.VIRTUAL_KEYBOARD_MANAGER:
                            vkm_id = new_id
                    elif vkm_id and obj_id == vkm_id and opcode == 0:  # create_virtual_keyboard
                        _, vk_id = struct.unpack_from("<II", payload, 0)
                        self.vk_objects.append(vk_id)
                    elif obj_id in self.vk_objects:
                        if opcode == 0:  # keymap
                            fmt, km_size = struct.unpack_from("<II", payload, 0)
                            assert fmt == wi.XKB_KEYMAP_FORMAT_V1
                            fd = fds.pop(0)
                            try:
                                os.lseek(fd, 0, os.SEEK_SET)
                                raw_km = os.read(fd, km_size)
                            finally:
                                os.close(fd)
                            self.keymaps[obj_id] = raw_km
                        elif opcode == 1:  # key
                            if self.error_on_key:
                                conn.sendall(
                                    _frame(1, 0, struct.pack("<II", obj_id, 1) + _wl_string("failed"))
                                )
                                return
                            _, keycode, state = struct.unpack_from("<III", payload, 0)
                            self.events.append(("key", obj_id, keycode, state))
                        elif opcode == 2:  # modifiers
                            mods = struct.unpack_from("<IIII", payload, 0)
                            self.events.append(("mods", obj_id, mods))
                        elif opcode == 3:  # destroy
                            self.destroyed.append(obj_id)
            for fd in fds:
                os.close(fd)


def _decode_typed_text(server):
    """Reconstruct the typed string from recorded keymaps, modifier states, and key presses."""
    result = []
    shift_by_vk = {}
    maps = {}
    for vk_id, raw_km in server.keymaps.items():
        text_km = raw_km.rstrip(b"\x00").decode("utf-8")
        name_to_evdev = {
            m.group(1): int(m.group(2)) - 8
            for m in re.finditer(r"<([A-Z0-9]+)>\s*=\s*(\d+);", text_km)
        }
        evdev_to_sym = {}
        for m in re.finditer(r"key\s+<([A-Z0-9]+)>\s*\{\s*\[\s*([^\s\]]+)\s*\]\s*\};", text_km):
            evdev_to_sym[name_to_evdev[m.group(1)]] = m.group(2)
        maps[vk_id] = evdev_to_sym
    for event in server.events:
        if event[0] == "mods":
            _, vk_id, mods = event
            shift_by_vk[vk_id] = bool(mods[0] & wi.SHIFT_MASK)
        elif event[0] == "key":
            _, vk_id, code, state = event
            if state != wi.KEY_PRESSED:
                continue
            sym = maps[vk_id][code]
            if sym == "Return":
                assert shift_by_vk.get(vk_id), "newlines must use Shift+Return to avoid submitting chats/forms"
                result.append("\n")
            else:
                assert sym.startswith("U")
                result.append(chr(int(sym[1:], 16)))
    return "".join(result)


def test_normalize_text_validates_control_chars_and_terminal_newlines():
    assert wi.normalize_text("") is None
    assert wi.normalize_text("first\tsecond") is None
    assert wi.normalize_text("a\x00b") is None
    assert wi.normalize_text("a\x07b") is None
    assert wi.normalize_text("a\x7fb") is None
    assert wi.normalize_text("a\x85b") is None
    assert wi.normalize_text("line1\r\nline2\rline3") == "line1\nline2\nline3"
    assert wi.normalize_text("single line in terminal", terminal=True) == "single line in terminal"
    assert wi.normalize_text("line1\nline2", terminal=True) is None


def test_build_batches_and_keymap_only_use_safe_printable_evdev_codes():
    # 60+ unique characters forces multiple batches, each <= 48 printable evdev scancodes.
    sample = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()Café—\n"
    batches = wi.build_batches(sample)
    assert len(batches) == 2
    assert "".join(text for text, _ in batches) == sample
    forbidden_evdev = {1, 15, 29, 54, 56, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 97, 100, 125, 126}
    lib_path = ctypes.util.find_library("xkbcommon")
    xkb = ctypes.CDLL(lib_path) if lib_path else None
    if xkb:
        xkb.xkb_context_new.restype = ctypes.c_void_p
        xkb.xkb_keymap_new_from_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
        xkb.xkb_keymap_new_from_string.restype = ctypes.c_void_p
        ctx = xkb.xkb_context_new(0)
    for _, chars in batches:
        assert len(chars) <= len(wi.PRINTABLE_EVDEV)
        keymap, mapping = wi.build_keymap(chars)
        assert keymap.endswith(b"\x00")
        assert forbidden_evdev.isdisjoint(mapping.values())
        if xkb:
            assert xkb.xkb_keymap_new_from_string(ctx, keymap, 1, 0)


async def test_type_text_streams_multibatch_unicode_and_shift_return_over_wayland(tmp_path, monkeypatch):
    sock_path = tmp_path / "wayland-test"
    server = MockWaylandServer(sock_path).start()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-test")
    client_cls = wi._WaylandVirtualKeyboardClient
    monkeypatch.setattr(
        wi,
        "_WaylandVirtualKeyboardClient",
        lambda path: client_cls(path, settle_seconds=0, drain_seconds=0),
    )
    sample = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 "
        "Café — “quotes”\n1. Rice\n2. Oil Done"
    )
    try:
        assert await wi.type_text(sample) is True
    finally:
        server.close()

    assert len(server.vk_objects) == 2
    assert server.destroyed == server.vk_objects
    assert _decode_typed_text(server) == sample


async def test_type_text_stops_if_focus_changes_within_one_batch(tmp_path, monkeypatch):
    sock_path = tmp_path / "wayland-focus"
    server = MockWaylandServer(sock_path).start()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-focus")
    client_cls = wi._WaylandVirtualKeyboardClient
    monkeypatch.setattr(
        wi,
        "_WaylandVirtualKeyboardClient",
        lambda path: client_cls(path, settle_seconds=0, drain_seconds=0),
    )
    checks = iter([True, False])

    async def verify_focus():
        return next(checks)

    sample = "a" * 100
    try:
        assert await wi.type_text(sample, verify_focus=verify_focus) is False
    finally:
        server.close()

    assert _decode_typed_text(server) == "a"
    assert len(server.vk_objects) == 1
    assert server.destroyed == server.vk_objects


async def test_type_text_returns_false_when_compositor_lacks_virtual_keyboard(tmp_path, monkeypatch):
    sock_path = tmp_path / "wayland-novk"
    server = MockWaylandServer(sock_path, advertise_vk=False).start()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-novk")
    try:
        assert await wi.type_text("Hello world") is False
    finally:
        server.close()
    assert server.vk_objects == []


async def test_type_text_returns_false_on_protocol_error_or_missing_display(tmp_path, monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert await wi.type_text("Hello world") is False

    sock_path = tmp_path / "wayland-err"
    server = MockWaylandServer(sock_path, error_on_key=True).start()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-err")
    client_cls = wi._WaylandVirtualKeyboardClient
    monkeypatch.setattr(
        wi,
        "_WaylandVirtualKeyboardClient",
        lambda path: client_cls(path, settle_seconds=0, drain_seconds=0),
    )
    try:
        assert await wi.type_text("Hello") is False
    finally:
        server.close()
