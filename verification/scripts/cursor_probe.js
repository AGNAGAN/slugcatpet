print("CURSORPROBE start", workspace.cursorPos.x, workspace.cursorPos.y);
try {
    var p = workspace.cursorPos;
    workspace.cursorPos = { x: p.x + 1, y: p.y };
    print("CURSORPROBE set-ok", workspace.cursorPos.x, workspace.cursorPos.y);
} catch (e) {
    print("CURSORPROBE set-error", String(e));
}
try {
    print("CURSORPROBE names", Object.getOwnPropertyNames(workspace).join(","));
} catch (e) {
    print("CURSORPROBE names-error", String(e));
}
