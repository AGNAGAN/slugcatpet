for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.caption === "SlugcatPet Overlay") print("OVERLAY3", JSON.stringify({visible:w.visible, minimized:w.minimized, x:w.frameGeometry.x, y:w.frameGeometry.y, w:w.frameGeometry.width, h:w.frameGeometry.height}));
  if (w.resourceClass === "Alacritty") print("ALAC3", w.caption, w.fullScreen, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height, w.visible);
}
