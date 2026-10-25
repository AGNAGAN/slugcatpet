// SlugcatPet KWin 全局快捷键脚本。
//
// 与几何/光标脚本分开加载：几何脚本会随输出和 overlay 尺寸反复重载，
// 而 KGlobalAccel 对已经存在的动作不会再绑定回调。快捷键脚本只在应用
// 启动或键位改变时重载。

var HOTKEYS = @HOTKEYS_JSON@;
var SERVICE = "@DBUS_SERVICE@";
var PATH = "@DBUS_PATH@";
var IFACE = "@DBUS_INTERFACE@";

function hotkeyCallback(id) {
    return function () {
        callDBus(SERVICE, PATH, IFACE, "HotkeyPressed", id);
    };
}

var status = [];
for (var i = 0; i < HOTKEYS.length; i++) {
    var h = HOTKEYS[i];
    var ok = false;
    try {
        ok = registerShortcut(h.action, h.text, h.key,
                              hotkeyCallback(h.id)) !== false;
    } catch (e) {
        print("slugcatpet shortcut failed", h.id, h.key, String(e));
    }
    status.push({ id: h.id, key: h.key, ok: ok });
}
callDBus(SERVICE, PATH, IFACE, "HotkeyStatus", JSON.stringify(status));
print("slugcatpet hotkeys registered", status.length);
