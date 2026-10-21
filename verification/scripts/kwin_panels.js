print("panels count", workspace.panels.length);
for (var i = 0; i < workspace.panels.length; i++) {
    var p = workspace.panels[i];
    print("panel", p.caption, p.resourceClass, p.frameGeometry, "output", p.output ? p.output.name : "none", "hidden", p.hidden);
}
print("desktops", workspace.desktops.length, "current", workspace.currentDesktop.name);
