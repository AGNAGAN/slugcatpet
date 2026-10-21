function dump() {
    for (var i = 0; i < workspace.stackingOrder.length; i++) {
        var w = workspace.stackingOrder[i];
        if (w.caption === "SlugcatPet Overlay") {
            print("PHASE1 overlay", w.frameGeometry, "keepAbove", w.keepAbove, "skipTaskbar", w.skipTaskbar, "active", w.active, "resource", w.resourceClass, "desktop", w.desktopFileName);
        }
    }
    print("PHASE1 active", workspace.activeWindow ? workspace.activeWindow.caption : "none");
}
dump();
