for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.caption === "SlugcatPet Overlay" || w.caption === "设置")
    print("WIN", w.caption, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height, w.keepAbove, w.transientFor ? w.transientFor.caption : null);
}
