var p = workspace.cursorPos;
print("WINAT cursor", p.x, p.y, "len", workspace.windowAt.length);
try {
    var a = workspace.windowAt(p);
    print("WINAT one", typeof a, Object.prototype.toString.call(a), a ? a.caption : a);
    if (a && a.length !== undefined) {
        for (var i = 0; i < a.length; i++) {
            print("WINAT one", i, a[i] ? a[i].caption : a[i]);
        }
    }
} catch (e) {
    print("WINAT one-error", String(e));
}
try {
    var b = workspace.windowAt(p, 5);
    print("WINAT many", typeof b, Object.prototype.toString.call(b), b ? b.caption : b);
    if (b && b.length !== undefined) {
        for (var j = 0; j < b.length; j++) {
            print("WINAT many", j, b[j] ? b[j].caption : b[j]);
        }
    }
} catch (e) {
    print("WINAT many-error", String(e));
}
