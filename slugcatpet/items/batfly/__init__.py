"""蝙蝠：乱飞、被叼挣扎、可被吃。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF

from ...core.units import clampf, inv_lerp, lerp
from ...rendering.graphics import _ang_from_up
from ..base import CARRYABLE, EDIBLE, ItemKind
from ..state import ItemState
from .model import BatFly

BATFLY_BLACK = (0, 0, 0)
BATFLY_EYE_COLOR = (250, 250, 235)
BATFLY_WING_COLOR = (0, 0, 0, 160)
BATFLY_BODY_HALF_W = 2.7
BATFLY_BODY_HALF_H = 3.3
BATFLY_ABDOMEN_MIN = 4.0
BATFLY_ABDOMEN_MAX = 6.0
BATFLY_WING_LEN = 12.5
BATFLY_WING_W = 6.0
BATFLY_EYE_RAD = 0.5
BATFLY_EYE_DX = 0.92
BATFLY_EYE_DY = 1.35
SHOVE_REACH = 22.0
SHOVE_COOLDOWN = 12
# 翅本地多边形（锚在本体，向 -y 伸展）
_WING_PTS = [
    (0.0, 0.0),
    (BATFLY_WING_W, -BATFLY_WING_LEN * 0.4),
    (BATFLY_WING_W * 0.55, -BATFLY_WING_LEN * 0.85),
    (0.0, -BATFLY_WING_LEN),
    (-BATFLY_WING_W * 0.22, -BATFLY_WING_LEN * 0.45),
]
# 形状 / 颜色缓存：身路径按腹长量化
_wing_poly = None
_BODY_PATHS: dict[int, QPainterPath] = {}
_BLACK_C = QColor(*BATFLY_BLACK)
_WING_C = QColor(*BATFLY_WING_COLOR)
_EYE_C = QColor(*BATFLY_EYE_COLOR)

_ICON_BODY = QColor(24, 26, 30)
_ICON_EYE = QColor(232, 236, 226)


class BatFlyKind(ItemKind):
    key = "batfly"
    store = "batflies"
    affords = frozenset({EDIBLE, CARRYABLE})
    grab_pad = 7.0
    grab_rank = 3

    def make(self, win, lx, ly, seed):
        return BatFly(lx, ly, seed=seed)

    def drop(self, win, b):
        b.stalk = None
        for pet in win.pets:
            pet.body.release(b)
        b.held_by_hand = None
        b.state = ItemState.EATEN
        getattr(win, "_batfly_shove_cd", {}).pop(id(b), None)

    def hit(self, b, cx, cy):
        if b.state in (ItemState.EATEN, ItemState.GONE):
            return None
        return math.hypot(cx - b.x, cy - b.y) - b.rad

    def on_grab(self, b):
        b.stalk = None
        b.held_by_hand = None

    def after_step(self, win):
        _shove(win)

    def draw(self, win, p):
        ts = win._ts
        win._batfly_vibe = getattr(win, "_batfly_vibe", 0) + 1
        for b in win.batflies:
            if b.state in (ItemState.EATEN, ItemState.GONE):
                continue
            _draw_one(win, p, b, ts)

    def draw_hint(self, win, p, cx, cy):
        p.save()
        p.setOpacity(0.5)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        _wing(p, cx, cy, -115.0, -0.9)
        _wing(p, cx, cy, 115.0, 0.9)
        _body(p, cx, cy, 0.0, 10.0)
        _eyes(p, cx, cy, 0.0)
        p.restore()

    def paint_icon(self, p, r, atlas):
        cx, cy = r.center().x(), r.center().y()
        w, h = r.width(), r.height()
        bx, by = cx, cy + h * 0.06
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_ICON_BODY)
        for sgn in (-1, 1):
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(bx + sgn * w * 0.02, by - h * 0.16),
                        QPointF(bx + sgn * w * 0.46, by - h * 0.34),
                        QPointF(bx + sgn * w * 0.30, by + h * 0.06),
                        QPointF(bx + sgn * w * 0.02, by + h * 0.10),
                    ]
                )
            )
        body = QRectF(0, 0, w * 0.26, h * 0.40)
        body.moveCenter(QPointF(bx, by))
        p.drawEllipse(body)
        p.setBrush(_ICON_EYE)
        p.drawEllipse(QPointF(bx, by - h * 0.09), w * 0.035, w * 0.035)


def _shove(win):
    cd = getattr(win, "_batfly_shove_cd", None)
    if cd is None:
        cd = win._batfly_shove_cd = {}
    for k in list(cd):
        cd[k] -= 1
        if cd[k] <= 0:
            del cd[k]
    for b in win.batflies:
        key = id(b)
        if b.state != ItemState.MOUSE or b.eaten > 0:
            cd.pop(key, None)  # __slots__ 无法挂属性，用 id 字典
            continue
        if key in cd:
            continue
        for pet in win.pets:
            if pet.behavior is None or not pet.can_eat(b):
                continue
            mx, my = pet.gfx.mouth_world()
            if math.hypot(b.x - mx, b.y - my) < SHOVE_REACH:
                if b.bite():
                    pet.body.feed(pet.traits.nourishment(b))
                cd[key] = SHOVE_COOLDOWN
                break


def _draw_one(win, p, bat, ts):
    x = bat.last_x + (bat.x - bat.last_x) * ts
    y = bat.last_y + (bat.y - bat.last_y) * ts
    lx = bat.last_lower_x + (bat.lower_x - bat.last_lower_x) * ts
    ly = bat.last_lower_y + (bat.lower_y - bat.last_lower_y) * ts
    if bat.eaten > 0:
        vf = win._batfly_vibe + (id(bat) & 0x3F)
        ox, oy = (vf % 3) - 1.0, ((vf // 2) % 3) - 1.0
        x += ox
        y += oy
        lx += ox
        ly += oy
    body_ang = _ang_from_up(x - lx, y - ly)
    abdomen = clampf(math.hypot(x - lx, y - ly), BATFLY_ABDOMEN_MIN, BATFLY_ABDOMEN_MAX)
    flap_depth = bat.last_flap_depth + (bat.flap_depth - bat.last_flap_depth) * ts
    steer = lerp(bat.last_steer, bat.steer, ts)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(2):
        if (i == 0 and bat.bites != 3) or (i == 1 and bat.bites <= 1):
            continue  # bites: 3 两翅 2 一翅 1 无翅
        wcur = lerp(bat.wings[i][1], bat.wings[i][0], ts)
        a = lerp(wcur, 0.5, lerp(0.3, 0.0, flap_depth))
        steer_fold = 0.0 if (steer < 0.0) == (i == 0) else clampf(abs(steer * 0.85) - 0.1, 0.0, 1.0)
        a = lerp(a, 0.5, steer_fold)
        a = inv_lerp(0.01, 0.99, a * a)
        # 折角压缩到 40~145°，防读作垂臂
        wing_ang = (-1.0 if i == 0 else 1.0) * (40.0 + 105.0 * a) + body_ang
        sx = 1.0 if bat.flap_speed < 0.0 else 1.0 - 0.6 * math.sin(wcur * math.pi) * (1.0 - steer_fold)
        sx *= -1.0 if i == 0 else 1.0
        _wing(p, x, y, wing_ang, sx)
    _body(p, x, y, body_ang, abdomen)
    _eyes(p, x, y, body_ang)
    p.restore()


def _body(p, x, y, ang, abdomen):
    q = int(round(abdomen * 8.0))  # 1/8px 量化，路径按档缓存
    path = _BODY_PATHS.get(q)
    if path is None:
        hw = BATFLY_BODY_HALF_W
        yh = -BATFLY_BODY_HALF_H
        ym = -BATFLY_BODY_HALF_H * 0.3
        yt = q / 8.0
        path = QPainterPath()
        path.moveTo(0.0, yh)
        path.cubicTo(hw * 1.05, yh + (ym - yh) * 0.2, hw, ym - 0.5, hw, ym)
        path.cubicTo(hw, ym + (yt - ym) * 0.6, hw * 0.45, yt - 1.0, 0.0, yt)
        path.cubicTo(-hw * 0.45, yt - 1.0, -hw, ym + (yt - ym) * 0.6, -hw, ym)
        path.cubicTo(-hw, ym - 0.5, -hw * 1.05, yh + (ym - yh) * 0.2, 0.0, yh)
        path.closeSubpath()
        _BODY_PATHS[q] = path
    p.save()
    p.translate(x, y)
    if ang:
        p.rotate(ang)
    p.setBrush(_BLACK_C)
    p.drawPath(path)
    p.restore()


def _wing(p, x, y, ang, sx):
    global _wing_poly
    if _wing_poly is None:
        _wing_poly = QPolygonF([QPointF(px, py) for px, py in _WING_PTS])
    p.save()
    p.translate(x, y)
    if ang:
        p.rotate(ang)
    p.scale(sx, 1.0)
    p.setBrush(_WING_C)
    p.drawPolygon(_wing_poly)
    p.restore()


def _eyes(p, x, y, ang):
    p.save()
    p.translate(x, y)
    if ang:
        p.rotate(ang)
    p.setBrush(_EYE_C)
    p.drawEllipse(QPointF(-BATFLY_EYE_DX, -BATFLY_EYE_DY), BATFLY_EYE_RAD, BATFLY_EYE_RAD)
    p.drawEllipse(QPointF(BATFLY_EYE_DX, -BATFLY_EYE_DY), BATFLY_EYE_RAD, BATFLY_EYE_RAD)
    p.restore()


KIND = BatFlyKind()
