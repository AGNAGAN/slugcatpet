for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.resourceClass === "Alacritty" && w.frameGeometry.y < 100 && w.frameGeometry.width < 1400) {
    print("FS-SET", w.caption, w.frameGeometry.x, w.frameGeometry.y, w.frameGeometry.width, w.frameGeometry.height);
    w.fullScreen = true;
    break;
  }
}
