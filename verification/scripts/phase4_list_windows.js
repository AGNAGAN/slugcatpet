for (var i = 0; i < workspace.stackingOrder.length; i++) {
    var w = workspace.stackingOrder[i];
    print("WIN", w.caption, w.resourceClass, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height, "skip", w.skipTaskbar);
}
