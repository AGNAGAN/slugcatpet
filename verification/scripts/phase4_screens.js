for (var i=0;i<workspace.screens.length;i++) {
  var s=workspace.screens[i];
  print("SCREEN", i, s.name, s.geometry.x, s.geometry.y, s.geometry.width, s.geometry.height);
}
for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.caption.indexOf("SlugcatPet")>=0 || w.caption==="设置")
    print("WIN", w.caption, w.resourceClass, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height);
}
