function targetScreen() {
    for (var i = 0; i < workspace.screens.length; i++) {
        if (workspace.screens[i].name === "eDP-1") return workspace.screens[i];
    }
    return workspace.screens[0];
}
function place(w) {
    if (w.caption === "phase1-target") {
        var s = targetScreen();
        w.frameGeometry = { x: s.geometry.x, y: s.geometry.y, width: 1440, height: 900 };
        w.keepAbove = false;
        print("phase1 target placed", w.frameGeometry);
    }
}
workspace.windowAdded.connect(place);
for (var i = 0; i < workspace.stackingOrder.length; i++) place(workspace.stackingOrder[i]);
print("phase1 target script loaded");
