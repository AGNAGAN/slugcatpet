function dump() {
    for (var i = 0; i < workspace.stackingOrder.length; i++) {
        var w = workspace.stackingOrder[i];
        if (w.caption === "SlugcatPet Overlay") {
            print("PHASE1P overlay", w.frameGeometry, "output", w.output ? w.output.name : "none", "screen", w.screen ? w.screen.name : "none", "keepAbove", w.keepAbove, "desktop", w.desktopFileName);
        }
        if (w.caption === "phase1-target") print("PHASE1P target", w.frameGeometry, "output", w.output ? w.output.name : "none");
    }
}
dump();
