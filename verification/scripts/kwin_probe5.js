function place(w) {
    if (w.caption !== "slugcatpet-probe5") return;
    print("probe5 found", w.frameGeometry, "output", w.output.name, w.output.geometry);
    var g = Object.assign({}, w.output.geometry);
    g.x = w.output.geometry.x;
    g.y = w.output.geometry.y;
    g.width = w.output.geometry.width;
    g.height = w.output.geometry.height;
    w.keepAbove = true;
    w.skipTaskbar = true;
    w.frameGeometry = g;
    print("probe5 set", g, "after", w.frameGeometry);
}
workspace.windowAdded.connect(place);
print("probe5 loaded");
