function place(w) {
    print("found", w.caption, w.resourceClass, w.resourceName, w.frameGeometry, "moveable", w.moveable, "resizeable", w.resizeable);
    var area = workspace.clientArea(KWin.WorkArea, w);
    print("area", area, "full", workspace.clientArea(KWin.FullArea, w));
    w.keepAbove = true;
    w.skipTaskbar = true;
    w.frameGeometry = workspace.clientArea(KWin.FullArea, w);
    print("after set", w.frameGeometry);
    w.frameGeometry = KWin.RectF(0, 0, 800, 600);
    print("after set2", w.frameGeometry);
}
workspace.windowAdded.connect(place);
for (var i = 0; i < workspace.stackingOrder.length; i++) place(workspace.stackingOrder[i]);
