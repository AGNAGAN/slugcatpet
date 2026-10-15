"""键位弹窗：列出全局和定格时的固定热键；手动控制的键点键帽录入新键，与其他动作冲突时互换，完成才保存。"""

from __future__ import annotations
import sys
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence

from ...i18n import t
from ...control.hotkey import FROZEN_KEYS, GLOBAL_KEYS, combo_text
from ...control.keymap import ACTIONS, DEFAULT_KEYBINDS, key_name, load_key_names, save_key_names
from ..theme import qss
from ..theme.palette import TEXT_DIM
from ..widgets.dialogs import CardDialog
from ..widgets.iconkit import ui_icon
from ..widgets.tips import install as install_tip

_CONTROL_ORDER = ("up", "down", "left", "right", "jump", "grab", "throw", "hold")
_ARROWS = {"Up": "↑", "Down": "↓", "Left": "←", "Right": "→"}
_SHORT = {"Control": "Ctrl", "Return": "Enter", "CapsLock": "Caps"}
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


def _set_prop(w, prop, on):
    w.setProperty(prop, on)
    w.style().unpolish(w)
    w.style().polish(w)


class _KeyCap(QPushButton):
    """键帽按钮：录入中吞下一次按键并发出 captured，Esc 或失焦发出 cancelled。"""

    captured = Signal(int)
    cancelled = Signal()

    def __init__(self):
        self.listening = False
        super().__init__()
        self.setObjectName("keyCap")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_listening(self, on: bool):
        self.listening = on
        _set_prop(self, "listening", on)

    def event(self, e):
        if self.listening:
            if e.type() == QEvent.Type.ShortcutOverride:
                e.accept()
                return True
            if e.type() == QEvent.Type.KeyPress:
                if not e.isAutoRepeat():
                    if e.key() == Qt.Key.Key_Escape:
                        self.cancelled.emit()
                    else:
                        self.captured.emit(int(e.key()))
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
        self._saved = load_key_names()
        self._names = dict(self._saved)
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
        r = self._fixed_group(grid, 0, "kb_group_global", GLOBAL_KEYS, hotkeys, live=True)
        r = self._fixed_group(grid, r, "kb_group_frozen", FROZEN_KEYS, hotkeys, live=False)

        r = self._group_head(grid, r, "kb_group_control")
        hint = QLabel(t("kb_hint"))
        hint.setObjectName("kbHint")
        hint.setWordWrap(True)
        grid.addWidget(hint, r, 0, 1, 3)
        r += 1
        for a in _CONTROL_ORDER:
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
        if r:
            grid.setRowMinimumHeight(r, 6)
            r += 1
        head = QLabel(t(key))
        head.setObjectName("kbGroup")
        grid.addWidget(head, r, 0, 1, 3)
        return r + 1

    def _fixed_group(self, grid, r, key, keys, hotkeys, live):
        """只读的热键行；live 为常驻热键（看注册结果），否则试注册看有没有被占。"""
        r = self._group_head(grid, r, key)
        for hk_id, (mods, vk, label_key) in keys.items():
            lbl = QLabel(t(label_key))
            lbl.setObjectName("kbAction")
            grid.addWidget(lbl, r, 0)
            cap = QLabel(combo_text(mods, vk))
            cap.setObjectName("keyCapFixed")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            taken = False
            if hotkeys is not None and sys.platform == "win32":
                taken = not (hotkeys.registered(hk_id) or (not live and hotkeys.available(mods, vk)))
            _set_prop(cap, "taken", taken)
            install_tip(cap, t("kb_taken") if taken else t("kb_fixed"))
            grid.addWidget(cap, r, 1)
            r += 1
        return r

    def _build_row(self, grid, r, action):
        lbl = QLabel(t("kb_" + action))
        lbl.setObjectName("kbAction")
        grid.addWidget(lbl, r, 0)

        cap = _KeyCap()
        cap.clicked.connect(lambda _c=False, a=action: self._toggle_listen(a))
        cap.captured.connect(lambda k, a=action: self._on_captured(a, k))
        cap.cancelled.connect(self._stop_listen)
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
        rs.clicked.connect(lambda _c=False, a=action: self._assign(a, DEFAULT_KEYBINDS[a]))
        install_tip(rs, t("kb_reset_one", name=key_label(DEFAULT_KEYBINDS[action])))
        grid.addWidget(rs, r, 2)
        self._resets[action] = rs

    def _refresh(self):
        for a, cap in self._caps.items():
            if not cap.listening:
                cap.setText(key_label(self._names[a]))
            self._resets[a].setVisible(self._names[a] != DEFAULT_KEYBINDS[a])
        self._reset_all.setEnabled(self._names != DEFAULT_KEYBINDS)

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
        cap.set_listening(True)
        cap.setText(t("kb_listening"))
        cap.setFocus()
        self._set_status()

    def _stop_listen(self):
        a, self._active = self._active, None
        if a is not None:
            self._caps[a].set_listening(False)
            self._refresh()

    def _on_captured(self, action, qt_key):
        name = key_name(qt_key)
        if name is None:
            self._set_status(t("kb_unsupported"), warn=True)
            return
        self._stop_listen()
        self._assign(action, name)

    def _assign(self, action, name):
        """给动作绑键；该键已被别的动作占用就把旧键换给它。"""
        old = self._names[action]
        if name == old:
            self._set_status()
            return
        other = next((b for b in ACTIONS if b != action and self._names[b] == name), None)
        self._names[action] = name
        if other is not None:
            self._names[other] = old
            self._set_status(t("kb_swapped", name=key_label(name), other=t("kb_" + other)))
        else:
            self._set_status()
        self._refresh()
        self._flash([action] if other is None else [action, other])

    def _on_reset_all(self):
        self._stop_listen()
        self._names = dict(DEFAULT_KEYBINDS)
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
        if result == self.DialogCode.Accepted and self._names != self._saved:
            if not save_key_names(self._names):
                self._set_status(t("kb_save_failed"), warn=True)
                return
            self._on_saved()
        super().done(result)
