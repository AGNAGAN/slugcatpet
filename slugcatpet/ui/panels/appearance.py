"""设置页「皮肤」区块与单只猫的外观弹窗。"""
from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QRadioButton, QWidget)

from ... import i18n, skins
from ...accessories import BUILTIN as ACCESSORIES
from ...appearance import accessory_color
from ...i18n import t
from ...skins.folder import ensure_folder
from ..theme import qss
from ..widgets.dialogs import CardDialog


def open_skin_folder(window):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(ensure_folder(window.atlas))))


def build_skin_section(settings, v):
    v.addWidget(settings._header(t("settings_skins_section")))

    b = QPushButton(t("settings_skins_open"))
    b.clicked.connect(lambda: open_skin_folder(settings._window))
    v.addWidget(b)

    chk = QCheckBox(t("settings_skins_scan"))
    chk.setChecked(skins.scan_external())

    def on_scan(checked):
        skins.configure(checked)
        settings._window.reload_skins()
        settings._write_state()
        settings._rebuild()
    chk.toggled.connect(on_scan)
    v.addWidget(chk)

    n_bad = len(skins.problems())
    text = t("settings_skins_status", n=len(skins.packs()))
    if n_bad:
        text += t("settings_skins_status_bad", n=n_bad)
    lab = QLabel(text)
    lab.setStyleSheet(qss.ERROR_TEXT if n_bad else qss.DIM_TEXT)
    v.addWidget(lab)


class AppearanceDialog(CardDialog):
    """改动即时生效，完成=保留，取消=还原。"""

    def __init__(self, pet, parent=None):
        super().__init__(t("look_button"), parent, width=340)
        self._card.setStyleSheet(qss.LOOK_DIALOG)
        pet.window.reload_skins(force=False)
        self._pet = pet
        self._orig = pet.look.copy()
        self._look = pet.look.copy()

        self.body.addWidget(_head(t("look_skin")))
        self.list = QListWidget()
        self.list.setMinimumHeight(240)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._fill_skins(pet.cat.key)
        self.list.currentItemChanged.connect(self._on_skin)
        self.body.addWidget(self.list)

        self._color_block()
        self._acc_block()

        cancel = self.add_button(t("settings_cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        ok = self.add_button(t("skin_done"), "primary")
        ok.clicked.connect(self.accept)

    def _fill_skins(self, species):
        self._add(t("skin_original"), "")
        groups = {}
        for p in skins.packs():
            groups.setdefault(p.collection, []).append(p)
        key = (lambda p: (species[:4] not in (p.name + p.id).lower(), p.name.lower()))
        loose = groups.pop("", [])
        for name in [n for n in groups if len(groups[n]) == 1]:
            loose += groups.pop(name)
        for p in sorted(loose, key=key):
            self._add(_label(p), p.id)
        for name in sorted(groups, key=str.lower):
            head = QListWidgetItem(name)
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            f = QFont()
            f.setBold(True)
            head.setFont(f)
            self.list.addItem(head)
            for p in sorted(groups[name], key=key):
                self._add("    " + _label(p), p.id)
        cur = self._look.skin or ""
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == cur:
                self.list.setCurrentRow(i)
                break

    def _add(self, text, sid):
        it = QListWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, sid)
        self.list.addItem(it)

    def _on_skin(self, item, _prev=None):
        if item is None:
            return
        self._look.skin = item.data(Qt.ItemDataRole.UserRole) or None
        self._apply()

    def _color_block(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_head(t("look_color")))
        self.rb_default = QRadioButton(t("look_default"))
        self.rb_custom = QRadioButton(t("look_custom"))
        grp = QButtonGroup(self)
        for rb in (self.rb_default, self.rb_custom):
            grp.addButton(rb)
            row.addWidget(rb)
        row.addStretch(1)
        (self.rb_custom if self._look.colors else self.rb_default).setChecked(True)
        self.rb_custom.toggled.connect(self._on_custom)
        self.body.addLayout(row)

        self.swatch_box = QWidget()
        sw = QHBoxLayout(self.swatch_box)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(8)
        self.swatch = {}
        for k, lk in (("body", "look_body"), ("face", "look_face")):
            sw.addWidget(_text(t(lk)))
            b = _swatch()
            b.clicked.connect(lambda _c=False, key=k: self._pick_color(key))
            self.swatch[k] = b
            sw.addWidget(b)
        sw.addStretch(1)
        self.swatch_box.setVisible(bool(self._look.colors))
        self._paint_colors()
        self.body.addWidget(self.swatch_box)

    def _on_custom(self, on):
        if on and not self._look.colors:
            g = self._pet.gfx
            self._look.colors = {"body": tuple(g._body0), "face": tuple(g.EYE)}
        elif not on:
            self._look.colors = None
        self.swatch_box.setVisible(on)
        self._paint_colors()
        self._card.adjustSize()
        self.adjustSize()
        self._apply()

    def _paint_colors(self):
        if self._look.colors:
            for k, b in self.swatch.items():
                _paint(b, self._look.colors[k])

    def _pick_color(self, k):
        c = QColorDialog.getColor(QColor(*self._look.colors[k]), self)
        if c.isValid():
            self.set_color(k, (c.red(), c.green(), c.blue()))

    def set_color(self, k, rgb):
        self._look.colors[k] = tuple(rgb)
        self._paint_colors()
        self._apply()

    def _acc_block(self):
        self.body.addWidget(_head(t("look_accessories")))
        self.acc_check = {}
        self.acc_swatch = {}
        for cls in ACCESSORIES:
            row = QHBoxLayout()
            row.setSpacing(8)
            chk = QCheckBox(cls.title.get(i18n.LANG) or cls.title["en"])
            chk.setChecked(self._look.wears(cls, self._pet.cat.key))
            chk.toggled.connect(lambda on, c=cls: self._on_acc(c, on))
            row.addWidget(chk, 1)
            b = _swatch()
            b.clicked.connect(lambda _c=False, c=cls: self._pick_acc_color(c))
            row.addWidget(b)
            self.acc_check[cls.key] = chk
            self.acc_swatch[cls.key] = b
            self.body.addLayout(row)
            self._paint_acc(cls)

    def _on_acc(self, cls, on):
        self._look.accessories.setdefault(cls.key, {})["on"] = on
        self._apply()

    def _acc_now(self, cls):
        probe = SimpleNamespace(color=self._look.acc_color(cls.key), color_group=cls.color_group,
                                default_color=cls.default_color)
        return accessory_color(probe, self._pet.gfx._skin_colors)

    def _paint_acc(self, cls):
        _paint(self.acc_swatch[cls.key], self._acc_now(cls))

    def _pick_acc_color(self, cls):
        c = QColorDialog.getColor(QColor(*self._acc_now(cls)), self)
        if c.isValid():
            self.set_acc_color(cls, (c.red(), c.green(), c.blue()))

    def set_acc_color(self, cls, rgb):
        self._look.accessories.setdefault(cls.key, {})["color"] = tuple(rgb)
        self._apply()

    def _apply(self):
        self._pet.set_look(self._look.copy())
        for cls in ACCESSORIES:
            self._paint_acc(cls)

    def reject(self):
        self._pet.set_look(self._orig)
        super().reject()


def _head(text):
    lab = QLabel(text)
    lab.setObjectName("lookHead")
    return lab


def _text(text):
    lab = QLabel(text)
    lab.setObjectName("cardText")
    return lab


def _swatch():
    b = QPushButton()
    b.setObjectName("swatch")
    return b


def _paint(b, c):
    r, g, bl = c
    hexs = f"#{r:02X}{g:02X}{bl:02X}"
    fg = "#000" if (r * 0.3 + g * 0.59 + bl * 0.11) > 128 else "#fff"
    b.setText(hexs)
    b.setStyleSheet(f"background:{hexs};color:{fg};")


def _label(p) -> str:
    return p.name + ("  ⚠" if p.missing or p.rejected else "")
