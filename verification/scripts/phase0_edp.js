function place(w) {
    if (w.caption === "phase0-edp-target") {
        var s = workspace.screens[0];
        w.frameGeometry = { x: s.geometry.x, y: s.geometry.y, width: 1200, height: 700 };
        w.keepAbove = false;
        print("phase0 edp target placed", w.frameGeometry);
    }
    if (w.caption === "phase0-edp-overlay") {
        var s = workspace.screens[0];
        var g = Object.assign({}, s.geometry);
        w.frameGeometry = g;
        w.keepAbove = true;
        w.skipTaskbar = true;
        print("phase0 edp overlay placed", w.frameGeometry, "keepAbove", w.keepAbove);
    }
}
workspace.windowAdded.connect(place);
for (var i = 0; i < workspace.stackingOrder.length; i++) place(workspace.stackingOrder[i]);
