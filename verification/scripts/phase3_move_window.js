for (var i = 0; i < workspace.stackingOrder.length; i++) {
    var w = workspace.stackingOrder[i];
    if (w.resourceClass === "Alacritty") {
        w.frameGeometry = {x: 0, y: 900, width: 1707, height: 1067};
        print("phase3 moved", w.caption, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height);
    }
}
