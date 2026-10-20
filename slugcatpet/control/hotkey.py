"""全局热键注册和分发：Windows 走 RegisterHotKey，Wayland 由 KWin 脚本转发。"""

from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, Signal

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000
VK_ESCAPE = 0x1B
VK_RIGHT = 0x27

HK_ABORT, HK_QUIT, HK_HUD, HK_PLACE_ESC, HK_FREEZE, HK_STEP, HK_STEP10 = 1, 2, 3, 4, 5, 6, 7
_CA = MOD_CONTROL | MOD_ALT
# 常驻热键：id → (修饰键, 虚拟键码, 文案键)，按键位弹窗里的顺序
GLOBAL_KEYS = {
    HK_FREEZE: (_CA, 0x50, "kb_freeze"),
    HK_HUD: (_CA, 0x48, "kb_hud"),
    HK_ABORT: (_CA, 0x51, "kb_abort"),
    HK_QUIT: (_CA, 0x58, "kb_quit"),
}
# 只在定格时注册的热键
FROZEN_KEYS = {
    HK_STEP: (_CA, VK_RIGHT, "kb_step"),
    HK_STEP10: (_CA | MOD_SHIFT, VK_RIGHT, "kb_step10"),
}
_PROBE_ID = 0xBFFF


def combo_text(mods: int, vk: int) -> str:
    """组合键的显示文本，如 Ctrl+Alt+P。"""
    parts = [
        n
        for m, n in ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))
        if mods & m
    ]
    parts.append("→" if vk == VK_RIGHT else chr(vk))
    return "+".join(parts)


def key_name(vk: int) -> str:
    """把虚拟键码转成 KWin 快捷键使用的按键名。"""
    if vk == VK_RIGHT:
        return "Right"
    if vk == VK_ESCAPE:
        return "Escape"
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    return f"0x{vk:X}"


def shortcut_sequence(mods: int, vk: int) -> str:
    """组合键的 KWin 写法，如 Ctrl+Alt+P。"""
    parts = [
        n
        for m, n in ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Meta"))
        if mods & m
    ]
    parts.append(key_name(vk))
    return "+".join(parts)


def qt_key_code(mods: int, vk: int) -> int:
    """KGlobalAccel 使用的 Qt 组合键整数，用于检查快捷键是否真的抢到。"""
    code = vk
    if vk == VK_RIGHT:
        code = Qt.Key.Key_Right.value
    elif vk == VK_ESCAPE:
        code = Qt.Key.Key_Escape.value
    for mod, qt_mod in (
        (MOD_CONTROL, Qt.KeyboardModifier.ControlModifier),
        (MOD_ALT, Qt.KeyboardModifier.AltModifier),
        (MOD_SHIFT, Qt.KeyboardModifier.ShiftModifier),
        (MOD_WIN, Qt.KeyboardModifier.MetaModifier),
    ):
        if mods & mod:
            code |= qt_mod.value
    return code


_IS_WIN = sys.platform == "win32"
if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32


class _NativeHotkeys(QAbstractNativeEventFilter):
    """原生消息过滤器：收到 WM_HOTKEY 时把热键 id 交给回调。"""

    def __init__(self, on_hotkey):
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, eventType, message):
        # PySide6 约定返回 (handled: bool, result: int)
        if _IS_WIN and eventType == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                self._on_hotkey(int(msg.wParam))
        return False, 0


class HotkeyFilter(QObject):
    """收到热键时发 triggered(id)。用 install 装到 QApplication 上，退出前要 uninstall。

    Windows 走 ``RegisterHotKey``；Wayland/KWin 下脚本已经注册了同一批
    shortcut，这里只负责维护“当前有效的 id”并过滤回调。
    """

    triggered = Signal(int)

    def __init__(self, backend=None):
        super().__init__()
        self._ids: list[int] = []
        self._backend = backend
        self._backend_conn = None
        self._native = _NativeHotkeys(self._dispatch)
        if backend is not None and not _IS_WIN:
            signal = getattr(backend, "hotkey_pressed", None)
            if signal is not None:
                self._backend_conn = signal.connect(self._dispatch)

    def install(self, app) -> None:
        # 非 Windows 没有原生 WM_HOTKEY；保留调用是为了统一生命周期。
        if _IS_WIN:
            app.installNativeEventFilter(self._native)

    def uninstall(self, app) -> None:
        if _IS_WIN:
            app.removeNativeEventFilter(self._native)

    def _dispatch(self, hk_id: int) -> None:
        if hk_id in self._ids:
            self.triggered.emit(int(hk_id))

    def register(self, hk_id: int, mods: int, vk: int) -> bool:
        """组合键被占返回 False。Wayland 下由 KWin 脚本统一注册。"""
        if not _IS_WIN:
            ok = bool(self._backend is not None and self._backend.register_hotkey(hk_id, mods, vk))
            if ok and hk_id not in self._ids:
                self._ids.append(hk_id)
            return ok
        if _user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
            self._ids.append(hk_id)
            return True
        return False

    def registered(self, hk_id: int) -> bool:
        return hk_id in self._ids

    def available(self, mods: int, vk: int) -> bool:
        """试注册一次看组合键有没有被占，不保留。"""
        if not _IS_WIN:
            status = getattr(self._backend, "hotkey_available", None)
            return bool(status(mods, vk)) if callable(status) else False
        if _user32.RegisterHotKey(None, _PROBE_ID, mods | MOD_NOREPEAT, vk):
            _user32.UnregisterHotKey(None, _PROBE_ID)
            return True
        return False

    def unregister(self, hk_id: int) -> None:
        if hk_id not in self._ids:
            return
        if _IS_WIN:
            _user32.UnregisterHotKey(None, hk_id)
        self._ids.remove(hk_id)

    def unregister_all(self) -> None:
        if _IS_WIN:
            for hk_id in self._ids:
                _user32.UnregisterHotKey(None, hk_id)
        self._ids.clear()
