for (var i = 0; i < workspace.stackingOrder.length; i++) {
    var w = workspace.stackingOrder[i];
    if (w.caption && w.caption.indexOf("phase0") >= 0) print("LEFTOVER", w.caption, w.frameGeometry);
}
print("leftover check done");
