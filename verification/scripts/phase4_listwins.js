for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.caption === "设置" || w.caption === "SlugcatPet Overlay" || String(w.caption).indexOf("音乐")>=0)
    print("LW", w.caption, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height, w.transientFor ? w.transientFor.caption : null);
}
