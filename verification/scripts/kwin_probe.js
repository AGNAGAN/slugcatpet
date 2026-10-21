function findAndPlace() {
    var wins = workspace.stackingOrder;
    for (var i = 0; i < wins.length; i++) {
        var w = wins[i];
        if (w.caption === "slugcatpet-probe") {
            print("probe found", w.resourceClass, w.resourceName, w.frameGeometry);
            var area = workspace.clientArea(KWin.WorkArea, w);
            print("probe area", area);
            w.keepAbove = true;
            w.skipTaskbar = true;
            w.skipSwitcher = true;
            w.frameGeometry = area;
            print("probe placed", w.frameGeometry, "keepAbove", w.keepAbove);
        }
    }
}
workspace.windowAdded.connect(findAndPlace);
findAndPlace();
