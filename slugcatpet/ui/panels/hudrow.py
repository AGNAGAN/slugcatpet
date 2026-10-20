"""HUD 里一只猫的一行：体征，左键弹菜单，拖动移 HUD。"""

from __future__ import annotations
import math
import time

from PySide6.QtWidgets import QWidget, QLabel, QGridLayout, QFrame
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath

from ... import tuning
from ...i18n import t
from .catmenu import pet_label
from ..widgets.tips import install as install_tip
from ..theme import palette

KARMA_ICON = 22
BAR_W, BAR_H = 88, 10
PIP = 12
_DRAG_THRESH = 3  # 小于此判定点击而非拖动
QUARTER_FPS = 40.0  # 1/4 格呼吸与亮起按这个帧率换算
QUARTER_PULSE = 20.0  # 呼吸正弦的帧数缩放
QUARTER_ALPHA = (0.2, 0.5)  # 呼吸透明度范围
QUARTER_LIT = 0.6  # 刚攒到一个 1/4 时亮到这么不透明
QUARTER_LIT_DECAY = 0.95  # 亮起每帧衰减

_BAR_BG = palette.BAR_BG
_BAR_FG = palette.BAR_FG
_ICY = palette.BAR_ICY
_OXY = palette.BAR_OXY


class _Bar(QWidget):
    def __init__(self, fg=None):
        super().__init__()
        self.setFixedSize(BAR_W, BAR_H)
        self._ratio = 0.0
        self._fg = fg if fg is not None else _BAR_FG

    def set_ratio(self, r):
        r = max(0.0, min(1.0, float(r)))
        if r != self._ratio:
            self._ratio = r
            self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_BAR_BG)
        p.drawRoundedRect(0, 0, BAR_W, BAR_H, 4, 4)
        w = int(BAR_W * self._ratio)
        if w > 0:
            p.setBrush(self._fg)
            p.drawRoundedRect(0, 0, max(w, 4), BAR_H, 4, 4)
        p.end()


class _Pips(QWidget):
    """饱食格：满的实心，下一格按攒着的 1/4 画扇形，呼吸闪烁。"""

    def __init__(self, total):
        super().__init__()
        self._total = int(total)
        self._filled = 0
        self._quarters = 0
        self._lit_at = None  # 最近一次多攒一个 1/4 的时刻
        gap = 4
        self.setFixedSize(self._total * PIP + (self._total - 1) * gap, PIP)
        self._gap = gap

    def set_filled(self, n, quarters=0):
        n = max(0, min(self._total, int(n)))
        q = max(0, min(3, int(quarters))) if n < self._total else 0
        if q > self._quarters:
            self._lit_at = time.monotonic()
        changed = (n, q) != (self._filled, self._quarters)
        self._filled, self._quarters = n, q
        if changed or q:
            self.update()

    def _quarter_alpha(self):
        now = time.monotonic()
        s = 0.5 + 0.5 * math.sin(now * QUARTER_FPS / QUARTER_PULSE)
        lo, hi = QUARTER_ALPHA
        a = lo + (hi - lo) * s**0.4
        if self._lit_at is not None:
            lit = QUARTER_LIT_DECAY ** ((now - self._lit_at) * QUARTER_FPS)
            a += (QUARTER_LIT - a) * lit * lit
        return a

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        x = 0
        for i in range(self._total):
            p.setBrush(_BAR_FG if i < self._filled else _BAR_BG)
            p.drawRoundedRect(x, 0, PIP, PIP, 3, 3)
            if i == self._filled and self._quarters:
                self._draw_quarters(p, x)
            x += PIP + self._gap
        p.end()

    def _draw_quarters(self, p, x):
        """从 12 点顺时针画 1/4、2/4、3/4 的扇形，裁在格子里。"""
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, 0, PIP, PIP), 3, 3)
        p.save()
        p.setClipPath(clip)
        c = QColor(_BAR_FG)
        c.setAlphaF(self._quarter_alpha())
        p.setBrush(c)
        r = PIP * 0.75
        p.drawPie(QRectF(x + PIP / 2 - r, PIP / 2 - r, 2 * r, 2 * r), 90 * 16, -self._quarters * 90 * 16)
        p.restore()


class PetRow(QFrame):
    def __init__(self, pet, hud):
        super().__init__()
        self.pet = pet
        self.hud = hud
        self.setObjectName("hudRow")
        self._drag_from = None
        self._start_tl = None
        self._moved = False
        self._build()
        self.refresh()

    def _build(self):
        grid = QGridLayout(self)
        grid.setContentsMargins(4, 3, 4, 3)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        def name_lbl(text):
            lbl = QLabel(text)
            lbl.setObjectName("hudName")
            return lbl

        self.name = QLabel()
        self.name.setObjectName("hudRowName")
        grid.addWidget(self.name, 0, 0, 1, 3)

        self.karma_icon = QLabel()
        self.karma_icon.setFixedSize(KARMA_ICON, KARMA_ICON)
        self.karma_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.karma_val = QLabel()
        self.karma_val.setObjectName("hudVal")
        grid.addWidget(name_lbl(t("hud_karma")), 1, 0)
        grid.addWidget(self.karma_icon, 1, 1)
        grid.addWidget(self.karma_val, 1, 2)

        self.stam_bar = _Bar()
        grid.addWidget(name_lbl(t("hud_stamina")), 2, 0)
        grid.addWidget(self.stam_bar, 2, 1)

        self.food_pips = _Pips(self.pet.body.food_max)
        grid.addWidget(name_lbl(t("hud_satiety")), 3, 0)
        grid.addWidget(self.food_pips, 3, 1)

        self.temper_bar = _Bar()
        grid.addWidget(name_lbl(t("hud_affection")), 4, 0)
        grid.addWidget(self.temper_bar, 4, 1)

        self.cold_lbl = name_lbl(t("hud_cold"))
        self.cold_bar = _Bar(fg=_ICY)
        grid.addWidget(self.cold_lbl, 5, 0)
        grid.addWidget(self.cold_bar, 5, 1)
        self._cold_visible = False
        self._karma_frame = None  # 已显示的帧名，没变不重设
        self.cold_lbl.setVisible(False)
        self.cold_bar.setVisible(False)

        self.air_lbl = name_lbl(t("hud_air"))  # 有水时才显示
        self.air_bar = _Bar(fg=_OXY)
        grid.addWidget(self.air_lbl, 6, 0)
        grid.addWidget(self.air_bar, 6, 1)
        self._air_visible = False
        self.air_lbl.setVisible(False)
        self.air_bar.setVisible(False)

        install_tip(self, self._tip_text)

    def _tip_text(self):
        parts = [t("hud_karma"), t("hud_stamina"), t("hud_satiety"), t("hud_affection")]
        if self._cold_visible:
            parts.append(t("hud_cold"))
        if self._air_visible:
            parts.append(t("hud_air"))
        return " · ".join(parts) + "\n" + t("hud_op_hint")

    def refresh(self) -> bool:
        """刷新本行，返回尺寸是否可能变了（名字、寒冷 / 氧气条显隐）。"""
        pets = list(getattr(self.pet.window, "pets", [self.pet]))
        label = pet_label(self.pet, pets) + (t("hud_held") if self.pet.held is not None else "")
        renamed = label != self.name.text()
        if renamed:
            self.name.setText(label)
        body = self.pet.body

        k = int(body.karma)
        frame = f"smallKarma{k}" if k <= 4 else f"smallKarma{k}-9"
        if frame != self._karma_frame:
            pm = self._karma_sprite(frame)
            if pm is not None and not pm.isNull():
                self.karma_icon.setPixmap(pm)
                self._karma_frame = frame
        kmax = int(getattr(body, "karma_max", tuning.KARMA_MAX))
        self.karma_val.setText(f"{k + 1}/{kmax + 1}")

        self.stam_bar.set_ratio(max(0.0, min(1.0, float(body.energy))))
        self.food_pips.set_filled(body.food, body.food_q)
        self.temper_bar.set_ratio((max(-1.0, min(1.0, float(body.temper))) + 1.0) * 0.5)

        cold = float(getattr(body, "cold", 0.0))
        show_cold = cold > 0.001 or bool(getattr(self.pet.window, "blizzard_on", False))
        changed = show_cold != self._cold_visible
        if changed:
            self._cold_visible = show_cold
            self.cold_lbl.setVisible(show_cold)
            self.cold_bar.setVisible(show_cold)
        if show_cold:
            self.cold_bar.set_ratio(max(0.0, min(1.0, cold)))

        show_air = getattr(self.pet.window, "water_surface", None) is not None
        if show_air != self._air_visible:
            changed = True
            self._air_visible = show_air
            self.air_lbl.setVisible(show_air)
            self.air_bar.setVisible(show_air)
        if show_air:
            self.air_bar.set_ratio(max(0.0, min(1.0, float(body.air_frac))))
        return changed or renamed

    def _karma_sprite(self, frame):
        atlas = getattr(self.pet.window, "atlas", None)
        if atlas is None:
            return None
        try:
            pm = atlas.sprite("ui", frame)
        except Exception:
            return None
        if pm.isNull():
            return pm
        if pm.width() > KARMA_ICON or pm.height() > KARMA_ICON:
            pm = pm.scaled(
                KARMA_ICON,
                KARMA_ICON,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return pm

    def _hud_point(self, ev):
        """事件点 → HUD 所在坐标；嵌入时是 overlay 本地坐标。"""
        if getattr(self.hud, "_embedded", False):
            return self.mapTo(self.hud, ev.position().toPoint())
        return ev.globalPosition().toPoint()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_from = self._hud_point(ev)
            self._start_tl = (
                self.hud.pos()
                if getattr(self.hud, "_embedded", False)
                else self.hud.frameGeometry().topLeft()
            )
            self._moved = False
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_from is None or not (ev.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = self._hud_point(ev) - self._drag_from
        if not self._moved and delta.manhattanLength() <= _DRAG_THRESH:
            return
        self._moved = True
        self.hud._move_to(self._start_tl + delta)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._drag_from is not None:
            moved = self._moved
            self._drag_from = None
            if not moved:
                host = self.pet.window
                if getattr(self.hud, "_embedded", False):
                    local = self.mapTo(host, ev.position().toPoint())
                    host.open_cat_menu(self.pet, local, local=True)
                else:
                    host.open_cat_menu(self.pet, ev.globalPosition().toPoint())
            ev.accept()
