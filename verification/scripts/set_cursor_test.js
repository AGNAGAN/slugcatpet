print("before", workspace.cursorPos);
try {
    workspace.cursorPos = { x: 700, y: 450 };
    print("after assign", workspace.cursorPos);
} catch (e) {
    print("assign failed", e);
}
