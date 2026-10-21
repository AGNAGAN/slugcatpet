function dump(tag) {
    var order = workspace.stackingOrder;
    var at = null;
    try {
        var seq = workspace.windowAt(workspace.cursorPos);
        at = seq && seq.length ? seq[0] : null;
    } catch (e) {
        at = null;
    }
    print("STACKPROBE", tag, "active", workspace.activeWindow ? workspace.activeWindow.caption : "none", "cursor", workspace.cursorPos.x, workspace.cursorPos.y, "windowAt", at ? at.caption : "none");
    for (var i = 0; i < order.length; i++) {
        var w = order[i];
        if (w.caption === "SlugcatPet Overlay" || w.caption === "SlugcatPet Cursor Capture" || w.resourceClass === "Alacritty") {
            print("STACKPROBE", tag, i, w.caption, "keepAbove", w.keepAbove, "active", w.active, "layer", w.layer, "wantsInput", w.wantsInput, "geo", w.x, w.y, w.width, w.height, "hidden", w.hidden, "minimized", w.minimized);
        }
    }
}

workspace.windowAdded.connect(function (w) {
    if (w && w.caption === "SlugcatPet Cursor Capture") {
        dump("capture-added");
        QTimer.singleShot(200, function () { dump("capture-later"); });
    }
});
workspace.windowActivated.connect(function (w) {
    if (w && (w.caption === "SlugcatPet Cursor Capture" || w.caption === "SlugcatPet Overlay")) {
        dump("activated-" + w.caption);
    }
});
dump("load");
