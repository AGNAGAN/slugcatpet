"""自绘卡片弹窗：show()=非模态，open()=WindowModal，不走 exec。"""

from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
)
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QGuiApplication, QTextDocument, QTextOption
from ..overlay import clamp_local
from ..theme import qss
from .screens import clamp_rect

# 壳级 QSS：防父窗样式渗透
_CARD_QSS = qss.CARD

_BTN_KIND = {"primary": "btnPrimary", "ghost": "btnGhost", "danger": "btnDanger"}


class CardDialog(QDialog):
    def __init__(self, title: str, parent=None, width: int = 300, embedded: bool | None = None):
        super().__init__(parent)
        if embedded is None:
            # 只有 overlay 自己的弹窗才嵌入。设置/音乐里的弹窗仍是普通 transient
            # 对话框，由合成器负责定位。
            embedded = bool(parent is not None and getattr(parent, "is_overlay", False))
        self._embedded = bool(embedded and parent is not None)
        self._host = parent if self._embedded else None
        self.setObjectName("cardShell")
        if self._embedded:
            self.setWindowFlags(Qt.WindowType.Widget)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        else:
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog
            )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._drag_off = None
        self._finished = False
        self._app_filter = False
        self._card = QWidget(self)
        self._card.setObjectName("cardRoot")
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._card.setFixedWidth(width)
        col = QVBoxLayout(self._card)
        col.setContentsMargins(24, 20, 24, 18)
        col.setSpacing(12)
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        col.addWidget(lbl)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        col.addLayout(self.body)
        self._btn_row = QHBoxLayout()
        self._btn_row.setSpacing(10)
        self._btn_row.addStretch(1)
        col.addLayout(self._btn_row)
        self.setStyleSheet(_CARD_QSS)

    def done(self, result):
        if self._finished:  # 防二次发射 finished
            return
        self._finished = True
        super().done(result)

    def add_button(self, text: str, kind: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(_BTN_KIND[kind])
        self._btn_row.addWidget(btn)
        return btn

    def place_center(self, host=None, offset: QPoint | None = None):
        self._card.adjustSize()
        size = self._card.size()
        self.resize(size)
        self._card.setGeometry(0, 0, size.width(), size.height())
        if self._embedded:
            area = self._host.rect()
            x = area.x() + (area.width() - size.width()) // 2
            y = area.y() + (area.height() - size.height()) // 3
        elif host is not None:
            g = host.frameGeometry()
            x = g.x() + (g.width() - size.width()) // 2
            y = g.y() + (g.height() - size.height()) // 2
        else:
            scr = QGuiApplication.primaryScreen().availableGeometry()
            x = scr.x() + (scr.width() - size.width()) // 2
            y = scr.y() + (scr.height() - size.height()) // 3
        if offset is not None:
            x += offset.x()
            y += offset.y()
        self.move(self._clamped(QPoint(x, y)))
        if self._embedded:
            self._host.register_overlay_widget(self)
            self.raise_()

    def _clamped(self, pos: QPoint) -> QPoint:
        if self._embedded:
            return clamp_local(self._host, pos, self.width(), self.height())
        return clamp_rect(pos, self.width(), self.height())

    def showEvent(self, ev):
        super().showEvent(ev)
        if self._embedded:
            self._host.register_overlay_widget(self)
            self.raise_()
            self.window().activateWindow()
            app = QGuiApplication.instance()
            if app is not None and not self._app_filter:
                app.installEventFilter(self)
                self._app_filter = True

    def hideEvent(self, ev):
        if self._embedded and self._app_filter:
            app = QGuiApplication.instance()
            if app is not None:
                app.removeEventFilter(self)
            self._app_filter = False
        super().hideEvent(ev)
        if self._embedded:
            self._host.unregister_overlay_widget(self)

    def eventFilter(self, obj, ev):
        """模态卡片打开时吃掉卡片外的点击，避免点到下面的猫或面板。"""
        if not self._embedded or not self.isVisible():
            return super().eventFilter(obj, ev)
        if ev.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(obj, ev)
        try:
            local = self._host.mapFromGlobal(ev.globalPosition().toPoint())
        except (AttributeError, RuntimeError):
            return super().eventFilter(obj, ev)
        if self.geometry().contains(local):
            return super().eventFilter(obj, ev)
        # 多张确认卡叠放时，点在另一张卡上仍要放行。
        for other in self._host.findChildren(CardDialog):
            if other is not self and other.isVisible() and other.geometry().contains(local):
                return super().eventFilter(obj, ev)
        return True

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._embedded:
                self._drag_off = ev.position().toPoint()
            else:
                self._drag_off = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag_off is not None and (ev.buttons() & Qt.MouseButton.LeftButton):
            if self._embedded:
                pos = self.pos() + ev.position().toPoint() - self._drag_off
            else:
                pos = ev.globalPosition().toPoint() - self._drag_off
            self.move(self._clamped(pos))
            if self._embedded:
                self._host.refresh_input_region(force=True)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_off = None
        super().mouseReleaseEvent(ev)


NOTE_MAX_HEIGHT = 170


class ConfirmDialog(CardDialog):
    """确认弹窗（Accepted=确认）；note 是附在正文下的一段原文；cancel_btn 供外部程序化点击。"""

    def __init__(
        self,
        title: str,
        text: str,
        confirm_text: str,
        cancel_text: str,
        parent=None,
        width: int = 300,
        note: str | None = None,
    ):
        super().__init__(title, parent, width)
        self._note = None
        lbl = QLabel(text)
        lbl.setObjectName("cardText")
        lbl.setWordWrap(True)
        self.body.addWidget(lbl)
        if note is not None:
            nl = QPlainTextEdit(note)
            nl.setObjectName("cardNote")
            nl.setReadOnly(True)
            nl.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            self._note = nl
            nl.setFixedHeight(40)
            self.body.addWidget(nl)
        self.confirm_btn = self.add_button(confirm_text, "danger")
        self.confirm_btn.clicked.connect(self.accept)
        self.cancel_btn = self.add_button(cancel_text, "primary")
        self.cancel_btn.setDefault(True)
        self.cancel_btn.clicked.connect(self.reject)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.cancel_btn.setFocus()
        if self._note is not None:
            self._fit_note()

    def _fit_note(self):
        """按换行后的文字高度定文字区高度，最高 NOTE_MAX_HEIGHT，并让弹窗跟着变。"""
        n = self._note
        n.ensurePolished()
        extra = n.height() - n.viewport().height()
        doc = QTextDocument()
        doc.setDefaultFont(n.font())
        doc.setDefaultTextOption(n.document().defaultTextOption())
        doc.setDocumentMargin(n.document().documentMargin())
        doc.setPlainText(n.toPlainText())
        doc.setTextWidth(n.viewport().width())
        n.setFixedHeight(min(NOTE_MAX_HEIGHT, int(doc.size().height()) + extra + 8))
        self._card.adjustSize()
        size = self._card.size()
        self.resize(size)
        self._card.setGeometry(0, 0, size.width(), size.height())
        if self._embedded:
            self._host.refresh_input_region(force=True)


class PickDialog(CardDialog):
    """选择弹窗；Accepted 后读 selected_index()。"""

    def __init__(
        self,
        title: str,
        label: str,
        items: list,
        ok_text: str,
        cancel_text: str,
        parent=None,
        current: int = 0,
        width: int = 320,
    ):
        super().__init__(title, parent, width)
        lbl = QLabel(label)
        lbl.setObjectName("cardText")
        lbl.setWordWrap(True)
        self.body.addWidget(lbl)
        self._group = QButtonGroup(self)
        for i, item in enumerate(items):
            rb = QRadioButton(item)
            rb.setChecked(i == current)
            self._group.addButton(rb, i)
            self.body.addWidget(rb)
        self.cancel_btn = self.add_button(cancel_text, "ghost")
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = self.add_button(ok_text, "primary")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)

    def selected_index(self) -> int:
        return max(0, self._group.checkedId())
