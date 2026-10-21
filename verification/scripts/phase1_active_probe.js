function dump() {
    print("PHASE1ACTIVE active", workspace.activeWindow ? workspace.activeWindow.caption : "none");
    for (var i = 0; i < workspace.stackingOrder.length; i++) {
        var w = workspace.stackingOrder[i];
        if (w.caption === "SlugcatPet Overlay") print("PHASE1ACTIVE overlay active", w.active, "keepAbove", w.keepAbove, "geo", w.frameGeometry);
    }
}
dump();
