function targetScreen() {
    for (var i = 0; i < workspace.screens.length; i++) {
        if (workspace.screens[i].name === "eDP-1") return workspace.screens[i];
    }
    return workspace.screens[0];
}
function place(w) {
    var s = targetScreen();
    if (w.caption === "phase1-target") {
        w.frameGeometry = { x: s.geometry.x, y: s.geometry.y, width: 1200, height: 700 };
        w.keepAbove = false;
        print("phase1 target placed", w.frameGeometry, "screen", s.name, s.geometry);
    }
    if (w.caption === "phase1-pet") {
        w.frameGeometry = { x: s.geometry.x, y: s.geometry.y, width: s.geometry.width, height: s.geometry.height };
        w.keepAbove = true;
        w.skipTaskbar = true;
        w.skipSwitcher = true;
        print("phase1 pet placed", w.frameGeometry, "screen", s.name, s.geometry);
    }
}
workspace.windowAdded.connect(place);
for (var i = 0; i < workspace.stackingOrder.length; i++) place(workspace.stackingOrder[i]);
print("phase1 script loaded, screens", workspace.screens.length);
