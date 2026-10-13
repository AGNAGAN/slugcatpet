"""状态面板 HUD：每猫一行体征，可拖动可隐藏；超出屏幕高时内部滚动。"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QScrollArea
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

from .hudrow import PetRow
from ..theme import qss

REFRESH_MS = 200
SCREEN_PAD = 24
SCROLLBAR_W = 10

_PANEL_QSS = qss.HUD_PANEL


class HudPanel(QWidget):
    def __init__(self, pet, params=None):
        super().__init__()
        self.pet = pet
        self.params = params if params is not None else {}
        self._drag = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._build()
        self._place()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        # 定时器由 toggle_visible 控制启停

        self.hide()

    def _pets(self):
        return getattr(self.pet, "pets", None) or [self.pet]

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(qss.HUD_SCROLL)
        self._scroll.viewport().setObjectName("hudViewport")
        self._panel = QWidget()
        self._panel.setObjectName("hudPanel")
        self._vbox = QVBoxLayout(self._panel)
        self._vbox.setContentsMargins(10, 8, 10, 8)
        self._vbox.setSpacing(6)
        self._panel.setStyleSheet(_PANEL_QSS)
        self._scroll.setWidget(self._panel)
        outer.addWidget(self._scroll)
        self._rows = []
        self._build_rows()

    def _build_rows(self):
        for i, pet_unit in enumerate(self._pets()):
            if i > 0:
                self._vbox.addWidget(self._divider())
            row = PetRow(pet_unit, self)
            self._vbox.addWidget(row)
            self._rows.append(row)

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(qss.DIVIDER_LINE)
        return f

    def rebuild_rows(self):
        while self._vbox.count():
            item = self._vbox.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows = []
        self._build_rows()
        self._refresh()
        self._place()

    def _place(self):
        self._panel.layout().activate()
        hint = self._panel.sizeHint()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(hint.width() + SCROLLBAR_W,
                    min(hint.height(), max(120, screen.height() - SCREEN_PAD * 2)))
        x = self.params.get("hud_x")
        y = self.params.get("hud_y")
        if x is None or y is None:
            x = screen.x() + SCREEN_PAD
            y = screen.y() + SCREEN_PAD
        x = max(screen.x(), min(screen.x() + screen.width() - self.width(), int(x)))
        y = max(screen.y(), min(screen.y() + screen.height() - self.height(), int(y)))
        self.move(x, y)
        self.params["hud_x"] = x
        self.params["hud_y"] = y

    def toggle_visible(self):
        # 实时记显隐（退出时查不到）
        if self.isVisible():
            self.hide()
            self._timer.stop()
            self.params["hud_visible"] = False
        else:
            self.show()
            self.raise_()
            self._refresh()
            self._timer.start(REFRESH_MS)
            self.params["hud_visible"] = True

    def _refresh(self):
        if not self.isVisible():
            return
        replot = False
        for row in self._rows:
            replot = row.refresh() or replot
        if replot:
            self._place()

    # 面板背景拖动整窗，行内由 PetRow 自理
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            screen = QGuiApplication.primaryScreen().availableGeometry()
            p = ev.globalPosition().toPoint() - self._drag
            x = max(screen.x(), min(screen.x() + screen.width() - self.width(), p.x()))
            y = max(screen.y(), min(screen.y() + screen.height() - self.height(), p.y()))
            self.move(x, y)
            self.params["hud_x"] = x
            self.params["hud_y"] = y
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        ev.accept()
