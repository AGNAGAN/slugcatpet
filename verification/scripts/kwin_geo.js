print("virtual", workspace.virtualScreenGeometry, "size", workspace.virtualScreenSize);
for (var i = 0; i < workspace.screens.length; i++) {
    var s = workspace.screens[i];
    print("screen", s.name, s.geometry, s.devicePixelRatio);
}
print("activeScreen", workspace.activeScreen.name, workspace.activeScreen.geometry);
