for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.caption === "SlugcatPet Overlay") print("OVERLAY", JSON.stringify({visible:w.visible, minimized:w.minimized, x:w.frameGeometry.x, y:w.frameGeometry.y, w:w.frameGeometry.width, h:w.frameGeometry.height}));
  if (w.resourceClass === "Alacritty") print("ALACRITTY", w.caption, w.fullScreen, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height);
}
