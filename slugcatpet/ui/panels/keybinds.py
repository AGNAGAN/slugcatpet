"""键位弹窗：全局热键、定格热键和手动控制键都点键帽录入新键，同组冲突时互换，完成才保存。"""

from __future__ import annotations
import sys
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence

from ...i18n import t
from ...control.hotkey import (
    DEFAULT_HOTKEYS,
    FROZEN_KEYS,
    GLOBAL_KEYS,
    HOTKEY_ACTIONS,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    combo_text,
    key_ok,
    load_hotkeys,
    mods_ok,
    save_hotkeys,
)
from ...control.keymap import ACTIONS, DEFAULT_KEYBINDS, key_name, load_key_names, save_key_names
from ..theme import qss
from ..theme.palette import TEXT_DIM
from ..widgets.dialogs import CardDialog
from ..widgets.iconkit import ui_icon
from ..widgets.tips import install as install_tip

_CONTROL_ORDER = ("up", "down", "left", "right", "jump", "grab", "throw", "meow", "hold")
_ARROWS = {"Up": "↑", "Down": "↓", "Left": "←", "Right": "→"}
_SHORT = {"Control": "Ctrl", "Return": "Enter", "CapsLock": "Caps"}
_MOD_KEYS = frozenset(
    int(k) for k in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta, Qt.Key.Key_AltGr)
)
_QT_MODS = (
    (Qt.KeyboardModifier.ControlModifier, MOD_CONTROL),
    (Qt.KeyboardModifier.AltModifier, MOD_ALT),
    (Qt.KeyboardModifier.ShiftModifier, MOD_SHIFT),
    (Qt.KeyboardModifier.MetaModifier, MOD_WIN),
)
FLASH_MS = 700


def key_label(name: str) -> str:
    """键名的显示文本。"""
    if name in _ARROWS:
        return _ARROWS[name]
    if name == "Space":
        return t("key_space")
    if name in _SHORT:
        return _SHORT[name]
    key = getattr(Qt.Key, "Key_" + name, None)
    text = QKeySequence(int(key)).toString(QKeySequence.SequenceFormat.NativeText) if key else ""
    return (text.upper() if len(text) == 1 else text) or name


def _win_mods(qt_mods) -> int:
    return sum(m for q, m in _QT_MODS if qt_mods & q)


def _set_prop(w, prop, on):
    w.setProperty(prop, on)
    w.style().unpolish(w)
    w.style().polish(w)


class _KeyCap(QPushButton):
    """键帽按钮：录入中吞下按键，Esc 或失焦发出 cancelled。
    单键模式按下即发 captured(Qt 键)；组合键模式按住修饰键时发 held(修饰键)，按下主键发 captured((修饰键, 虚拟键码))。"""

    captured = Signal(object)
    held = Signal(int)
    cancelled = Signal()

    def __init__(self, combo=False):
        self.listening = False
        self.combo = combo
        super().__init__()
        self.setObjectName("keyCap")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_listening(self, on: bool):
        self.listening = on
        _set_prop(self, "listening", on)

    def event(self, e):
        if self.listening:
            et = e.type()
            if et == QEvent.Type.ShortcutOverride:
                e.accept()
                return True
            if et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                key = int(e.key())
                if self.combo and key in _MOD_KEYS:
                    self.held.emit(_win_mods(QGuiApplication.queryKeyboardModifiers()))
                elif et == QEvent.Type.KeyPress and not e.isAutoRepeat():
                    if key == int(Qt.Key.Key_Escape):
                        self.cancelled.emit()
                    elif self.combo:
                        self.captured.emit((_win_mods(e.modifiers()), int(e.nativeVirtualKey())))
                    else:
                        self.captured.emit(key)
                return True
        return super().event(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        if self.listening:
            self.cancelled.emit()


class KeybindDialog(CardDialog):
    def __init__(self, on_saved, hotkeys=None, parent=None):
        super().__init__(t("settings_keybinds"), parent, width=360)
        self._card.setStyleSheet(qss.KEYBINDS)
        self._on_saved = on_saved
        self._hotkeys = hotkeys if sys.platform == "win32" else None
        self._saved = load_key_names()
        self._names = dict(self._saved)
        self._saved_combos = load_hotkeys()
        self._combos = dict(self._saved_combos)
        self._caps = {}
        self._resets = {}
        self._active = None  # 正在录入的动作
        self._flashing = []
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._unflash)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        hint = QLabel(t("kb_hint"))
        hint.setObjectName("kbHint")
        hint.setWordWrap(True)
        grid.addWidget(hint, 0, 0, 1, 3)
        r = 1
        for head, actions in (
            ("kb_group_global", GLOBAL_KEYS.values()),
            ("kb_group_frozen", FROZEN_KEYS.values()),
            ("kb_group_control", _CONTROL_ORDER),
        ):
            r = self._group_head(grid, r, head)
            for a in actions:
                self._build_row(grid, r, a)
                r += 1
        grid.setColumnStretch(0, 1)
        self.body.addLayout(grid)

        self._status = QLabel("")
        self._status.setObjectName("kbStatus")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(self._status.fontMetrics().height() * 2)
        self._status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.body.addWidget(self._status)

        self._reset_all = QPushButton(t("kb_reset_all"))
        self._reset_all.setObjectName("btnGhost")
        self._reset_all.clicked.connect(self._on_reset_all)
        self._btn_row.insertWidget(0, self._reset_all)
        cancel = self.add_button(t("settings_cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        ok = self.add_button(t("skin_done"), "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        self._refresh()

    @staticmethod
    def _group_head(grid, r, key):
        grid.setRowMinimumHeight(r, 6)
        head = QLabel(t(key))
        head.setObjectName("kbGroup")
        grid.addWidget(head, r + 1, 0, 1, 3)
        return r + 2

    # 热键和控制键两张表，按动作名分派

    def _table(self, action):
        return self._combos if action in DEFAULT_HOTKEYS else self._names

    def _default(self, action):
        return DEFAULT_HOTKEYS[action] if action in DEFAULT_HOTKEYS else DEFAULT_KEYBINDS[action]

    def _text(self, action, value):
        return combo_text(*value) if action in DEFAULT_HOTKEYS else key_label(value)

    def _taken(self, combo) -> bool:
        """被别的程序占着；自己注册着的保存时会重挂，不算。"""
        hk = self._hotkeys
        return hk is not None and not hk.owns(*combo) and not hk.available(*combo)

    def _build_row(self, grid, r, action):
        lbl = QLabel(t("kb_" + action))
        lbl.setObjectName("kbAction")
        grid.addWidget(lbl, r, 0)

        cap = _KeyCap(combo=action in DEFAULT_HOTKEYS)
        cap.clicked.connect(lambda _c=False, a=action: self._toggle_listen(a))
        cap.captured.connect(lambda v, a=action: self._on_captured(a, v))
        cap.held.connect(lambda m, c=cap: c.setText(combo_text(m, 0) + "+…" if m else t("kb_listening")))
        cap.cancelled.connect(self._stop_listen)
        if cap.combo:
            install_tip(cap, lambda c=cap: t("kb_taken") if c.property("taken") else "")
        grid.addWidget(cap, r, 1)
        self._caps[action] = cap

        rs = QPushButton()
        rs.setObjectName("kbReset")
        rs.setIcon(ui_icon("reset", TEXT_DIM))
        rs.setIconSize(QSize(14, 14))
        rs.setFixedSize(22, 22)
        rs.setCursor(Qt.CursorShape.PointingHandCursor)
        rs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sp = rs.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        rs.setSizePolicy(sp)
        rs.clicked.connect(lambda _c=False, a=action: self._assign(a, self._default(a)))
        install_tip(rs, t("kb_reset_one", name=self._text(action, self._default(action))))
        grid.addWidget(rs, r, 2)
        self._resets[action] = rs

    def _refresh(self):
        for a, cap in self._caps.items():
            value = self._table(a)[a]
            if not cap.listening:
                cap.setText(self._text(a, value))
            if cap.combo:
                _set_prop(cap, "taken", self._taken(value))
            self._resets[a].setVisible(value != self._default(a))
        self._reset_all.setEnabled(self._names != DEFAULT_KEYBINDS or self._combos != DEFAULT_HOTKEYS)

    def _set_status(self, text="", warn=False):
        self._status.setText(text)
        _set_prop(self._status, "warn", warn)

    def _toggle_listen(self, action):
        if self._active == action:
            self._stop_listen()
            return
        self._stop_listen()
        self._active = action
        cap = self._caps[action]
        if cap.combo and self._hotkeys is not None:
            self._hotkeys.suspend()  # 不摘掉的话自己的组合键按下去会直接触发
        cap.set_listening(True)
        cap.setText(t("kb_listening"))
        cap.setFocus()
        self._set_status()

    def _stop_listen(self):
        a, self._active = self._active, None
        if a is not None:
            if self._hotkeys is not None:
                self._hotkeys.resume()
            self._caps[a].set_listening(False)
            self._refresh()

    def _on_captured(self, action, value):
        if action in DEFAULT_HOTKEYS:
            mods, vk = value
            if not key_ok(vk):
                self._set_status(t("kb_unsupported"), warn=True)
                return
            if not mods_ok(mods):
                self._set_status(t("kb_need_mod"), warn=True)
                return
            name = (mods, vk)
        else:
            name = key_name(value)
            if name is None:
                self._set_status(t("kb_unsupported"), warn=True)
                return
        self._stop_listen()
        self._assign(action, name)

    def _assign(self, action, value):
        """给动作绑键；该键已被同组别的动作占用就把旧键换给它。"""
        table = self._table(action)
        old = table[action]
        if value == old:
            self._set_status()
            return
        peers = HOTKEY_ACTIONS if action in DEFAULT_HOTKEYS else ACTIONS
        other = next((b for b in peers if b != action and table[b] == value), None)
        table[action] = value
        if other is not None:
            table[other] = old
            self._set_status(t("kb_swapped", name=self._text(action, value), other=t("kb_" + other)))
        else:
            self._set_status()
        self._refresh()
        self._flash([action] if other is None else [action, other])

    def _on_reset_all(self):
        self._stop_listen()
        self._names = dict(DEFAULT_KEYBINDS)
        self._combos = dict(DEFAULT_HOTKEYS)
        self._set_status()
        self._refresh()

    def _flash(self, actions):
        self._unflash()
        self._flashing = [self._caps[a] for a in actions]
        for cap in self._flashing:
            _set_prop(cap, "flash", True)
        self._flash_timer.start(FLASH_MS)

    def _unflash(self):
        for cap in self._flashing:
            _set_prop(cap, "flash", False)
        self._flashing = []

    def mousePressEvent(self, ev):
        self._stop_listen()
        super().mousePressEvent(ev)

    def done(self, result):
        if self._finished:
            return
        self._stop_listen()
        if result == self.DialogCode.Accepted:
            changed = False
            if self._names != self._saved:
                if not save_key_names(self._names):
                    self._set_status(t("kb_save_failed"), warn=True)
                    return
                self._saved = dict(self._names)
                changed = True
            if self._combos != self._saved_combos:
                if not save_hotkeys(self._combos):
                    self._set_status(t("kb_save_failed"), warn=True)
                    return
                self._saved_combos = dict(self._combos)
                changed = True
            if changed:
                self._on_saved()
        super().done(result)
