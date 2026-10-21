for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (String(w.caption).indexOf("设置")>=0 || String(w.caption).indexOf("SlugcatPet")>=0 || String(w.caption).indexOf("音乐")>=0)
    print("W", w.caption, w.resourceClass, w.pid, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height, w.keepAbove);
}
