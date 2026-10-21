var o=workspace.stackingOrder;
for (var i=0;i<o.length;i++) {
  var w=o[i];
  if (w.caption === "SlugcatPet Overlay" || w.caption === "slugcatpet-tool-probe" || w.caption === "slugcatpet-move-probe") {
    print("DUMPWIN", w.caption, "frame", JSON.stringify(w.frameGeometry), "out", w.output?w.output.name:"?", "outgeo", w.output?JSON.stringify(w.output.geometry):"?", "keep", w.keepAbove, "skip", w.skipTaskbar, "type", w.type);
  }
}
