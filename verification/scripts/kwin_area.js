for (var i = 0; i < workspace.screens.length; i++) {
    var s = workspace.screens[i];
    print("area screen", s.name, s.geometry,
          "work", workspace.clientArea(KWin.WorkArea, s, workspace.currentDesktop),
          "full", workspace.clientArea(KWin.FullArea, s, workspace.currentDesktop));
}
