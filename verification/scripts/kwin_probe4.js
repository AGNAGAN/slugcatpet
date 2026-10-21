function place(w) {
    if (w.caption !== "slugcatpet-probe4") return;
    print("probe4 found", w.frameGeometry, "output", w.output.name, w.output.geometry);
    var area = workspace.clientArea(KWin.WorkArea, w.output, workspace.currentDesktop);
    print("probe4 area", area);
    w.keepAbove = true;
    w.skipTaskbar = true;
    w.frameGeometry = w.output.geometry;
    print("probe4 after", w.frameGeometry);
}
workspace.windowAdded.connect(place);
print("probe4 loaded");
