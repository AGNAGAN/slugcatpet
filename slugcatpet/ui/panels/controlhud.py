"""控制 HUD：受控猫键盘输入窗，失焦暂停。"""

from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QLayout
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication

from ...i18n import t
from ...control.input import InputPackage
from ...control.keymap import load_key_names, load_keymap, normalize_key
from .keybinds import key_label
from .catmenu import pet_label
from ..theme import qss
from ..widgets.screens import clamp_rect

WATCH_MS = 200
BOTTOM_MARGIN = 24

_PANEL_QSS = qss.CONTROL_PANEL

_PAUSED_QSS = qss.PAUSED_TEXT


class ControlHud(QWidget):
    def __init__(self, window, pet, parent=None, embedded=False):
        self._embedded = bool(embedded and parent is not None)
        self._host = parent if self._embedded else None
        super().__init__(parent if self._embedded else None)
        self._window = window
        self.pet = pet
        self._held = set()
        self._paused = False
        self._drag = None
        self._keymap = {}

        if not self._embedded:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
            )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 勿设 WA_ShowWithoutActivating，键盘唯一入口

        self._build()
        self._place()

        self._watch = QTimer(self)
        self._watch.timeout.connect(self._check_session)
        self._watch.start(WATCH_MS)
        if self._embedded:
            self._host.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if self._embedded and obj is self._host:
            try:
                if ev.type() == QEvent.Type.Resize:
                    self._place()
            except AttributeError:
                pass
        return super().eventFilter(obj, ev)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        panel = QWidget()
        panel.setObjectName("ctrlPanel")
        panel.setStyleSheet(_PANEL_QSS)
        box = QVBoxLayout(panel)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(6)

        title = QLabel(t("ctrlhud_title", name=pet_label(self.pet, list(self._window.pets))))
        title.setObjectName("ctrlTitle")
        box.addWidget(title)

        self._keys = QLabel()
        self._keys.setObjectName("ctrlKeys")
        box.addWidget(self._keys)
        self.reload_keys()

        btn = QPushButton(t("ctrlhud_exit"))
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 防空格触发按钮
        btn.clicked.connect(lambda: self._window.stop_control())
        box.addWidget(btn)
        outer.addWidget(panel)

    def reload_keys(self):
        """重读键位表，刷新映射和提示文字。"""
        names = load_key_names()
        self._keymap = load_keymap()
        self._held.clear()
        k = {a: key_label(n) for a, n in names.items()}
        arrows = [k[a] for a in ("up", "left", "down", "right")]
        move = "".join(arrows) if all(len(x) == 1 for x in arrows) else "/".join(arrows)
        self._keys_text = t(
            "ctrlhud_keys", move=move, jump=k["jump"], grab=k["grab"], throw=k["throw"], hold=k["hold"]
        )
        if not self._paused:
            self._keys.setText(self._keys_text)

    def _place(self):
        self.layout().activate()
        size = self.sizeHint()
        screen = self._host.rect() if self._embedded else QGuiApplication.primaryScreen().availableGeometry()
        x = max(screen.x(), screen.x() + (screen.width() - size.width()) // 2)
        y = max(screen.y(), screen.y() + screen.height() - size.height() - BOTTOM_MARGIN)
        self.move(x, y)

    # 输入来源，暂停时返回空包防冻结
    def current_input(self) -> InputPackage:
        if self._paused:
            return InputPackage()
        km, held = self._keymap, self._held

        def down(action):
            k = km.get(action)
            return k is not None and k in held

        x = (1 if down("right") else 0) - (1 if down("left") else 0)
        y = (1 if down("up") else 0) - (1 if down("down") else 0)
        return InputPackage(x=x, y=y, jmp=down("jump"), pckp=down("grab"), thrw=down("throw"))

    def _check_session(self):
        if not getattr(self.pet, "controlled", False) or self.pet not in self._window.pets:
            self._window.stop_control()

    def _set_paused(self, paused: bool):
        if paused == self._paused:
            return
        self._paused = paused
        self._held.clear()
        g = self.geometry()
        cx, cy = g.x() + g.width() // 2, g.y() + g.height() // 2
        self._keys.setText(t("ctrlhud_paused") if paused else self._keys_text)
        self._keys.setStyleSheet(_PAUSED_QSS if paused else "")
        self.setWindowOpacity(0.7 if paused else 1.0)
        self.layout().activate()  # 文字宽度变了，按原中心重新摆
        w, h = self.width(), self.height()
        p = QPoint(cx - w // 2, cy - h // 2)
        if self._embedded:
            p = QPoint(
                max(0, min(p.x(), max(0, self._host.width() - w))),
                max(0, min(p.y(), max(0, self._host.height() - h))),
            )
        else:
            p = clamp_rect(p, w, h)
        self.move(p)
        if self._embedded:
            self._host.refresh_input_region(force=True)

    # 焦点：show 即抢焦（需同步栈内）
    def showEvent(self, e):
        super().showEvent(e)
        if self._embedded:
            # 子控件不能自己成为顶层焦点代理，先激活 overlay 表面。
            self.window().activateWindow()
        else:
            self.activateWindow()
        self.raise_()
        self.setFocus()
        refresh = getattr(self._window, "refresh_input_region", None)
        if refresh is not None:
            refresh(force=True)

    def hideEvent(self, e):
        super().hideEvent(e)
        refresh = getattr(self._window, "refresh_input_region", None)
        if refresh is not None:
            refresh(force=True)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._set_paused(False)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._set_paused(True)

    def focusNextPrevChild(self, _next):
        return False  # Tab 留给键位

    def keyPressEvent(self, e):
        if e.isAutoRepeat():
            return
        if e.key() == Qt.Key.Key_Escape:
            self._window.stop_control()
            return
        if normalize_key(e.key()) == self._keymap.get("hold"):
            self._window.hold_controlled()
            return
        self._held.add(normalize_key(e.key()))

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        self._held.discard(normalize_key(e.key()))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._embedded:
                self._drag = ev.position().toPoint()
                self.window().activateWindow()
            else:
                self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.activateWindow()
            self.setFocus()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            if self._embedded:
                pos = self.pos() + ev.position().toPoint() - self._drag
                pos = QPoint(
                    max(0, min(pos.x(), max(0, self._host.width() - self.width()))),
                    max(0, min(pos.y(), max(0, self._host.height() - self.height()))),
                )
            else:
                pos = clamp_rect(ev.globalPosition().toPoint() - self._drag, self.width(), self.height())
            self.move(pos)
            if self._embedded:
                self._host.refresh_input_region(force=True)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        ev.accept()
