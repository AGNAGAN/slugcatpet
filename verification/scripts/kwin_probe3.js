function place(w) {
    if (w.caption !== "slugcatpet-probe3") return;
    print("probe3 found", w.caption, w.resourceClass, w.resourceName, w.frameGeometry, "moveable", w.moveable, "resizeable", w.resizeable);
    var full = workspace.clientArea(KWin.FullArea, w);
    print("probe3 full", full);
    w.keepAbove = true;
    w.skipTaskbar = true;
    w.frameGeometry = full;
    print("probe3 after", w.frameGeometry, "keepAbove", w.keepAbove);
}
workspace.windowAdded.connect(place);
print("probe3 script loaded");
