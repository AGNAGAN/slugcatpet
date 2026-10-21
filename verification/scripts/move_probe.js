function find() {
    var order = workspace.stackingOrder;
    for (var i = 0; i < order.length; i++) {
        if (order[i].caption === "slugcatpet-move-probe") return order[i];
    }
    return null;
}
function move(tag) {
    var w = find();
    if (!w) { print("MOVEPROBE", tag, "no-window"); return; }
    print("MOVEPROBE", tag, "before", JSON.stringify(w.frameGeometry), "out", w.output ? w.output.name : "?", "outgeo", w.output ? JSON.stringify(w.output.geometry) : "?");
    var g = {x: 0, y: 0, width: 1440, height: 900};
    w.frameGeometry = g;
    print("MOVEPROBE", tag, "after", JSON.stringify(w.frameGeometry), "out", w.output ? w.output.name : "?");
}
function scan() {
    var w = find();
    if (w) move("scan");
}
workspace.windowAdded.connect(function(w){ if (w.caption === "slugcatpet-move-probe") move("added"); });
workspace.screensChanged.connect(function(){ move("screens"); });
for (var i = 0; i < workspace.stackingOrder.length; i++) { if (workspace.stackingOrder[i].caption === "slugcatpet-move-probe") move("load"); }
