function go() {
    var target = null;
    for (var i = 0; i < workspace.stackingOrder.length; i++) {
        if (workspace.stackingOrder[i].caption === "phase3-fullscreen") {
            target = workspace.stackingOrder[i];
        }
    }
    var out = null;
    for (var j = 0; j < workspace.screens.length; j++) {
        if (workspace.screens[j].name === "HDMI-A-1") out = workspace.screens[j];
    }
    if (target && out) {
        target.frameGeometry = {x: Math.round(out.geometry.x), y: Math.round(out.geometry.y), width: Math.round(out.geometry.width), height: Math.round(out.geometry.height)};
        target.fullScreen = true;
        workspace.activeWindow = target;
        print("phase3 force fullscreen", out.name, out.geometry.width, out.geometry.height);
    } else {
        print("phase3 force failed", target, out);
    }
}
go();
