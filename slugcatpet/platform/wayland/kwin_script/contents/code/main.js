// SlugcatPet KWin bridge.
//
// 由 Python 后端在运行时替换占位符后写到 ~/.slugcatpet/kwin/，再用
// org.kde.KWin.Scripting.loadScript 加载。职责：
//   1. 找到 overlay 顶层窗口，钉在目标输出上并保持置顶；
//   2. 推送 overlay 实际几何、光标、活动窗口全屏状态和挡雨窗口快照；
//   3. 注册固定全局快捷键并推回每个快捷键是否注册成功。
//
// 所有坐标都是 KWin 的逻辑坐标；Python 侧再换算成 overlay-local。

var APP_ID = "@APP_ID@";
var OVERLAY_CAPTION = "@OVERLAY_CAPTION@";
var CAPTURE_CAPTION = "@CAPTURE_CAPTION@";
var TARGET_SCREEN = "@TARGET_SCREEN@";
var OVERLAY_X = @OVERLAY_X@;
var OVERLAY_Y = @OVERLAY_Y@;
var OVERLAY_W = @OVERLAY_W@;
var OVERLAY_H = @OVERLAY_H@;
var HOTKEYS = @HOTKEYS_JSON@;

var SERVICE = "@DBUS_SERVICE@";
var PATH = "@DBUS_PATH@";
var IFACE = "@DBUS_INTERFACE@";

var MIN_SIDE = 24;
var MIN_CURSOR_MS = 33;  // ~30 Hz
var OVERLAY_FOCUS_GRACE_MS = 1000;

var overlay = null;
var overlayPid = 0;
var monitored = {};
var lastFullscreen = "";
var lastWindowList = null;
var lastCursorMs = 0;
var lastActive = null;
var lastExternalActive = null;
var overlayMappedAt = 0;

function isOverlay(w) {
    if (!w) {
        return false;
    }
    if (w.caption === OVERLAY_CAPTION) {
        return true;
    }
    return w.desktopFileName === APP_ID && w.caption === OVERLAY_CAPTION;
}

function isCapture(w) {
    return !!w && w.caption === CAPTURE_CAPTION;
}

function rememberOverlay(w) {
    if (!overlay) {
        overlay = w;
        overlayPid = w.pid || 0;
    }
}

function isOwnWindow(w) {
    if (!w) {
        return true;
    }
    if (w === overlay || isOverlay(w) || isCapture(w)) {
        return true;
    }
    return overlayPid !== 0 && w.pid === overlayPid;
}

function isRestorableWindow(w) {
    // overlay 本身也可能持有键盘焦点（例如 ControlHud），不能一概排除。
    return (
        !!w &&
        !isCapture(w) &&
        !w.dock &&
        !w.desktopWindow &&
        !w.notification &&
        !w.tooltip &&
        !w.hidden &&
        !w.minimized
    );
}

function findRestorableWindow(excludeOverlay) {
    var order = workspace.stackingOrder;
    for (var i = order.length - 1; i >= 0; i--) {
        var w = order[i];
        if (isRestorableWindow(w) && !(excludeOverlay && isOverlay(w))) {
            return w;
        }
    }
    return null;
}

function rememberActive(w) {
    if (isRestorableWindow(w)) {
        lastActive = w;
        if (!isOverlay(w)) {
            lastExternalActive = w;
        }
    }
}

function restoreFocusTo(target, reason) {
    if (!target || workspace.activeWindow === target) {
        return;
    }
    try {
        workspace.activeWindow = target;
        print("slugcatpet restored focus", reason, target.caption);
    } catch (e) {
        print("slugcatpet restore focus failed", reason, String(e));
    }
}

function restoreUserFocus(w) {
    // 捕获面只是为了拿指针焦点，不能把键盘焦点从原窗口抢走。
    if (!isCapture(w)) {
        return;
    }
    var target = lastActive;
    if (!isRestorableWindow(target)) {
        target = findRestorableWindow(false);
    }
    restoreFocusTo(target, "capture");
}

function overlayJustMapped() {
    return overlayMappedAt > 0 && Date.now() - overlayMappedAt < OVERLAY_FOCUS_GRACE_MS;
}

function restoreOverlayFocus(w) {
    // 主 overlay 首次映射时不应抢走用户窗口的键盘焦点；ControlHud 打开后的
    // overlay 激活已经超出映射宽限期，会按正常焦点处理。
    if (!isOverlay(w)) {
        return;
    }
    var target = lastExternalActive;
    if (!isRestorableWindow(target) || isOverlay(target)) {
        target = findRestorableWindow(true);
    }
    restoreFocusTo(target, "overlay");
}

function sendGeometry(w) {
    var r = w && w.frameGeometry ? w.frameGeometry : null;
    if (r === null) {
        r = { x: OVERLAY_X, y: OVERLAY_Y, width: OVERLAY_W, height: OVERLAY_H };
    }
    callDBus(SERVICE, PATH, IFACE, "OverlayGeometryChanged",
             Math.round(r.x), Math.round(r.y),
             Math.round(r.width), Math.round(r.height));
}

function applyOverlay(w) {
    if (!isOverlay(w)) {
        return;
    }
    rememberOverlay(w);
    var g = Object.assign({}, w.frameGeometry);
    g.x = OVERLAY_X;
    g.y = OVERLAY_Y;
    g.width = OVERLAY_W;
    g.height = OVERLAY_H;
    w.frameGeometry = g;
    w.keepAbove = true;
    w.skipTaskbar = true;
    w.skipSwitcher = true;
    sendGeometry(w);
}

function applyCapture(w) {
    if (!isCapture(w)) {
        return;
    }
    var g = Object.assign({}, w.frameGeometry);
    g.x = OVERLAY_X;
    g.y = OVERLAY_Y;
    g.width = OVERLAY_W;
    g.height = OVERLAY_H;
    w.frameGeometry = g;
    w.keepAbove = true;
    w.skipTaskbar = true;
    w.skipSwitcher = true;
}

function windowKey(w) {
    try {
        return String(w.internalId);
    } catch (e) {
        return String(w.stackingOrder);
    }
}

function connectSignal(w, name, callback) {
    try {
        var signal = w[name];
        if (signal && signal.connect) {
            signal.connect(callback);
        }
    } catch (e) {
        // 某些窗口类型没有该信号；忽略即可。
    }
}

function monitorWindow(w) {
    if (!w) {
        return;
    }
    var key = windowKey(w);
    if (monitored[key]) {
        return;
    }
    monitored[key] = true;
    var refresh = function () {
        if (isOverlay(w)) {
            // frameGeometry 的写入是异步的；立刻 sendGeometry 可能还是旧值，
            // 必须等 KWin 真正改完后再推一次，否则 Python 的 origin 会落后一屏。
            sendGeometry(w);
        }
        sendWindowList();
        if (workspace.activeWindow === w) {
            sendFullscreen();
        }
    };
    connectSignal(w, "frameGeometryChanged", refresh);
    connectSignal(w, "minimizedChanged", refresh);
    connectSignal(w, "hiddenChanged", refresh);
    connectSignal(w, "skipTaskbarChanged", refresh);
    connectSignal(w, "fullScreenChanged", refresh);
    connectSignal(w, "desktopsChanged", refresh);
    connectSignal(w, "activitiesChanged", refresh);
    connectSignal(w, "outputChanged", refresh);
    connectSignal(w, "captionChanged", refresh);
    connectSignal(w, "closed", function () {
        delete monitored[key];
        if (w === overlay) {
            overlay = null;
            overlayPid = 0;
        }
        sendWindowList();
        sendFullscreen();
    });
}

function onCurrentDesktop(w) {
    try {
        return w.onAllDesktops || !w.desktops || w.desktops.length === 0
            || w.desktops.indexOf(workspace.currentDesktop) >= 0;
    } catch (e) {
        return true;
    }
}

function onCurrentActivity(w) {
    try {
        return !w.activities || w.activities.length === 0
            || w.activities.indexOf(workspace.currentActivity) >= 0;
    } catch (e) {
        return true;
    }
}

function isShelter(w) {
    try {
        if (!w || isOwnWindow(w)) {
            return false;
        }
        if (!w.managed || !w.normalWindow || w.deleted || w.minimized || w.hidden) {
            return false;
        }
        if (w.skipTaskbar || w.dock || w.desktopWindow || w.specialWindow
                || w.tooltip || w.notification || w.criticalNotification
                || w.onScreenDisplay || w.popupMenu || w.dropdownMenu
                || w.comboBox || w.menu || w.splash || w.utility) {
            return false;
        }
        if (TARGET_SCREEN && w.output && String(w.output.name) !== TARGET_SCREEN) {
            return false;
        }
        if (!onCurrentDesktop(w) || !onCurrentActivity(w)) {
            return false;
        }
        var g = w.frameGeometry;
        return g && g.width >= MIN_SIDE && g.height >= MIN_SIDE;
    } catch (e) {
        return false;
    }
}

function sendWindowList() {
    var list = [];
    var order = workspace.stackingOrder;
    for (var i = 0; i < order.length; i++) {
        var w = order[i];
        try {
            if (!isShelter(w)) {
                continue;
            }
            var g = w.frameGeometry;
            list.push({
                caption: String(w.caption),
                resourceClass: String(w.resourceClass),
                output: w.output ? String(w.output.name) : "",
                x: Math.round(g.x),
                y: Math.round(g.y),
                w: Math.round(g.width),
                h: Math.round(g.height),
                fullScreen: !!w.fullScreen,
                pid: w.pid
            });
        } catch (e) {
            // 窗口正在销毁时属性可能抛异常，跳过。
        }
    }
    var payload = JSON.stringify(list);
    if (payload === lastWindowList) {
        return;
    }
    lastWindowList = payload;
    callDBus(SERVICE, PATH, IFACE, "WindowListChanged", payload);
}

function sendFullscreen() {
    var w = workspace.activeWindow;
    var full = false;
    var x = 0;
    var y = 0;
    var width = 0;
    var height = 0;
    try {
        if (w && !isOwnWindow(w) && w.fullScreen) {
            var g = w.frameGeometry;
            full = true;
            x = Math.round(g.x);
            y = Math.round(g.y);
            width = Math.round(g.width);
            height = Math.round(g.height);
        }
    } catch (e) {
        full = false;
    }
    var payload = full + ":" + x + ":" + y + ":" + width + ":" + height;
    if (payload === lastFullscreen) {
        return;
    }
    lastFullscreen = payload;
    callDBus(SERVICE, PATH, IFACE, "FullscreenChanged", full, x, y, width, height);
}

function sendCursor() {
    var p = workspace.cursorPos;
    var now = Date.now();
    if (lastCursorMs && now - lastCursorMs < MIN_CURSOR_MS) {
        return;
    }
    lastCursorMs = now;
    callDBus(SERVICE, PATH, IFACE, "CursorMoved",
             Math.round(p.x), Math.round(p.y));
}

function scan() {
    var order = workspace.stackingOrder;
    for (var i = 0; i < order.length; i++) {
        var w = order[i];
        applyOverlay(w);
        applyCapture(w);
        monitorWindow(w);
    }
    sendWindowList();
    sendFullscreen();
    sendCursor();
}

function hotkeyCallback(id) {
    return function () {
        callDBus(SERVICE, PATH, IFACE, "HotkeyPressed", id);
    };
}

function registerHotkeys() {
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
}

workspace.windowAdded.connect(function (w) {
    applyOverlay(w);
    applyCapture(w);
    if (isOverlay(w)) {
        overlayMappedAt = Date.now();
        if (workspace.activeWindow === w) {
            restoreOverlayFocus(w);
        }
        if (lastActive === w) {
            lastActive = lastExternalActive;
        }
    }
    restoreUserFocus(w);
    monitorWindow(w);
    sendWindowList();
    sendFullscreen();
});
workspace.windowRemoved.connect(function (w) {
    try {
        delete monitored[windowKey(w)];
    } catch (e) {
    }
    if (w === overlay) {
        overlay = null;
        overlayPid = 0;
        overlayMappedAt = 0;
    }
    if (w === lastExternalActive) {
        lastExternalActive = null;
    }
    if (w === lastActive) {
        lastActive = lastExternalActive;
    }
    sendWindowList();
    sendFullscreen();
});
workspace.windowActivated.connect(function (w) {
    var overlayMapping = isOverlay(w) && overlayJustMapped();
    applyOverlay(w);
    applyCapture(w);
    if (overlayMapping) {
        if (lastActive === w) {
            lastActive = lastExternalActive;
        }
        restoreOverlayFocus(w);
    } else {
        rememberActive(w);
    }
    restoreUserFocus(w);
    sendFullscreen();
});
workspace.currentDesktopChanged.connect(function () {
    sendWindowList();
    sendFullscreen();
});
workspace.currentActivityChanged.connect(function () {
    sendWindowList();
    sendFullscreen();
});
workspace.screensChanged.connect(function () {
    scan();
});
workspace.virtualScreenGeometryChanged.connect(function () {
    scan();
});
workspace.cursorPosChanged.connect(sendCursor);

lastActive = workspace.activeWindow;
if (!isRestorableWindow(lastActive)) {
    lastActive = findRestorableWindow(false);
}
lastExternalActive = isRestorableWindow(lastActive) && !isOverlay(lastActive)
    ? lastActive
    : findRestorableWindow(true);
scan();
if (HOTKEYS.length > 0) {
    registerHotkeys();
}
print("slugcatpet target", TARGET_SCREEN, "overlay", OVERLAY_W + "x" + OVERLAY_H);
callDBus(SERVICE, PATH, IFACE, "Log", "script loaded");
