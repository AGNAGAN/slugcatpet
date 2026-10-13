"""渲染层数学工具与常量，坐标系 y↓。"""
from __future__ import annotations

SHOULDER_OFF_X = 4.5
SHOULDER_OFF_Y = 3.5                # y↓
ARM_DIV = 2.0
ARM_MAX = 12
TAIL_RAD = (6.0, 4.0, 2.5, 1.0)
TONGUE_WIDTH_SCALE = 0.4            # 调校值，勿改回


def _hsl2rgb(h, sl, l):
    r = g = b = l
    v_max = l * (1.0 + sl) if l <= 0.5 else l + sl - l * sl
    if v_max > 0.0:
        v_min = l + l - v_max
        chroma_ratio = (v_max - v_min) / v_max
        h6 = h * 6.0
        sector = int(h6)
        frac = h6 - sector
        delta = v_max * chroma_ratio * frac
        rising = v_min + delta
        falling = v_max - delta
        if sector == 0:   r, g, b = v_max, rising, v_min
        elif sector == 1: r, g, b = falling, v_max, v_min
        elif sector == 2: r, g, b = v_min, v_max, rising
        elif sector == 3: r, g, b = v_min, falling, v_max
        elif sector == 4: r, g, b = rising, v_min, v_max
        elif sector == 5: r, g, b = v_max, v_min, falling
    return r, g, b


def _lerp(a, b, t):
    return a + (b - a) * t


def _catmull(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return 0.5 * ((2.0 * p1)
                  + (-p0 + p2) * t
                  + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                  + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3)
