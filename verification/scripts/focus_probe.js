function dump(tag) {
    var a = workspace.activeWindow;
    print("FOCUSPROBE", tag, a ? a.caption : "none", a ? a.pid : 0);
}

dump("load");
workspace.windowActivated.connect(function (w) {
    print("FOCUSPROBE activated", w ? w.caption : "none", w ? w.pid : 0);
});
workspace.windowAdded.connect(function (w) {
    print("FOCUSPROBE added", w ? w.caption : "none", w ? w.pid : 0);
});
workspace.windowRemoved.connect(function (w) {
    print("FOCUSPROBE removed", w ? w.caption : "none", w ? w.pid : 0);
});
