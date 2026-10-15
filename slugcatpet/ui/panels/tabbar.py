"""侧边栏：收起时是可上下拖的箭头，展开后是物品图标和操作按钮。"""

from __future__ import annotations
import math
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QVBoxLayout,
    QGridLayout,
    QFrame,
    QLabel,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QRectF, QPointF, QSize, QEvent
from PySide6.QtGui import QGuiApplication, QColor, QPainter, QPixmap, QIcon
from ...i18n import t
from ...items import kinds as item_kinds
from ..widgets.iconkit import ICON_GREY, ICON_RED, pen
from ..widgets.tips import install as install_tip
from ..theme import qss

COLLAPSED_W, COLLAPSED_H = 24, 48
EXPANDED_W = 120  # 展开态面板宽（不含左侧箭头）
ARROW_W = 16  # 展开态左侧收起箭头宽
EXPANDED_H = 250  # 估值，实际高度见 _expanded_h()
SLIDE_MS = 150


def _paint_tool_icon(p, kind, r):
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    if kind == "remove":
        d = min(w, h) * 0.52
        orb = QRectF(0, 0, d, d)
        orb.moveCenter(QPointF(cx - w * 0.09, cy + h * 0.03))
        p.setPen(pen(ICON_GREY, max(1.5, w * 0.10)))
        p.setBrush(QColor(70, 76, 66, 90))
        p.drawEllipse(orb)
        bd = min(w, h) * 0.48
        badge = QRectF(0, 0, bd, bd)
        badge.moveCenter(QPointF(cx + w * 0.22, cy - h * 0.20))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ICON_RED)
        p.drawEllipse(badge)
        p.setPen(pen(QColor(255, 255, 255), max(1.6, w * 0.09)))
        bc, hw = badge.center(), bd * 0.28
        p.drawLine(QPointF(bc.x() - hw, bc.y()), QPointF(bc.x() + hw, bc.y()))
    else:
        d = min(w, h) * 0.90
        ring = QRectF(0, 0, d, d)
        ring.moveCenter(QPointF(cx, cy))
        p.setPen(pen(ICON_RED, max(1.8, w * 0.13)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ring)
        a, rr = math.radians(45), d / 2
        p.drawLine(
            QPointF(cx - math.cos(a) * rr, cy + math.sin(a) * rr),
            QPointF(cx + math.cos(a) * rr, cy - math.sin(a) * rr),
        )


def _make_icon(paint, size, dpr):
    """把图标离屏画成 QPixmap。"""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    r = QRectF(0, 0, size, size)
    r.adjust(size * 0.10, size * 0.10, -size * 0.10, -size * 0.10)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    paint(p, r)
    p.end()
    return pm


class TabBar(QWidget):
    def __init__(self, pet, app, params=None):
        super().__init__()
        self.pet = pet
        self.app = app
        self.params = params or {}
        self.expanded = False
        self._drag = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self._y = self.params.get("tab_y", screen.y() + (screen.height() - EXPANDED_H) // 2)
        self._read_screen()

        self._build()
        self._apply_collapsed()

        app = QGuiApplication.instance()
        app.primaryScreenChanged.connect(self._track_screen)
        self._track_screen()

    def _read_screen(self):
        """取主屏可用区，收起态贴右边，纵向位置夹回屏内。"""
        s = QGuiApplication.primaryScreen().availableGeometry()
        self._screen = s
        self._edge_x = s.x() + s.width() - COLLAPSED_W
        self._y = max(s.y(), min(s.y() + s.height() - COLLAPSED_H, int(self._y)))

    def _track_screen(self, *_):
        QGuiApplication.primaryScreen().availableGeometryChanged.connect(self._on_screen_changed)
        self._on_screen_changed()

    def _on_screen_changed(self, *_):
        """分辨率、任务栏或主屏变化后重新贴边。"""
        self._read_screen()
        self._apply_expanded() if self.expanded else self._apply_collapsed()

    def _build(self):
        self._panel = QWidget(self)
        self._panel.setObjectName("tabPanel")
        self._panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self._panel)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        self._panel_lay = lay

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        atlas = getattr(self.pet, "atlas", None)
        place_items = [
            (
                lambda p, r, k=k: k.paint_icon(p, r, atlas),
                t(f"tip_{k.key}"),
                lambda _=False, k=k: self._place(k),
            )
            for k in item_kinds()
            if k.placeable
        ]
        place_items += [
            (lambda p, r: _paint_tool_icon(p, "remove", r), t("tip_remove"), self._remove_one),
            (lambda p, r: _paint_tool_icon(p, "clear", r), t("tip_clear"), self._clear_all),
        ]
        for i, (paint, tip, cb) in enumerate(place_items):
            ib = QPushButton()
            ib.setIcon(QIcon(_make_icon(paint, 22, dpr)))
            ib.setIconSize(QSize(22, 22))
            ib.setFixedHeight(32)
            install_tip(ib, tip)
            ib.setCursor(Qt.CursorShape.PointingHandCursor)
            ib.clicked.connect(cb)
            grid.addWidget(ib, i // 3, i % 3)
        grid_host = QWidget()
        grid_host.setLayout(grid)
        lay.addWidget(grid_host)
        lay.addWidget(self._divider())

        def btn(text, enabled, cb, tip=None):
            b = QPushButton(text)
            b.setEnabled(enabled)
            if tip:
                install_tip(b, tip)
            if cb:
                b.clicked.connect(cb)
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
            return b

        btn(t("btn_music"), True, lambda: self.pet.open_music())
        btn(t("btn_open_settings"), True, self._open_settings)
        btn(t("btn_quit_app"), True, self._quit)
        self._panel.setStyleSheet(qss.TABBAR_PANEL)

        # 箭头：eventFilter 区分拖动和点击
        self._arrow = QPushButton("‹", self)
        self._arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow.installEventFilter(self)
        self._arrow_press = None
        self._arrow_moved = False
        self._arrow.setStyleSheet(qss.TABBAR_ARROW)

        # 提示用顶层窗口，免得被裁切
        self._toast_lbl = QLabel("", None)
        self._toast_lbl.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.ToolTip
        )
        self._toast_lbl.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._toast_lbl.setStyleSheet(qss.TOAST)
        self._toast_lbl.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_lbl.hide)

    def rebuild_ui(self):
        expanded = self.expanded
        self._toast_timer.stop()
        for w in (self._panel, self._arrow, self._toast_lbl):
            w.setParent(None)
            w.deleteLater()
        self._build()
        self._apply_expanded() if expanded else self._apply_collapsed()

    def _apply_collapsed(self):
        self.expanded = False
        h = COLLAPSED_H
        self.setGeometry(self._edge_x, self._y, COLLAPSED_W, h)
        self._arrow.setGeometry(0, 0, COLLAPSED_W, h)
        self._arrow.setText("‹")
        self._arrow.show()
        self._panel.hide()
        eff = QGraphicsOpacityEffect(self._arrow)
        eff.setOpacity(0.45)
        self._arrow.setGraphicsEffect(eff)

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(qss.DIVIDER_LINE)
        return f

    def _expanded_h(self):
        return self._panel_lay.sizeHint().height()

    def _apply_expanded(self):
        self.expanded = True
        h = self._expanded_h()
        s = self._screen
        x = s.x() + s.width() - EXPANDED_W - ARROW_W
        y = max(s.y(), min(s.y() + s.height() - h, self._y))  # 只夹展开态，不改记下的位置
        self.setGeometry(x, y, EXPANDED_W + ARROW_W, h)
        self._panel.setGeometry(ARROW_W, 0, EXPANDED_W, h)
        self._panel.show()
        self._arrow.setGeometry(0, 0, ARROW_W, h)
        self._arrow.setText("›")
        self._arrow.setGraphicsEffect(None)
        self._arrow.raise_()

    def toggle(self):
        if self.expanded:
            self._animate_to(self._edge_x, COLLAPSED_W, COLLAPSED_H, self._apply_collapsed)
        else:
            self._apply_expanded()

    def _animate_to(self, x, w, h, done):
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(SLIDE_MS)
        anim.setStartValue(self.geometry())
        anim.setEndValue(QRect(x, self._y, w, h))
        anim.finished.connect(done)
        anim.start()
        self._anim = anim

    def eventFilter(self, obj, ev):
        if obj is self._arrow:
            try:
                t = ev.type()
            except AttributeError:
                return False  # 关停期丢 type，放行
            if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self._arrow_press = ev.globalPosition().y() - self.y()
                self._arrow_moved = False
                return False
            if t == QEvent.Type.MouseMove and self._arrow_press is not None and not self.expanded:
                ny = int(ev.globalPosition().y() - self._arrow_press)
                ny = max(self._screen.y(), min(self._screen.y() + self._screen.height() - self.height(), ny))
                if abs(ny - self._y) > 2:
                    self._arrow_moved = True
                self._y = ny
                self.move(self._edge_x, ny)
                return False
            if (
                t == QEvent.Type.MouseButtonRelease
                and ev.button() == Qt.MouseButton.LeftButton
                and self._arrow_press is not None
            ):
                moved = self._arrow_moved
                self._arrow_press = None
                self._arrow_moved = False
                if moved and not self.expanded:
                    self.params["tab_y"] = self._y
                else:
                    self.toggle()
                return True
        return super().eventFilter(obj, ev)

    def _toast(self, msg):
        self._toast_lbl.setText(msg)
        self._toast_lbl.adjustSize()
        right = EXPANDED_W + ARROW_W if self.expanded else COLLAPSED_W
        gx = self._screen.x() + self._screen.width() - self._toast_lbl.width() - right - 8
        gy = self.y() + 10
        self._toast_lbl.move(gx, gy)
        self._toast_lbl.show()
        self._toast_lbl.raise_()
        self._toast_timer.start(1600)

    def _collapse(self):
        if self.expanded:
            self.toggle()

    def _place(self, kind):
        if self.pet.enter_place_mode(kind.key):
            self._collapse()
        else:
            self._toast(t(f"toast_max_{kind.key}", n=kind.cap))

    def _remove_one(self):
        if self.pet.has_items():
            self.pet.enter_remove_mode()
            self._collapse()
        else:
            self._toast(t("toast_no_object"))

    def _clear_all(self):
        if self.pet.has_items():
            self.pet.clear_all_items()
        else:
            self._toast(t("toast_no_object"))

    def _open_settings(self):
        self.pet.open_settings()

    def _quit(self):
        # 释放劫持后再 quit
        try:
            from ...platform.cursorfx import abort_all

            abort_all()
        except Exception:
            pass
        self.app.quit()
