print("FS3-START");
for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.resourceClass === "Alacritty" && w.caption.indexOf("slugcatpet") >= 0) {
    print("FS3-SET", w.caption, w.frameGeometry.x, w.frameGeometry.y);
    w.fullScreen = true;
    print("FS3-DONE", w.fullScreen);
    break;
  }
}
