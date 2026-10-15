"""蛋虫和蛋的配色：按色相算出各部位颜色。"""

from __future__ import annotations

import colorsys

from ...core.units import lerp

_cache = {}


def _hsl(h, s, light):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, light, s)
    return int(r * 255), int(g * 255), int(b * 255)


def _mix(a, b, t):
    return tuple(int(round(lerp(x, y, t))) for x, y in zip(a, b))


def palette(hue):
    """背上的蛋发青光、红点，身子近黑带一点红。"""
    c = _cache.get(hue)
    if c is None:
        glow = _hsl(hue + 0.5, 1.0, 0.5)
        red = _hsl(hue, 1.0, 0.5)
        black = _mix((14, 10, 13), _mix(red, (110, 110, 120), 0.3), 0.1)
        tip = _mix(black, red, 0.2)
        dot = _mix(red, black, 0.5)
        c = _cache[hue] = {
            "black": black,
            "glow": glow,
            "dot": dot,
            "eye": _mix((205, 210, 205), glow, 0.5),
            "tip": tip,
            "drip": _mix(glow, black, 0.4),
            "stub": _mix(tip, dot, 0.5),
            "blood": _mix(dot, black, 0.4),
        }
    return c


def colors(g):
    return palette(g.hue)


mix = _mix
