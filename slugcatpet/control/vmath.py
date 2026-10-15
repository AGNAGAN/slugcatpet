"""Roll、Flip 力矩用的向量函数，按 y↑ 计算不翻转；角度 0° 为 +Y，顺时针增大。"""

from __future__ import annotations
import math


def normalize(x: float, y: float):
    d = math.hypot(x, y)
    if d < 1e-9:
        return (0.0, 0.0)
    return (x / d, y / d)


def dirvec(ax: float, ay: float, bx: float, by: float):
    return normalize(bx - ax, by - ay)


def perpendicular(ax: float, ay: float, bx: float, by: float):
    dx, dy = dirvec(ax, ay, bx, by)
    return (dy, -dx)


def degvec(deg: float):
    r = deg * math.pi / 180.0
    return (math.sin(r), math.cos(r))
