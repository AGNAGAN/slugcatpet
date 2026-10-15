"""Windows 全局热键的注册和分发，其他平台不生效。"""

from __future__ import annotations
import sys
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

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
    """收到热键时发 triggered(id)。用 install 装到 QApplication 上，退出前要 uninstall。"""

    triggered = Signal(int)

    def __init__(self):
        super().__init__()
        self._ids: list[int] = []
        self._native = _NativeHotkeys(self.triggered.emit)

    def install(self, app) -> None:
        app.installNativeEventFilter(self._native)

    def uninstall(self, app) -> None:
        app.removeNativeEventFilter(self._native)

    def register(self, hk_id: int, mods: int, vk: int) -> bool:
        """组合键被占返回 False。"""
        if not _IS_WIN:
            return False
        if _user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
            self._ids.append(hk_id)
            return True
        return False

    def registered(self, hk_id: int) -> bool:
        return hk_id in self._ids

    def available(self, mods: int, vk: int) -> bool:
        """试注册一次看组合键有没有被占，不保留。"""
        if not _IS_WIN:
            return False
        if _user32.RegisterHotKey(None, _PROBE_ID, mods | MOD_NOREPEAT, vk):
            _user32.UnregisterHotKey(None, _PROBE_ID)
            return True
        return False

    def unregister(self, hk_id: int) -> None:
        if not _IS_WIN or hk_id not in self._ids:
            return
        _user32.UnregisterHotKey(None, hk_id)
        self._ids.remove(hk_id)

    def unregister_all(self) -> None:
        if not _IS_WIN:
            return
        for hk_id in self._ids:
            _user32.UnregisterHotKey(None, hk_id)
        self._ids.clear()
