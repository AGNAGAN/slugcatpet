"""全局热键注册和分发：Windows 走 RegisterHotKey，Wayland 由 KWin 脚本转发。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, Signal

from .._paths import user_dir

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000
VK_ESCAPE = 0x1B
VK_RIGHT = 0x27

HK_ABORT, HK_QUIT, HK_HUD, HK_PLACE_ESC, HK_FREEZE, HK_STEP, HK_STEP10, HK_RAIN = 1, 2, 3, 4, 5, 6, 7, 8
HK_MEOW = 9
_CA = MOD_CONTROL | MOD_ALT
# 常驻热键：id → 动作，按键位弹窗里的顺序；文案键为 kb_<动作>
GLOBAL_KEYS = {
    HK_MEOW: "meow_hover",
    HK_FREEZE: "freeze",
    HK_HUD: "hud",
    HK_RAIN: "rain",
    HK_ABORT: "abort",
    HK_QUIT: "quit",
}
# 只在定格时注册的热键
FROZEN_KEYS = {HK_STEP: "step", HK_STEP10: "step10"}
DEFAULT_HOTKEYS = {
    "meow_hover": (MOD_ALT, 0x4D),
    "freeze": (_CA, 0x50),
    "hud": (_CA, 0x48),
    "rain": (_CA, 0x52),
    "abort": (_CA, 0x51),
    "quit": (_CA, 0x58),
    "step": (_CA, VK_RIGHT),
    "step10": (_CA | MOD_SHIFT, VK_RIGHT),
}
HOTKEY_ACTIONS = tuple(DEFAULT_HOTKEYS)
_PROBE_ID = 0xBFFF

_MOD_NAMES = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
_VK_NAMES = {
    **{0x30 + i: str(i) for i in range(10)},
    **{0x41 + i: chr(0x41 + i) for i in range(26)},
    **{0x60 + i: f"Num{i}" for i in range(10)},
    **{0x70 + i: f"F{i + 1}" for i in range(24)},
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x13: "Pause",
    0x20: "Space",
    0x21: "PgUp",
    0x22: "PgDn",
    0x23: "End",
    0x24: "Home",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0x2D: "Insert",
    0x2E: "Delete",
    0xBA: ";",
    0xBB: "=",
    0xBC: ",",
    0xBD: "-",
    0xBE: ".",
    0xBF: "/",
    0xC0: "`",
    0xDB: "[",
    0xDC: "\\",
    0xDD: "]",
    0xDE: "'",
}
_NAME_VK = {n: vk for vk, n in _VK_NAMES.items()}
_ARROWS = {"Left": "←", "Up": "↑", "Right": "→", "Down": "↓"}


def combo_name(mods: int, vk: int) -> str:
    """存档用的组合键文本，如 Ctrl+Alt+Right；vk 为 0 时只有修饰键。"""
    parts = [n for n, m in _MOD_NAMES if mods & m]
    if vk:
        parts.append(_VK_NAMES.get(vk, f"0x{vk:02X}"))
    return "+".join(parts)


def combo_text(mods: int, vk: int) -> str:
    """显示用的组合键文本，方向键画成箭头。"""
    name = _VK_NAMES.get(vk, "")
    return combo_name(mods, 0 if name in _ARROWS else vk) + ("+" + _ARROWS[name] if name in _ARROWS else "")


def parse_combo(text) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    *mod_parts, key = text.split("+")
    mods = 0
    for part in mod_parts:
        m = dict(_MOD_NAMES).get(part)
        if m is None:
            return None
        mods |= m
    vk = _NAME_VK.get(key)
    return None if vk is None else (mods, vk)


def key_ok(vk: int) -> bool:
    return vk in _VK_NAMES


def mods_ok(mods: int) -> bool:
    """要带 Ctrl、Alt 或 Win，否则这个键在所有程序里都会被吞掉。"""
    return bool(mods & (MOD_CONTROL | MOD_ALT | MOD_WIN))


def _default_path() -> Path:
    return user_dir() / "hotkeys.json"


def load_hotkeys(path=None) -> dict[str, tuple[int, int]]:
    """读动作 → (修饰键, 虚拟键码)；文件缺失、损坏或某项无效时那项用默认。"""
    keys = dict(DEFAULT_HOTKEYS)
    p = Path(path) if path is not None else _default_path()
    try:
        loaded = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return keys
    if isinstance(loaded, dict):
        for action in HOTKEY_ACTIONS:
            c = parse_combo(loaded.get(action))
            if c is not None and mods_ok(c[0]):
                keys[action] = c
    return keys


def save_hotkeys(keys: dict[str, tuple[int, int]], path=None) -> bool:
    p = Path(path) if path is not None else _default_path()
    data = {a: combo_name(*keys.get(a, DEFAULT_HOTKEYS[a])) for a in HOTKEY_ACTIONS}
    try:
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        return False
    return True


def key_name(vk: int) -> str:
    """把虚拟键码转成 KWin 快捷键使用的按键名。"""
    return _VK_NAMES.get(vk, f"0x{vk:X}")


def shortcut_sequence(mods: int, vk: int) -> str:
    """组合键的 KWin 写法，如 Ctrl+Alt+P。"""
    parts = [
        n
        for m, n in (
            (MOD_CONTROL, "Ctrl"),
            (MOD_ALT, "Alt"),
            (MOD_SHIFT, "Shift"),
            (MOD_WIN, "Meta"),
        )
        if mods & m
    ]
    parts.append(key_name(vk))
    return "+".join(parts)


def qt_key_code(mods: int, vk: int) -> int:
    """KGlobalAccel 使用的 Qt 组合键整数，用于检查快捷键是否真的抢到。"""
    special = {
        0x08: Qt.Key.Key_Backspace,
        0x09: Qt.Key.Key_Tab,
        0x0D: Qt.Key.Key_Return,
        0x13: Qt.Key.Key_Pause,
        0x20: Qt.Key.Key_Space,
        0x21: Qt.Key.Key_PageUp,
        0x22: Qt.Key.Key_PageDown,
        0x23: Qt.Key.Key_End,
        0x24: Qt.Key.Key_Home,
        0x25: Qt.Key.Key_Left,
        0x26: Qt.Key.Key_Up,
        0x27: Qt.Key.Key_Right,
        0x28: Qt.Key.Key_Down,
        0x2D: Qt.Key.Key_Insert,
        0x2E: Qt.Key.Key_Delete,
    }
    if 0x70 <= vk <= 0x87:
        code = Qt.Key.Key_F1.value + vk - 0x70
    else:
        code = special.get(vk, vk).value if vk in special else vk
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


def key_down(vk: int) -> bool:
    """这个键现在是否按着（WM_HOTKEY 只报按下，松开要自己查）。"""
    return _IS_WIN and bool(_user32.GetAsyncKeyState(vk) & 0x8000)


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
    shortcut，这里只负责维护“当前有效的 id”、过滤回调并在录键时暂停。
    """

    triggered = Signal(int)
    released = Signal(int)

    def __init__(self, backend=None):
        super().__init__()
        self._ids: dict[int, tuple[int, int]] = {}
        self._suspended: dict[int, tuple[int, int]] = {}
        self._down: set[int] = set()
        self._backend = backend
        self._backend_pressed = None
        self._backend_released = None
        self._native = _NativeHotkeys(self._dispatch)
        if backend is not None and not _IS_WIN:
            pressed = getattr(backend, "hotkey_pressed", None)
            if pressed is not None:
                self._backend_pressed = pressed.connect(self._dispatch)
            released = getattr(backend, "hotkey_released", None)
            if released is not None:
                self._backend_released = released.connect(self._release)

    def install(self, app) -> None:
        # 非 Windows 没有原生 WM_HOTKEY；保留调用是为了统一生命周期。
        if _IS_WIN:
            app.installNativeEventFilter(self._native)

    def uninstall(self, app) -> None:
        if _IS_WIN:
            app.removeNativeEventFilter(self._native)

    def _dispatch(self, hk_id: int) -> None:
        hk_id = int(hk_id)
        if hk_id in self._ids:
            self._down.add(hk_id)
            self.triggered.emit(hk_id)

    def _release(self, hk_id: int) -> None:
        hk_id = int(hk_id)
        if hk_id in self._ids:
            self._down.discard(hk_id)
            self.released.emit(hk_id)

    def is_down(self, hk_id: int, vk: int = 0) -> bool:
        """热键当前是否仍按着；Wayland 靠 KGlobalAccel 的松开信号。"""
        if _IS_WIN:
            return key_down(vk) if vk else hk_id in self._down
        return hk_id in self._down

    def register(self, hk_id: int, mods: int, vk: int) -> bool:
        """组合键被占返回 False。Wayland 下由 KWin 脚本统一注册。"""
        hk_id = int(hk_id)
        if not _IS_WIN:
            ok = bool(self._backend is not None and self._backend.register_hotkey(hk_id, mods, vk))
            if ok:
                self._ids[hk_id] = (mods, vk)
                self._suspended.pop(hk_id, None)
            return ok
        if _user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
            self._ids[hk_id] = (mods, vk)
            self._suspended.pop(hk_id, None)
            return True
        return False

    def registered(self, hk_id: int) -> bool:
        return hk_id in self._ids or hk_id in self._suspended

    def owns(self, mods: int, vk: int) -> bool:
        """这个组合键是不是自己注册着（含暂停中的）。"""
        return (mods, vk) in self._ids.values() or (mods, vk) in self._suspended.values()

    def available(self, mods: int, vk: int) -> bool:
        """试注册一次看组合键有没有被占，不保留。"""
        if not _IS_WIN:
            status = getattr(self._backend, "hotkey_available", None)
            if callable(status):
                return bool(status(mods, vk))
            # 没有可查询的 KWin 后端时不把键帽标红；保存后会由脚本报告冲突。
            return True
        if _user32.RegisterHotKey(None, _PROBE_ID, mods | MOD_NOREPEAT, vk):
            _user32.UnregisterHotKey(None, _PROBE_ID)
            return True
        return False

    def unregister(self, hk_id: int) -> None:
        hk_id = int(hk_id)
        self._down.discard(hk_id)
        self._suspended.pop(hk_id, None)
        if _IS_WIN and hk_id in self._ids:
            _user32.UnregisterHotKey(None, hk_id)
        self._ids.pop(hk_id, None)

    def suspend(self) -> None:
        """暂时摘掉，好让录键时按下的组合键送到窗口；resume 挂回。"""
        pending = dict(self._ids)
        if _IS_WIN:
            for hk_id in pending:
                _user32.UnregisterHotKey(None, hk_id)
        else:
            fn = getattr(self._backend, "suspend_hotkeys", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        self._suspended.update(pending)
        self._ids.clear()
        self._down.clear()

    def resume(self) -> None:
        pending, self._suspended = self._suspended, {}
        if _IS_WIN:
            for hk_id, (mods, vk) in pending.items():
                self.register(hk_id, mods, vk)
            return
        self._ids.update(pending)
        fn = getattr(self._backend, "resume_hotkeys", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def apply(self) -> bool:
        """把当前 hotkeys.json 重新应用到 KWin 脚本；Windows 无需处理。"""
        fn = getattr(self._backend, "refresh_hotkeys", None)
        return bool(fn()) if callable(fn) else True

    def unregister_all(self) -> None:
        self._suspended.clear()
        self._down.clear()
        if _IS_WIN:
            for hk_id in self._ids:
                _user32.UnregisterHotKey(None, hk_id)
        else:
            fn = getattr(self._backend, "resume_hotkeys", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        self._ids.clear()
