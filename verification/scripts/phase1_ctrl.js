function place(w) {
  if (w.caption === "phase1-ctrl-overlay") {
    for (var i=0;i<workspace.screens.length;i++) {
      var s=workspace.screens[i];
      if (s.name === "eDP-1") {
        w.frameGeometry={x:s.geometry.x,y:s.geometry.y,width:s.geometry.width,height:s.geometry.height};
        w.keepAbove=true; w.skipTaskbar=true; w.skipSwitcher=true;
        print("phase1 ctrl placed",w.frameGeometry);
      }
    }
  }
}
workspace.windowAdded.connect(place);
for (var i=0;i<workspace.stackingOrder.length;i++) place(workspace.stackingOrder[i]);
