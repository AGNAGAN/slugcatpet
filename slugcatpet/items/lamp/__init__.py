"""暖灯：从最近的屏幕边伸出一根杆挂着灯泡；只有一盏，能取暖。"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPainterPathStroker, QRadialGradient

from ...core.units import clampf
from ...core.vecmath import _seg_dist
from ...rendering.primitives import draw_fruit, draw_rope
from ..base import WARM, ItemKind
from ..state import ItemState
from .model import Lamp

LAMP_STICK_COLOR = (0, 0, 0)
LAMP_BULB_FLESH = (255, 255, 255)
LAMP_BULB_OUTLINE = (255, 51, 0)
LAMP_GLOW_COLOR = (255, 51, 0)
LAMP_GLOW_ALPHA = 130
LAMP_TILT_MAX_DEG = 25.0
LAMP_STICK_OUTSET = 40.0
LAMP_HIT_STICK = 3.0  # 灯杆命中半宽
LAMP_HIT_BULB = 8.0  # 灯泡命中半径

_ICON_OUTLINE = QColor(255, 70, 20)
_ICON_FLESH = QColor(255, 248, 230)
_ICON_AMBER = QColor(233, 203, 138)


def _geom(win, lx, ly):
    d = {"top": ly, "bottom": win._HL - ly, "left": lx, "right": win._WL - lx}
    edge = min(d, key=d.get)
    off = d[edge] * math.tan(math.radians(getattr(win, "_lamp_tilt", 0.0)))
    if edge == "top":
        ax, ay = clampf(lx + off, 0.0, win._WL), 0.0
    elif edge == "bottom":
        ax, ay = clampf(lx + off, 0.0, win._WL), win._HL
    elif edge == "left":
        ax, ay = 0.0, clampf(ly + off, 0.0, win._HL)
    else:
        ax, ay = win._WL, clampf(ly + off, 0.0, win._HL)
    vx, vy = ax - lx, ay - ly
    vlen = math.hypot(vx, vy) or 1.0
    ax += vx / vlen * LAMP_STICK_OUTSET
    ay += vy / vlen * LAMP_STICK_OUTSET
    return ax, ay, lx, ly, edge


def _shape(p, atlas, ax, ay, bx, by, opacity, glow_radius=None):
    p.save()
    if opacity < 1.0:
        p.setOpacity(opacity)
    dx, dy = bx - ax, by - ay
    seg_len = math.hypot(dx, dy)
    bulb_rot = 0.0
    if seg_len > 1.0:
        ux, uy = dx / seg_len, dy / seg_len
        root_w = 1.0 + min(seg_len / 190.0, 3.0)
        sx, sy = ax + ux * 5.0, ay + uy * 5.0
        tx, ty = bx + ux * 25.0, by + uy * 25.0
        n = 8
        pts = [(sx + (tx - sx) * i / (n - 1), sy + (ty - sy) * i / (n - 1)) for i in range(n)]
        widths = [2.0 * (root_w + (0.5 - root_w) * (i / (n - 1))) for i in range(n)]
        draw_rope(p, pts, widths, color=LAMP_STICK_COLOR)
        bulb_rot = math.degrees(math.atan2(ax - bx, by - ay))
    draw_fruit(
        p,
        atlas,
        bx,
        by,
        bulb_rot,
        3,
        flesh_color=LAMP_BULB_FLESH,
        outline_color=LAMP_BULB_OUTLINE,
        scalex=0.8,
        scaley=0.9,
    )
    if glow_radius and glow_radius > 1.0:
        grad = QRadialGradient(QPointF(bx, by), glow_radius)
        grad.setColorAt(0.0, QColor(*LAMP_GLOW_COLOR, LAMP_GLOW_ALPHA))
        grad.setColorAt(1.0, QColor(*LAMP_GLOW_COLOR, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(bx, by), glow_radius, glow_radius)
    p.restore()


class LampKind(ItemKind):
    key = "lamp"
    store = "lamp"
    single = True
    cap = None
    affords = frozenset({WARM})
    layer = "top"
    mobile = False
    late_tick = True
    geometry = True
    dead_state = ItemState.GONE

    def make(self, win, lx, ly, seed):
        ax, ay, bx, by, edge = _geom(win, lx, ly)
        return Lamp(ax, ay, bx, by, edge, seed=seed)

    def on_enter_place(self, win):
        win._lamp_tilt = random.uniform(-LAMP_TILT_MAX_DEG, LAMP_TILT_MAX_DEG)

    def tick(self, win):
        if win.lamp is not None:
            win.lamp.step()

    def hit(self, lamp, cx, cy):
        return min(
            max(
                0.0,
                _seg_dist(cx, cy, lamp.anchor_x, lamp.anchor_y, lamp.bulb_x, lamp.bulb_y) - LAMP_HIT_STICK,
            ),
            math.hypot(cx - lamp.bulb_x, cy - lamp.bulb_y) - LAMP_HIT_BULB,
        )

    def draw_mark(self, p, lamp, rad):
        band = QPainterPath()
        band.moveTo(lamp.anchor_x, lamp.anchor_y)
        band.lineTo(lamp.bulb_x, lamp.bulb_y)
        outline = QPainterPathStroker()
        outline.setWidth(12.0)
        outline.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.drawPath(outline.createStroke(band))
        p.drawEllipse(QPointF(lamp.bulb_x, lamp.bulb_y), rad, rad)

    def floor_shift(self, win, old, new):
        lamp = win.lamp
        if lamp is not None and lamp.edge == "bottom":
            lamp.anchor_y += new - old
            lamp.bulb_y += new - old

    def draw(self, win, p):
        lamp = win.lamp
        _shape(
            p,
            win.atlas,
            lamp.anchor_x,
            lamp.anchor_y,
            lamp.bulb_x,
            lamp.bulb_y,
            1.0,
            glow_radius=lamp.glow_radius(),
        )

    def draw_hint(self, win, p, cx, cy):
        ax, ay, bx, by, _ = _geom(win, cx, cy)
        _shape(p, win.atlas, ax, ay, bx, by, 0.5)

    def paint_icon(self, p, r, atlas):
        cx, cy = r.center().x(), r.center().y()
        w, h = r.width(), r.height()
        if atlas is None or not atlas.get("base").has("DangleFruit0A"):
            from ...ui.widgets.iconkit import pen

            d = w * 0.42
            bulb = QRectF(0, 0, d, d)
            bulb.moveCenter(QPointF(cx, cy))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_ICON_AMBER)
            p.drawEllipse(bulb)
            p.setPen(pen(_ICON_AMBER, max(1.4, w * 0.08)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            bc, rad = bulb.center(), d / 2
            for k in range(8):
                a = math.radians(22.5 + 45 * k)
                p.drawLine(
                    QPointF(bc.x() + math.cos(a) * (rad + w * 0.05), bc.y() - math.sin(a) * (rad + w * 0.05)),
                    QPointF(bc.x() + math.cos(a) * (rad + w * 0.18), bc.y() - math.sin(a) * (rad + w * 0.18)),
                )
            return
        glow_r = min(w, h) * 0.52
        grad = QRadialGradient(QPointF(cx, cy), glow_r)
        grad.setColorAt(0.0, QColor(255, 150, 70, 165))
        grad.setColorAt(0.45, QColor(255, 100, 35, 80))
        grad.setColorAt(1.0, QColor(255, 70, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)
        sw, sh = atlas.source_size("base", "DangleFruit0A")
        s = min(w / sw, h / sh) * 0.58
        dw, dh = sw * s, sh * s
        outline = atlas.sprite("base", "DangleFruit0A", _ICON_OUTLINE)
        flesh = atlas.sprite("base", "DangleFruit0B", _ICON_FLESH)
        p.save()  # 镜像：粗头朝上
        p.translate(cx, cy)
        p.scale(1.0, -1.0)
        local = QRectF(-dw / 2, -dh / 2, dw, dh)
        p.drawPixmap(local, outline, QRectF(outline.rect()))
        p.drawPixmap(local, flesh, QRectF(flesh.rect()))
        p.restore()


KIND = LampKind()
