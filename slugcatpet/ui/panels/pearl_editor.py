"""珍珠编辑弹窗：写文字、选颜色、勾选是否有悬浮符文。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
)

from ...i18n import t
from ..theme import qss
from ..widgets.dialogs import CardDialog


class _LimitedEdit(QPlainTextEdit):
    """粘贴或拖入时只收下还放得下的部分。"""

    def __init__(self, limit):
        super().__init__()
        self._limit = limit

    def insertFromMimeData(self, source):
        if not source.hasText():
            return
        room = self._limit - len(self.toPlainText()) + len(self.textCursor().selectedText())
        if room > 0:
            self.textCursor().insertText(source.text()[:room])


class PearlEditor(CardDialog):
    def __init__(self, text, color, glyph_on, palette, limit, parent=None):
        super().__init__(t("pearl_title"), parent, width=320)
        self._limit = limit
        self._palette = palette
        self.edit = _LimitedEdit(limit)
        self.edit.setFixedHeight(96)
        self.edit.setPlainText(text)
        self.edit.textChanged.connect(self._clamp)
        self.body.addWidget(self.edit)
        self._count = QLabel()
        self._count.setObjectName("pearlCount")
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.body.addWidget(self._count)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._group = QButtonGroup(self)
        for i, rgb in enumerate(palette):
            b = QPushButton()
            b.setObjectName("pearlSwatch")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"background:rgb({rgb[0]},{rgb[1]},{rgb[2]});")
            b.setChecked(tuple(rgb) == tuple(color))
            self._group.addButton(b, i)
            row.addWidget(b)
        row.addStretch(1)
        self.body.addLayout(row)
        if self._group.checkedId() < 0:
            self._group.button(0).setChecked(True)

        self._glyph = QCheckBox(t("pearl_glyph"))
        self._glyph.setChecked(glyph_on)
        self.body.addWidget(self._glyph)

        self.cancel_btn = self.add_button(t("settings_cancel"), "ghost")
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = self.add_button(t("settings_ok"), "primary")
        self.ok_btn.clicked.connect(self.accept)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.accept)
        self._clamp()
        self.setStyleSheet(qss.PEARL_EDITOR)

    def _clamp(self):
        s = self.edit.toPlainText()
        if len(s) > self._limit:
            cur = self.edit.textCursor()
            pos = min(cur.position(), self._limit)
            self.edit.blockSignals(True)
            self.edit.setPlainText(s[: self._limit])
            cur.setPosition(pos)
            self.edit.setTextCursor(cur)
            self.edit.blockSignals(False)
            s = s[: self._limit]
        self._count.setText(f"{len(s)}/{self._limit}")

    def focus_text(self):
        self.edit.setFocus()
        self.edit.moveCursor(self.edit.textCursor().MoveOperation.End)

    def text(self) -> str:
        return self.edit.toPlainText()

    def color(self):
        return tuple(self._palette[max(0, self._group.checkedId())])

    def glyph_on(self) -> bool:
        return self._glyph.isChecked()
