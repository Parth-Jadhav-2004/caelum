"""Exercise the real exported tray protocol on an isolated session bus."""

import os
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    os.environ.get("CAELUM_DESKTOP_TESTS") != "1" or not shutil.which("dbus-run-session"),
    reason="Opt-in native Gio test with an isolated D-Bus session",
)
def test_status_notifier_registration_menu_actions_and_cleanup():
    probe = r'''
import time
from gi.repository import Gio, GLib
from caelum.tray import Tray, ITEM_PATH, ITEM_INTERFACE, MENU_PATH, MENU_INTERFACE
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
seen = []
availability = []
watcher = Gio.DBusNodeInfo.new_for_xml("""<node><interface name="org.kde.StatusNotifierWatcher">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
</interface></node>""").interfaces[0]
def register(bus, sender, path, interface, method, parameters, invocation):
    seen.append(parameters.unpack()[0])
    invocation.return_value(None)
registration = bus.register_object('/StatusNotifierWatcher', watcher, register, None, None)
owner = Gio.bus_own_name_on_connection(bus, 'org.kde.StatusNotifierWatcher', Gio.BusNameOwnerFlags.NONE, None, None)
tray = Tray(lambda: seen.append('open'), lambda: seen.append('settings'),
            lambda: seen.append('pause'), lambda: seen.append('quit'), availability.append)
def wait(predicate):
    deadline = time.monotonic() + 4
    while not predicate():
        assert time.monotonic() < deadline, 'D-Bus operation timed out'
        GLib.MainContext.default().iteration(False)
        time.sleep(.001)
wait(lambda: tray.registered)
assert seen[0] == bus.get_unique_name()
assert availability == [True]
def call(path, interface, method, parameters=None):
    result = []
    def done(bus, response):
        try:
            result.append(bus.call_finish(response))
        except Exception as error:
            result.append(error)
    bus.call(bus.get_unique_name(), path, interface, method, parameters, None,
             Gio.DBusCallFlags.NONE, 3000, None, done)
    wait(lambda: bool(result))
    if isinstance(result[0], Exception):
        raise result[0]
    return result[0].unpack()
properties = call(ITEM_PATH, 'org.freedesktop.DBus.Properties', 'GetAll', GLib.Variant('(s)', (ITEM_INTERFACE,)))[0]
assert properties['IconName'] == 'caelum-symbolic'
from pathlib import Path
assert (Path(properties['IconThemePath']) / 'caelum-symbolic.svg').is_file()
assert properties['ToolTip'][0] == 'caelum-symbolic'
revision, layout = call(MENU_PATH, MENU_INTERFACE, 'GetLayout', GLib.Variant('(iias)', (0, -1, [])))
assert [item[1]['label'] for item in layout[2]] == ['Open Caelum', 'Settings', 'Start dictation', 'Quit Caelum']
assert layout[2][2][1]['enabled']
tray.update(True, True, 'Paused')
revision2, layout = call(MENU_PATH, MENU_INTERFACE, 'GetLayout', GLib.Variant('(iias)', (0, -1, [])))
assert revision2 > revision
assert layout[2][2][1]['label'] == 'Resume dictation'
assert layout[2][2][1]['enabled']
assert call(ITEM_PATH, 'org.freedesktop.DBus.Properties', 'Get', GLib.Variant('(ss)', (ITEM_INTERFACE, 'Menu'))) == (MENU_PATH,)
call(ITEM_PATH, ITEM_INTERFACE, 'Activate', GLib.Variant('(ii)', (0, 0)))
for identifier in (2, 3, 4):
    call(MENU_PATH, MENU_INTERFACE, 'Event', GLib.Variant('(isvu)', (identifier, 'clicked', GLib.Variant('i', 0), 0)))
assert seen[1:] == ['open', 'settings', 'pause', 'quit']
Gio.bus_unown_name(owner)
wait(lambda: not tray.registered)
assert availability[-1] is False
owner = Gio.bus_own_name_on_connection(bus, 'org.kde.StatusNotifierWatcher', Gio.BusNameOwnerFlags.NONE, None, None)
wait(lambda: tray.registered)
tray.close()
assert not tray.registered and not tray.objects
bus.unregister_object(registration)
Gio.bus_unown_name(owner)
'''
    result = subprocess.run(
        ["dbus-run-session", "--", sys.executable, "-c", probe],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
