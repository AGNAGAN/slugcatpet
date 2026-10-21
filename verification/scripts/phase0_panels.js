function place(w) {
    if (w.caption === "phase0-panels") {
        var s = workspace.screens[1];
        var g = Object.assign({}, s.geometry);
        w.frameGeometry = g;
        w.keepAbove = true;
        w.skipTaskbar = true;
        print("phase0 panels placed", w.frameGeometry);
    }
}
workspace.windowAdded.connect(place);
for (var i = 0; i < workspace.stackingOrder.length; i++) place(workspace.stackingOrder[i]);
