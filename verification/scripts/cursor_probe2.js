workspace.cursorPosChanged.connect(function () {
    print("CURSORPROBE2 moved", workspace.cursorPos.x, workspace.cursorPos.y);
});
print("CURSORPROBE2 start", workspace.cursorPos.x, workspace.cursorPos.y);
