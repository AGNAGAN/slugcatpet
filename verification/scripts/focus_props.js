var w = workspace.activeWindow;
print("FOCUSPROBE ws-props", Object.getOwnPropertyNames(workspace).join(","));
print("FOCUSPROBE win-props", w ? Object.getOwnPropertyNames(w).join(",") : "none");
if (w) {
    try {
        print("FOCUSPROBE activate", typeof w.activate, typeof w.activateWindow, typeof w.requestActivate);
    } catch (e) {
        print("FOCUSPROBE activate-error", String(e));
    }
}
