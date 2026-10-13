"""果子：高处放挂在果柄上，低处放散落；能吃、能叼。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from ...rendering.graphics import _ang_from_up
from ...rendering.primitives import draw_fruit, draw_rope
from ..base import CARRYABLE, EDIBLE, ItemKind
from ..state import ItemState
from .model import PLACE_HANGING_FRAC, make_fruit

STALK_ROOT_W = 3.0
STALK_TIP_W = 2.0
STALK_COLOR = (0, 0, 0)
FRUIT_FLESH = (0, 0, 255)
FRUIT_OUTLINE = (0, 0, 0)

_ICON_TOP = QColor(140, 185, 255)
_ICON_BOT = QColor(28, 64, 210)
_ICON_OUTLINE = QColor(22, 26, 44)


class FruitKind(ItemKind):
    key = "fruit"
    store = "fruits"
    affords = frozenset({EDIBLE, CARRYABLE})
    collides = True
    grab_pad = 7.0
    grab_states = (ItemState.FREE, ItemState.HANGING)
    grab_rank = 2
    splash_states = (ItemState.FREE, ItemState.HANGING)

    def make(self, win, lx, ly, seed):
        return make_fruit(lx, ly, win._HL, seed=seed, zerog=win.zerog_on)

    def drop(self, win, f):
        f.stalk = None
        for pet in win.pets:
            pet.body.release(f)
        f.held_by_hand = None
        f.state = ItemState.EATEN

    def on_grab(self, f):
        f.stalk = None
        f.held_by_hand = None

    def on_zerog(self, win):
        for f in win.fruits:
            f.stalk = None
            if f.state == ItemState.HANGING:
                f.state = ItemState.FREE

    def draw_under(self, win, p):
        ts = win._ts
        for f in win.fruits:
            st = f.stalk
            if st is None:
                continue
            pts = [st.stuck_pos]
            for s in st.segs:
                pts.append((s[2] + (s[0] - s[2]) * ts, s[3] + (s[1] - s[3]) * ts))
            n = len(pts)
            if n < 2:
                continue
            pts[-1] = (f.last_x + (f.x - f.last_x) * ts, f.last_y + (f.y - f.last_y) * ts)
            widths = [STALK_ROOT_W + (STALK_TIP_W - STALK_ROOT_W) * (i / (n - 1)) for i in range(n)]
            draw_rope(p, pts, widths, color=STALK_COLOR)

    def draw(self, win, p):
        ts = win._ts
        for f in win.fruits:
            x = f.last_x + (f.x - f.last_x) * ts
            y = f.last_y + (f.y - f.last_y) * ts
            rx, ry = f.rotation
            draw_fruit(
                p,
                win.atlas,
                x,
                y,
                _ang_from_up(rx, ry),
                f.bites,
                flesh_color=FRUIT_FLESH,
                outline_color=FRUIT_OUTLINE,
            )

    def draw_guide(self, win, p):
        if not win.zerog_on:  # 这条线以上放的会挂起来
            p.save()
            p.setPen(QPen(QColor(255, 255, 255, 110), 1.0, Qt.PenStyle.DashLine))
            yline = win._HL * PLACE_HANGING_FRAC
            p.drawLine(QPointF(0.0, yline), QPointF(win._WL, yline))
            p.restore()

    def draw_hint(self, win, p, cx, cy):
        p.save()
        p.setOpacity(0.5)
        draw_fruit(p, win.atlas, cx, cy, 0.0, 3, flesh_color=FRUIT_FLESH, outline_color=FRUIT_OUTLINE)
        p.restore()

    def paint_icon(self, p, r, atlas):
        if atlas is None or not atlas.get("base").has("DangleFruit0A"):
            _icon_fallback(p, r)
            return
        sw, sh = atlas.source_size("base", "DangleFruit0A")
        s = min(r.width() / sw, r.height() / sh) * 0.8
        dw, dh = sw * s, sh * s
        dst = QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh)
        outline = atlas.sprite("base", "DangleFruit0A", _ICON_OUTLINE)
        flesh = atlas.sprite("base", "DangleFruit0B")  # 白模，下面渐变上色
        ss = 4
        lw, lh = max(1, int(dw * ss)), max(1, int(dh * ss))
        layer = QPixmap(lw, lh)
        layer.fill(Qt.GlobalColor.transparent)
        lp = QPainter(layer)
        lp.drawPixmap(QRectF(0, 0, lw, lh), flesh, QRectF(flesh.rect()))
        lp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        g = QLinearGradient(QPointF(0, 0), QPointF(0, lh))
        g.setColorAt(0.0, _ICON_TOP)
        g.setColorAt(1.0, _ICON_BOT)
        lp.fillRect(layer.rect(), g)
        lp.end()
        p.drawPixmap(dst, outline, QRectF(outline.rect()))
        p.drawPixmap(dst, layer, QRectF(layer.rect()))


def _icon_fallback(p, r):
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    path = QPainterPath()
    path.moveTo(QPointF(cx, r.top()))
    path.cubicTo(
        QPointF(cx + w * 0.50, cy - h * 0.10), QPointF(cx + w * 0.42, r.bottom()), QPointF(cx, r.bottom())
    )
    path.cubicTo(
        QPointF(cx - w * 0.42, r.bottom()), QPointF(cx - w * 0.50, cy - h * 0.10), QPointF(cx, r.top())
    )
    g = QLinearGradient(QPointF(0, r.top()), QPointF(0, r.bottom()))
    g.setColorAt(0.0, _ICON_TOP)
    g.setColorAt(1.0, _ICON_BOT)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)


KIND = FruitKind()
