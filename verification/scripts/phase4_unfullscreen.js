for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (w.resourceClass === "Alacritty" && w.fullScreen) {
    print("FS-UNSET", w.caption);
    w.fullScreen = false;
    break;
  }
}
