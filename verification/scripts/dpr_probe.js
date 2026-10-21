function place(w) {
    if (w.caption === "phase0-dpr") {
        var s = workspace.screens[0];
        var g = Object.assign({}, s.geometry);
        w.frameGeometry = g; w.keepAbove = true; w.skipTaskbar = true;
        print("phase0 dpr placed", w.frameGeometry, "output", w.output ? w.output.name : "?", "geo", w.output ? w.output.geometry : "?");
    }
}
workspace.windowAdded.connect(place);
for (var i = 0; i < workspace.stackingOrder.length; i++) place(workspace.stackingOrder[i]);
function dump() {
    for (var i = 0; i < workspace.stackingOrder.length; i++) {
        var w = workspace.stackingOrder[i];
        if (w.caption === "phase0-dpr") print("phase0 dpr state", w.frameGeometry, "output", w.output ? w.output.name : "?");
    }
}
dump();
