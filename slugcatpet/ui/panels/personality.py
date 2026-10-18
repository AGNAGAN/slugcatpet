"""性格弹窗：精力、亲和两根滑条，改动即时生效，完成保留，取消还原。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider

from ...characters.personality import AXES
from ...i18n import t
from ..theme import qss
from ..widgets.dialogs import CardDialog
from .catmenu import pet_label

DIALOG_W = 340
SCALE = 100


class PersonalityDialog(CardDialog):
    def __init__(self, pet, title, parent=None):
        super().__init__(t("pers_title", name=title), parent, width=DIALOG_W)
        self._card.setStyleSheet(qss.LOOK_DIALOG + qss.SLIDER)
        self._pet = pet
        self._orig = dict(pet.personality)
        self._sliders = {}
        for a in AXES:
            self._axis_row(a)
        if pet.cat.personality.vary > 0.0:
            hint = QLabel(t("pers_hint_vary"))
            hint.setObjectName("cardText")
            hint.setWordWrap(True)
            self.body.addWidget(hint)

        self._btn_row.takeAt(0)  # 恢复默认靠左，另两个靠右
        reset = self.add_button(t("pers_reroll" if pet.cat.personality.vary > 0.0 else "pers_reset"), "ghost")
        reset.clicked.connect(self._on_reset)
        self._btn_row.addStretch(1)
        cancel = self.add_button(t("settings_cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        ok = self.add_button(t("skin_done"), "primary")
        ok.clicked.connect(self.accept)

    def _axis_row(self, a):
        head = QLabel(t(f"pers_{a}"))
        head.setObjectName("lookHead")
        self.body.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(8)
        lo = QLabel(t(f"pers_{a}_lo"))
        lo.setObjectName("cardText")
        hi = QLabel(t(f"pers_{a}_hi"))
        hi.setObjectName("cardText")
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(0, SCALE)
        sl.setValue(round(self._pet.personality[a] * SCALE))
        sl.valueChanged.connect(lambda _n: self._apply())
        row.addWidget(lo)
        row.addWidget(sl, 1)
        row.addWidget(hi)
        self.body.addLayout(row)
        self._sliders[a] = sl

    def _axes(self):
        return {a: sl.value() / SCALE for a, sl in self._sliders.items()}

    def _apply(self):
        self._pet.set_personality(self._axes())

    def _on_reset(self):
        axes = self._pet.default_personality()
        for a, sl in self._sliders.items():
            sl.blockSignals(True)
            sl.setValue(round(axes[a] * SCALE))
            sl.blockSignals(False)
        self._pet.set_personality(axes)

    def reject(self):
        self._pet.set_personality(self._orig)
        super().reject()


def open_personality(pet, pets, parent=None):
    """打开这只猫的性格弹窗；已开着就提到前面。"""
    w = pet.window
    dlg = getattr(w, "_personality_dlg", None)
    if dlg is not None:
        dlg.raise_()
        dlg.activateWindow()
        return dlg
    dlg = PersonalityDialog(pet, pet_label(pet, pets), parent=parent)

    def finished(_r):
        w._personality_dlg = None
        dlg.deleteLater()
        w._after_pets_changed()

    dlg.finished.connect(finished)
    w._personality_dlg = dlg
    dlg.place_center(parent)
    dlg.show()
    return dlg
