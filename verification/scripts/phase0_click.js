function place(w) {
    if (w.caption === "phase0-target") {
        var t = workspace.screens[1];
        w.frameGeometry = { x: t.geometry.x, y: t.geometry.y, width: 900, height: 700 };
        w.keepAbove = false;
        print("phase0 target placed", w.frameGeometry);
    }
    if (w.caption === "phase0-overlay") {
        var s = workspace.screens[1];
        var g = Object.assign({}, s.geometry);
        g.x = s.geometry.x; g.y = s.geometry.y; g.width = s.geometry.width; g.height = s.geometry.height;
        w.frameGeometry = g;
        w.keepAbove = true;
        w.skipTaskbar = true;
        w.skipSwitcher = true;
        print("phase0 overlay placed", w.frameGeometry, "keepAbove", w.keepAbove);
    }
}
workspace.windowAdded.connect(place);
for (var i = 0; i < workspace.stackingOrder.length; i++) place(workspace.stackingOrder[i]);
function sendCursor() {
    callDBus("org.slugcatpet.Phase0", "/Phase0", "org.slugcatpet.Phase0", "Cursor", workspace.cursorPos.x, workspace.cursorPos.y);
}
workspace.cursorPosChanged.connect(sendCursor);
sendCursor();
print("phase0 click script loaded");
