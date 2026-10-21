function find() {
    var order = workspace.stackingOrder;
    for (var i = 0; i < order.length; i++) if (order[i].caption === "SlugcatPet Overlay") return order[i];
    return null;
}
function dump(tag, w) {
    print("OVERLAYMOVE", tag, "frame", JSON.stringify(w.frameGeometry), "out", w.output ? w.output.name : "?", "geo", JSON.stringify(w.geometry));
}
function move(tag) {
    var w = find();
    if (!w) { print("OVERLAYMOVE", tag, "none"); return; }
    dump(tag+"-before", w);
    try { w.frameGeometry = {x:0,y:0,width:1440,height:932}; } catch(e) { print("OVERLAYMOVE set-error", String(e)); }
    dump(tag+"-after", w);
    QTimer.singleShot(400, function(){ if (find()) dump(tag+"-later", find()); });
}
workspace.windowAdded.connect(function(w){ if (w.caption === "SlugcatPet Overlay") move("added"); });
move("load");
