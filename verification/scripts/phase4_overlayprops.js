for (var i=0;i<workspace.stackingOrder.length;i++) {
  var w=workspace.stackingOrder[i];
  if (String(w.caption).indexOf("SlugcatPet Overlay")===0)
    print("OVERLAY", JSON.stringify({caption:w.caption, desktopFileName:w.desktopFileName, keepAbove:w.keepAbove, skipTaskbar:w.skipTaskbar, skipSwitcher:w.skipSwitcher, x:w.frameGeometry.x, y:w.frameGeometry.y, w:w.frameGeometry.width, h:w.frameGeometry.height}));
}
