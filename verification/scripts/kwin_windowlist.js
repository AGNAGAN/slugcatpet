function snapshot() {
    var arr = [];
    for (var i = 0; i < workspace.stackingOrder.length; i++) {
        var w = workspace.stackingOrder[i];
        if (w.dock || w.desktopWindow || w.notification || w.tooltip || w.skipTaskbar) continue;
        arr.push({caption: w.caption, resourceClass: w.resourceClass,
                  x: w.frameGeometry.x, y: w.frameGeometry.y,
                  w: w.frameGeometry.width, h: w.frameGeometry.height,
                  full: w.fullScreen, minimized: w.minimized});
    }
    callDBus("org.slugcatpet.Phase0Meta", "/Meta", "org.slugcatpet.Phase0Meta", "WindowList", JSON.stringify(arr));
    print("windowlist sent", arr.length);
}
snapshot();
