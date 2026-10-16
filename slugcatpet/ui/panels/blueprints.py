"""布局蓝图弹窗：存下场上的杆和灯笼，单击一行在场上预览，载入、覆盖、改名、删除。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...i18n import t
from ...items import scene
from ..theme import qss
from ..widgets.dialogs import CardDialog, ConfirmDialog
from ..widgets.tips import install as install_tip

LIST_MAX_H = 380  # 列表超过这么高就滚动
_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape)


def _set_prop(w, prop, on):
    w.setProperty(prop, on)
    w.style().unpolish(w)
    w.style().polish(w)


class _NameEdit(QLineEdit):
    """改名输入框：回车或失焦提交，Esc 取消。"""

    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, text):
        super().__init__(text)
        self._done = False
        self.setMaxLength(24)

    def _commit(self):
        if not self._done:
            self._done = True
            self.committed.emit(self.text())

    def event(self, e):
        if e.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and e.key() in _KEYS:
            e.accept()  # 回车、Esc 只管改名，不触发弹窗的默认按钮或关闭
            if e.type() == QEvent.Type.KeyPress:
                if e.key() == Qt.Key.Key_Escape:
                    if not self._done:
                        self._done = True
                        self.cancelled.emit()
                else:
                    self._commit()
            return True
        return super().event(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._commit()


class _Card(QFrame):
    """一行蓝图；单击空白处发出 clicked。"""

    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("bpCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class BlueprintDialog(CardDialog):
    def __init__(self, window, write_state, parent=None):
        super().__init__(t("settings_blueprints"), parent, width=440)
        self._card.setStyleSheet(qss.BLUEPRINTS)
        self._win = window
        self._write_state = write_state
        self._sel = None  # 选中的那份蓝图（dict）
        self._previewing = False
        self._renaming = None
        self._sub = None  # 确认弹窗

        top = QHBoxLayout()
        hint = QLabel(t("bp_hint"))
        hint.setObjectName("bpHint")
        top.addWidget(hint, 1)
        self._count = QLabel()
        self._count.setObjectName("bpCount")
        top.addWidget(self._count)
        self.body.addLayout(top)

        self._list = QWidget()
        self._list.setObjectName("bpList")
        self._rows = QVBoxLayout(self._list)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(8)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._list)
        self.body.addWidget(self._scroll)

        self._status = QLabel("")
        self._status.setObjectName("bpStatus")
        self._status.setWordWrap(True)
        self.body.addWidget(self._status)

        self._new = QPushButton()
        self._new.setObjectName("btnGhost")
        self._new.clicked.connect(self._on_new)
        self._btn_row.insertWidget(0, self._new)
        done = self.add_button(t("skin_done"), "primary")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        self._rebuild()

    # 列表

    def _bps(self):
        return self._win.blueprints()

    def _rebuild(self, rename=None):
        while self._rows.count():
            w = self._rows.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._renaming = None
        bps = self._bps()
        rows = [self._make_card(bp, bp is rename) for bp in bps]
        if not rows:
            empty = QLabel(t("bp_none"))
            empty.setObjectName("bpHint")
            empty.setWordWrap(True)
            empty.setFixedWidth(self._scroll.viewport().width() or 380)
            rows.append(empty)
        for wd in rows:
            self._rows.addWidget(wd)
        self._rows.addStretch(1)
        # 新加的行还没显示，列表的 sizeHint 不算它们，高度按各行自己算
        h = sum(wd.sizeHint().height() for wd in rows) + self._rows.spacing() * (len(rows) - 1)
        self._list.setMinimumHeight(h)
        n, cap = len(bps), scene.BLUEPRINT_CAP
        self._count.setText(t("bp_count", n=n, cap=cap))
        full = n >= cap
        self._new.setText(t("bp_full", cap=cap) if full else t("bp_new"))
        self._new.setEnabled(not full)
        self._scroll.setFixedHeight(min(LIST_MAX_H, h))
        self.place_size()

    def place_size(self):
        """内容高度变了，卡片和外壳跟着变，左上角不动。"""
        self._card.adjustSize()
        self.resize(self._card.size())

    def _make_card(self, bp, rename):
        card = _Card()
        selected = bp is self._sel
        _set_prop(card, "selected", selected)
        card.clicked.connect(lambda b=bp: self._on_pick(b))
        col = QVBoxLayout(card)
        col.setContentsMargins(12, 10, 12, 10)
        col.setSpacing(4)

        head = QHBoxLayout()
        if rename:
            edit = _NameEdit(bp.get("name", ""))
            edit.committed.connect(lambda text, b=bp: self._finish_rename(b, text))
            edit.cancelled.connect(lambda: self._rebuild())
            head.addWidget(edit, 1)
            self._renaming = edit
        else:
            name = QLabel(bp.get("name", ""))
            name.setObjectName("bpName")
            head.addWidget(name, 1)
        if selected and self._previewing:
            tag = QLabel(t("bp_previewing"))
            tag.setObjectName("bpTag")
            head.addWidget(tag)
        col.addLayout(head)

        meta = QHBoxLayout()
        c = scene.counts(bp)
        summary = QLabel(t("bp_summary", v=c.get("vpole", 0), h=c.get("hpole", 0), l=c.get("lamp", 0)))
        summary.setObjectName("bpMeta")
        meta.addWidget(summary, 1)
        size = QLabel()
        size.setObjectName("bpMeta")
        text = self._size_text(bp.get("size"))
        if scene.Fit(bp.get("size"), self._win._WL, self._win._HL).same:
            size.setText(text)
        else:
            size.setText(text + " ⚠")
            _set_prop(size, "warn", True)
            install_tip(size, t("bp_other_screen", size=text))
        meta.addWidget(size)
        col.addLayout(meta)

        btns = QHBoxLayout()
        btns.addStretch(1)
        for key, kind, slot in (
            ("bp_load", "btnPrimary", self._on_load),
            ("bp_overwrite", "btnGhost", self._on_overwrite),
            ("bp_rename", "btnGhost", self._on_rename),
            ("bp_delete", "btnDanger", self._on_delete),
        ):
            b = QPushButton(t(key))
            b.setObjectName(kind)
            b.clicked.connect(lambda _c=False, f=slot, x=bp: f(x))
            btns.addWidget(b)
        col.addLayout(btns)
        return card

    def _size_text(self, size):
        """逻辑尺寸按画布缩放换回屏幕像素显示。"""
        s = self._win._scale or 1.0
        try:
            return f"{round(float(size[0]) * s)}×{round(float(size[1]) * s)}"
        except (TypeError, ValueError, IndexError):
            return "?"

    def _set_status(self, text="", warn=False):
        self._status.setText(text)
        _set_prop(self._status, "warn", warn)

    # 预览

    def _on_pick(self, bp):
        if self._renaming is not None:
            return
        self._set_status()
        if bp is self._sel and self._previewing:
            self._sel = None
            self._show(None)
        else:
            self._sel = bp
            self._show(bp)
        self._rebuild()

    def _show(self, bp):
        self._previewing = bp is not None
        self._win.set_ghosts(scene.build(self._win, bp, blueprint=True) if bp is not None else None)

    # 操作

    def _scene_or_warn(self):
        data = scene.capture(self._win, blueprint=True)
        if not data["items"]:
            self._set_status(t("bp_empty_scene"), warn=True)
            return None
        return data

    def _on_new(self):
        bps = self._bps()
        if len(bps) >= scene.BLUEPRINT_CAP:
            return
        data = self._scene_or_warn()
        if data is None:
            return
        self._set_status()
        names = {b.get("name") for b in bps}
        n = 1
        while t("bp_default_name", n=n) in names:
            n += 1
        bp = {"name": t("bp_default_name", n=n), **data}
        bps.append(bp)
        self._write_state()
        self._rebuild(rename=bp)
        self._focus_rename()

    def _on_load(self, bp):
        self._set_status()
        scene.restore(self._win, bp, blueprint=True)
        self._sel = bp
        self._show(None)
        self._rebuild()

    def _on_overwrite(self, bp):
        if self._scene_or_warn() is None:
            return
        self._confirm(
            "bp_overwrite_title",
            t("bp_overwrite_text", name=bp.get("name", "")),
            "bp_overwrite",
            bp,
            self._overwrite,
        )

    def _overwrite(self, bp):
        data = self._scene_or_warn()
        if data is None:
            return
        bp.update(data)
        self._write_state()
        if bp is self._sel and self._previewing:
            self._show(bp)
        self._rebuild()

    def _on_rename(self, bp):
        self._set_status()
        self._rebuild(rename=bp)
        self._focus_rename()

    def _focus_rename(self):
        if self._renaming is not None:
            self._renaming.setFocus()
            self._renaming.selectAll()

    def _finish_rename(self, bp, text):
        text = text.strip()
        if text and text != bp.get("name"):
            bp["name"] = text
            self._write_state()
        self._rebuild()

    def _on_delete(self, bp):
        self._confirm(
            "bp_delete_title", t("bp_delete_text", name=bp.get("name", "")), "bp_delete", bp, self._delete
        )

    def _delete(self, bp):
        bps = self._bps()
        i = next((i for i, b in enumerate(bps) if b is bp), None)
        if i is not None:
            del bps[i]
            self._write_state()
        if bp is self._sel:
            self._sel = None
            self._show(None)
        self._rebuild()

    def _confirm(self, title_key, text, ok_key, bp, then):
        if self._sub is not None:
            return
        dlg = ConfirmDialog(t(title_key), text, t(ok_key), t("settings_cancel"), parent=self)
        self._sub = dlg

        def finished(result):
            self._sub = None
            dlg.deleteLater()
            if result == dlg.DialogCode.Accepted:
                then(bp)

        dlg.finished.connect(finished)
        dlg.place_center(self)
        dlg.open()

    def done(self, result):
        if self._finished:
            return
        self._win.set_ghosts(None)
        super().done(result)
