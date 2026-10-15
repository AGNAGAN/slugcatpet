"""液滴：从蛋虫和它的蛋上甩出的一小道液体，受重力下落，后半生慢慢缩没，碰到地面就消失。y↓。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from ..core.units import inv_lerp, lerp

GRAVITY = 0.9
LIFE = (20.0, 40.0)  # 寿命帧数范围
WIDTH = 1.5


def new_drip(x, y, vx, vy, rng, blood=False):
    """[x, y, vx, vy, 上帧 x, 上帧 y, 上上帧 x, 上上帧 y, 剩余寿命, 每帧减少, 是血]"""
    return [x, y, vx, vy, x, y, x, y, 1.0, 1.0 / lerp(*LIFE, rng.random()), blood]


def step_drips(drips, room_gravity, HL):
    """推进一帧，返回还活着的。"""
    keep = []
    for d in drips:
        d[6], d[7] = d[4], d[5]
        d[4], d[5] = d[0], d[1]
        d[3] += GRAVITY * room_gravity
        d[0] += d[2]
        d[1] += d[3]
        d[8] -= d[9]
        if d[8] > 0.0 and d[5] < HL:
            keep.append(d)
    return keep


def draw_drips(p, drips, ts, color, blood_color=None):
    """每滴画成拖向上一帧的一小段，长约半帧位移加 2。"""
    cols = (QColor(*color), QColor(*(blood_color or color)))
    for d in drips:
        x, y = lerp(d[4], d[0], ts), lerp(d[5], d[1], ts)
        ax, ay = lerp(d[6], d[4], ts), lerp(d[7], d[5], ts)
        ax, ay = lerp(ax, x, 0.5), lerp(ay, y, 0.5)
        fade = inv_lerp(0.0, 0.5, d[8])
        if fade <= 0.0:
            continue
        dx, dy = ax - x, ay - y
        m = math.hypot(dx, dy)
        ux, uy = (dx / m, dy / m) if m > 1e-9 else (0.0, -1.0)
        n = (m + 2.0) * fade
        pen = QPen(cols[1] if d[10] else cols[0], WIDTH * fade)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawLine(QPointF(x, y), QPointF(x + ux * n, y + uy * n))
    p.setPen(Qt.PenStyle.NoPen)
