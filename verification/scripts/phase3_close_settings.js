for (var i = 0; i < workspace.stackingOrder.length; i++) {
    var w = workspace.stackingOrder[i];
    if (w.caption === "设置") {
        w.closeWindow();
    }
}
