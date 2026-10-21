for (var i = 0; i < workspace.stackingOrder.length; i++) {
    var w = workspace.stackingOrder[i];
    print("ALLWIN", i, JSON.stringify({
        caption: w.caption,
        resourceClass: w.resourceClass,
        pid: w.pid,
        layer: w.layer,
        keepAbove: w.keepAbove,
        active: w.active,
        hidden: w.hidden,
        minimized: w.minimized,
        skipTaskbar: w.skipTaskbar,
        windowType: w.windowType,
        popupWindow: w.popupWindow,
        wantsInput: w.wantsInput,
        x: w.x, y: w.y, width: w.width, height: w.height,
        desktop: w.desktopFileName
    }));
}
