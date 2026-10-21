var target = null;
for (var i = 0; i < workspace.stackingOrder.length; i++) {
    var w = workspace.stackingOrder[i];
    if (w.resourceClass === "Alacritty") {
        target = w;
    }
}
if (target) {
    print("FOCUSPROBE target", target.caption, target.pid);
    try {
        workspace.activeWindow = target;
        print("FOCUSPROBE assign-ok", workspace.activeWindow ? workspace.activeWindow.caption : "none");
    } catch (e) {
        print("FOCUSPROBE assign-error", String(e));
    }
} else {
    print("FOCUSPROBE no-target");
}
