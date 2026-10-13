"""二维向量小工具（不依赖 Qt），坐标系 y↓。"""
from __future__ import annotations
import math


def _dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def _dirvec(ax, ay, bx, by):
    """a→b 单位方向；重合→(0,0)。"""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return (0.0, 0.0)
    return (dx / d, dy / d)


def _span(ax, ay, bx, by):
    """a→b 的距离与单位方向（一次 hypot）；重合→方向 (0,0)。"""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return d, 0.0, 0.0
    return d, dx / d, dy / d


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    k = 0.0 if l2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + dx * k), py - (ay + dy * k))


def _ang_from_up(dx, dy):
    """方向相对『上』(0,-1) 的角（度，Qt 同号：顺时针正）。"""
    return math.degrees(math.atan2(dx, -dy))


def _rot(lx, ly, deg):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return lx * c - ly * s, lx * s + ly * c
