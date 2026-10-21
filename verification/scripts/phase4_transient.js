for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.caption === "设置" || w.caption === "SlugcatPet Overlay" || String(w.caption).indexOf("音乐")>=0) {
    var t = null;
    try { t = w.transientFor ? w.transientFor.caption : null; } catch(e) { t = "err"; }
    print("T", w.caption, "transientFor", t, "keepAbove", w.keepAbove, "layer", w.layer, "pid", w.pid);
  }
}
