print("dbus probe script loaded", workspace.cursorPos);
callDBus("org.slugcatpet.Probe", "/Probe", "org.slugcatpet.Probe", "Note", "hello from kwin");
callDBus("org.slugcatpet.Probe", "/Probe", "org.slugcatpet.Probe", "Cursor", workspace.cursorPos.x, workspace.cursorPos.y);
workspace.cursorPosChanged.connect(function() {
    callDBus("org.slugcatpet.Probe", "/Probe", "org.slugcatpet.Probe", "Cursor", workspace.cursorPos.x, workspace.cursorPos.y);
});
