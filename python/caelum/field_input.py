"""Clipboard-free insertion into a specific Linux accessibility-bus object."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from dbus_next import Message, MessageType
from dbus_next.aio import MessageBus
from dbus_next.errors import AuthError, InvalidAddressError

DBUS = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
ROOT = "/org/a11y/atspi/accessible/root"
ATSPI = "org.a11y.atspi."
ACCESSIBLE = ATSPI + "Accessible"
TEXT = ATSPI + "Text"
EDITABLE = ATSPI + "EditableText"
# Stable AT-SPI StateType and Role values from atspi-constants.h.
ACTIVE, EDITABLE_STATE, FOCUSED, READ_ONLY = 1, 7, 12, 43
PASSWORD_TEXT, TERMINAL = 40, 60
WINDOW_ROLES = (16, 23, 69)  # dialog, frame, window


@dataclass(frozen=True)
class Field:
    bus_id: str
    owner: str
    path: str
    window: str


async def call(bus, owner, path, interface, member, signature="", body=None):
    reply = await bus.call(Message(destination=owner, path=path, interface=interface,
                                   member=member, signature=signature, body=body or []))
    if reply.message_type != MessageType.METHOD_RETURN:
        raise RuntimeError("Desktop text interface unavailable")
    return reply.body


@asynccontextmanager
async def connection():
    session = await MessageBus().connect()
    try:
        address, = await call(session, "org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress")
    finally:
        session.disconnect()
    bus = await MessageBus(bus_address=address).connect()
    try:
        yield bus
    finally:
        bus.disconnect()


def state(bits, n):
    return len(bits) > n // 32 and bool(bits[n // 32] & (1 << (n % 32)))


def eligible(bits):
    return state(bits, FOCUSED) and state(bits, EDITABLE_STATE) and not state(bits, READ_ONLY)


async def collection_field(bus, bus_id, owner, root):
    # ATK clients can expose Collection without implementing Cache.GetItems.
    # Match all specified states and interfaces, in canonical order.
    rule = [[(1 << FOCUSED) | (1 << EDITABLE_STATE), 0], 1, {}, 1, [], 1, ["EditableText"], 1, False]
    matches, = await call(bus, owner, root, ATSPI + "Collection", "GetMatches",
                          "(aiia{ss}iaiiasib)uib", [rule, 1, 2, True])
    if len(matches) != 1 or matches[0][0] != owner:
        return None
    path = matches[0][1]
    parent = path
    for _ in range(64):
        role, = await call(bus, owner, parent, ACCESSIBLE, "GetRole")
        if role in (PASSWORD_TEXT, TERMINAL):
            break
        if role in WINDOW_ROLES:
            flags, = await call(bus, owner, parent, ACCESSIBLE, "GetState")
            return Field(bus_id, owner, path, parent) if state(flags, ACTIVE) else None
        ref, = await call(bus, owner, parent, "org.freedesktop.DBus.Properties", "Get",
                          "ss", [ACCESSIBLE, "Parent"])
        if ref.value[0] != owner:
            break
        parent = ref.value[1]
    return None


async def app_field(bus, bus_id, owner, root, pid):
    if not owner.startswith(":"):
        return None
    if pid is not None and await call(bus, DBUS, DBUS_PATH, DBUS, "GetConnectionUnixProcessID",
                                      "s", [owner]) != [pid]:
        return None
    try:
        rows, = await call(bus, owner, "/org/a11y/atspi/cache", ATSPI + "Cache", "GetItems")
    except RuntimeError:
        return await collection_field(bus, bus_id, owner, root)
    # Cache rows include a parent reference, interfaces, role and current state.
    # Retain only the object's address; never read the contents of a text field.
    objects = {row[0][1]: row for row in rows if row[0][0] == owner}
    matches = []
    for path, row in objects.items():
        if EDITABLE not in row[-5] or row[-3] in (PASSWORD_TEXT, TERMINAL) or not eligible(row[-1]):
            continue
        parent = row
        for _ in range(64):
            if parent[-3] in (PASSWORD_TEXT, TERMINAL):
                break
            if parent[-3] in WINDOW_ROLES:
                if state(parent[-1], ACTIVE):
                    matches.append(Field(bus_id, owner, path, parent[0][1]))
                break
            parent = objects.get(parent[2][1]) if parent[2][0] == owner else None
            if parent is None:
                break
    return matches[0] if len(matches) == 1 else None


UNAVAILABLE = (OSError, EOFError, RuntimeError, TimeoutError, ValueError, AuthError, InvalidAddressError)


async def focused_field(pid=None):
    try:
        async with asyncio.timeout(0.65), connection() as bus:
            bus_id, = await call(bus, DBUS, DBUS_PATH, DBUS, "GetId")
            apps, = await call(bus, ATSPI + "Registry", ROOT, ACCESSIBLE, "GetChildren")
            fields = await asyncio.gather(*(app_field(bus, bus_id, owner, root, pid) for owner, root in apps),
                                          return_exceptions=True)
            matches = [field for field in fields if isinstance(field, Field)]
            return matches[0] if len(matches) == 1 else None
    except UNAVAILABLE:
        return None


async def insert_field(text, field):
    if not field or not text or "\x00" in text:
        return False
    inserted = False
    try:
        async with asyncio.timeout(1), connection() as bus:
            if await call(bus, DBUS, DBUS_PATH, DBUS, "GetId") != [field.bus_id]:
                return False
            async def widget(iface, method, sig="", args=None):
                return await call(bus, field.owner, field.path, iface, method, sig, args)

            if await widget(ACCESSIBLE, "GetRole") in ([PASSWORD_TEXT], [TERMINAL]):
                return False
            if await widget(TEXT, "GetNSelections") != [0]:
                return False  # No atomic selection replacement in AT-SPI; never delete user text.
            caret, = await widget("org.freedesktop.DBus.Properties", "Get", "ss", [TEXT, "CaretOffset"])
            window, = await call(bus, field.owner, field.window, ACCESSIBLE, "GetState")
            current, = await widget(ACCESSIBLE, "GetState")
            if caret.value < 0 or not state(window, ACTIVE) or not eligible(current):
                return False
            # Object-addressed plain text, not simulated keys (including embedded newlines).
            inserted = await widget(EDITABLE, "InsertText", "isi",
                                    [caret.value, text, len(text.encode())]) == [True]
            if inserted:
                # GTK's editable interface can insert without advancing the caret.
                # Leave a caret already moved by the app or the user alone.
                after, = await widget("org.freedesktop.DBus.Properties", "Get", "ss", [TEXT, "CaretOffset"])
                if after.value == caret.value and eligible((await widget(ACCESSIBLE, "GetState"))[0]):
                    await widget(TEXT, "SetCaretOffset", "i", [caret.value + len(text)])
            return inserted
    except UNAVAILABLE:
        return inserted
