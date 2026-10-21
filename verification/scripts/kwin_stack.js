for (var i = 0; i < workspace.stackingOrder.length; i++) {
    var w = workspace.stackingOrder[i];
    if (w.caption === "phase0-overlay" || w.caption === "phase0-target")
        print("STACK", i, w.caption, "keepAbove", w.keepAbove, "skipTaskbar", w.skipTaskbar, "geo", w.frameGeometry);
}
