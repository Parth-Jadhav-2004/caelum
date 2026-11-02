"""StatusNotifierItem and DBusMenu integration using GTK's existing Gio runtime."""

from gi.repository import Gio, GLib

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
WATCHER = "org.kde.StatusNotifierWatcher"
ITEM_INTERFACE = "org.kde.StatusNotifierItem"
MENU_INTERFACE = "com.canonical.dbusmenu"

ITEM_XML = """<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/>
<property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/>
<property name="Status" type="s" access="read"/>
<property name="WindowId" type="i" access="read"/>
<property name="IconName" type="s" access="read"/>
<property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/>
<property name="Menu" type="o" access="read"/>
<signal name="NewStatus"><arg type="s"/></signal>
<signal name="NewToolTip"/>
</interface></node>"""

MENU_XML = """<node><interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/>
<arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/>
<arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/>
<arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/>
<arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/>
<arg type="ai" direction="out"/></method>
<property name="Version" type="u" access="read"/>
<property name="TextDirection" type="s" access="read"/>
<property name="Status" type="s" access="read"/>
<property name="IconThemePath" type="as" access="read"/>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
</interface></node>"""


class Tray:
    def __init__(self, open_app, settings, pause, quit_app, availability=None):
        self.actions = {1: open_app, 2: settings, 3: pause, 4: quit_app}
        self.availability = availability or (lambda available: None)
        self.registered = False
        self.closed = False
        self.paused = False
        self.running = False
        self.status = "Starting dictation"
        self.revision = 1
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.objects = []
        for path, xml in ((ITEM_PATH, ITEM_XML), (MENU_PATH, MENU_XML)):
            interface = Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0]
            self.objects.append(self.bus.register_object(
                path, interface, self.method, self.property, None
            ))
        self.watch = Gio.bus_watch_name_on_connection(
            self.bus, WATCHER, Gio.BusNameWatcherFlags.NONE,
            lambda *_: self.register(), lambda *_: self.unavailable(),
        )

    def register(self):
        self.bus.call(
            WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (self.bus.get_unique_name(),)), None,
            Gio.DBusCallFlags.NONE, 3000, None, self.registered_item,
        )

    def registered_item(self, bus, result):
        try:
            bus.call_finish(result)
        except GLib.Error:
            self.unavailable()
            return
        if not self.closed:
            self.registered = True
            self.availability(True)

    def unavailable(self):
        self.registered = False
        if not self.closed:
            self.availability(False)

    def properties(self, identifier):
        if identifier == 0:
            return {"children-display": GLib.Variant("s", "submenu")}
        dictation = "Start dictation" if not self.running else "Resume dictation" if self.paused else "Pause dictation"
        labels = {1: "Open Caelum", 2: "Settings", 3: dictation, 4: "Quit Caelum"}
        if identifier not in labels:
            raise ValueError("Unknown menu item")
        return {
            "label": GLib.Variant("s", labels[identifier]),
            "enabled": GLib.Variant("b", True),
            "visible": GLib.Variant("b", True),
        }

    def layout(self, identifier, depth, names):
        properties = self.properties(identifier)
        if names:
            properties = {key: value for key, value in properties.items() if key in names}
        children = [GLib.Variant("(ia{sv}av)", self.layout(child, 0, names))
                    for child in self.actions] if identifier == 0 and depth != 0 else []
        return identifier, properties, children

    def event(self, identifier, event):
        if event == "clicked" and identifier in self.actions:
            self.actions[identifier]()

    def method(self, bus, sender, path, interface, method, parameters, invocation):
        args = parameters.unpack()
        try:
            if interface == ITEM_INTERFACE:
                if method in ("Activate", "SecondaryActivate", "ContextMenu"):
                    self.actions[1]()
                result = None
            elif method == "GetLayout":
                result = GLib.Variant("(u(ia{sv}av))", (self.revision, self.layout(*args)))
            elif method == "GetGroupProperties":
                ids, names = args
                result = GLib.Variant("(a(ia{sv}))", ([
                    (identifier, self.layout(identifier, 0, names)[1]) for identifier in ids
                ],))
            elif method == "GetProperty":
                result = GLib.Variant("(v)", (self.properties(args[0])[args[1]],))
            elif method == "Event":
                self.event(*args[:2])
                result = None
            elif method == "EventGroup":
                errors = []
                for identifier, event, _, _ in args[0]:
                    if identifier not in self.actions:
                        errors.append(identifier)
                    else:
                        self.event(identifier, event)
                result = GLib.Variant("(ai)", (errors,))
            elif method == "AboutToShow":
                result = GLib.Variant("(b)", (False,))
            elif method == "AboutToShowGroup":
                result = GLib.Variant("(aiai)", ([], []))
            else:
                invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)
                return
            invocation.return_value(result)
        except (ValueError, KeyError):
            invocation.return_dbus_error("com.canonical.dbusmenu.Error.InvalidMenuItem", "Unknown menu item or property")

    def property(self, bus, sender, path, interface, name):
        if interface == MENU_INTERFACE:
            return {"Version": GLib.Variant("u", 3), "TextDirection": GLib.Variant("s", "ltr"),
                    "Status": GLib.Variant("s", "normal"), "IconThemePath": GLib.Variant("as", [])}.get(name)
        return {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "caelum"), "Title": GLib.Variant("s", "Caelum"),
            "Status": GLib.Variant("s", "Active"), "WindowId": GLib.Variant("i", 0),
            "IconName": GLib.Variant("s", "audio-input-microphone-symbolic"),
            "IconPixmap": GLib.Variant("a(iiay)", []),
            "ToolTip": GLib.Variant("(sa(iiay)ss)", ("audio-input-microphone-symbolic", [], "Caelum", self.status)),
            "ItemIsMenu": GLib.Variant("b", False), "Menu": GLib.Variant("o", MENU_PATH),
        }.get(name)

    def update(self, running, paused, status):
        if (running, paused, status) == (self.running, self.paused, self.status):
            return
        self.running, self.paused, self.status = running, paused, status
        self.revision += 1
        self.bus.emit_signal(None, MENU_PATH, MENU_INTERFACE, "LayoutUpdated",
                             GLib.Variant("(ui)", (self.revision, 0)))
        self.bus.emit_signal(None, ITEM_PATH, ITEM_INTERFACE, "NewToolTip", None)

    def close(self):
        self.closed = True
        Gio.bus_unwatch_name(self.watch)
        for identifier in self.objects:
            self.bus.unregister_object(identifier)
        self.objects.clear()
        self.registered = False
