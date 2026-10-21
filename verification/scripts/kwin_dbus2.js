print("dbus2 loaded", workspace.cursorPos);
callDBus("org.slugcatpet.Probe", "/Probe", "local.py.dbus_probe.Probe", "Note", "hello2");
callDBus("org.slugcatpet.Probe", "/Probe", "local.py.dbus_probe.Probe", "Cursor", workspace.cursorPos.x, workspace.cursorPos.y);
workspace.cursorPosChanged.connect(function() {
    callDBus("org.slugcatpet.Probe", "/Probe", "local.py.dbus_probe.Probe", "Cursor", workspace.cursorPos.x, workspace.cursorPos.y);
});
