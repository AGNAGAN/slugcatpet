"""尾巴斑点：沿尾巴铺 5 行 × 3 列小点，越往尾尖越亮；按每段的位置和粗细摆，任何尾巴都贴得上。"""

from __future__ import annotations

import math

from ...appearance import accessory_color
from ...core.gfxmath import _lerp
from ...core.vecmath import _ang_from_up
from ...rendering.primitives import blit
from ..base import Accessory

FRAME = "tinyStar"
ROWS, LINES = 5, 3
SPAN = (0.4, 0.95)  # 铺在尾巴长度的这一段
TIP_MIX = 0.3  # 默认色：白色混这么多体色
BASE_MIX = 0.2  # 尾根那行往默认色混的起点
LIGHT_BODY = 0.9  # 尾巴亮度超过这个时默认改用灰色，不然白点看不见
GRAY = (128, 128, 128)


def _mix(a, b, t):
    t = min(1.0, max(0.0, t))
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _luma(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255.0


def spine_at(pts, rads, s):
    """尾巴长度比例 s 处的 (位置, 切向, 法向, 半径)；pts/rads 为各段位置和半径。"""
    n = len(pts)
    v = s * n
    a = min(n - 1, max(0, math.floor(v - 1.0)))
    b = min(n - 1, max(0, math.floor(v)))
    c = min(b + 1, n - 1)
    t = 0.0 if a == b else min(1.0, max(0.0, (v - (a + 1)) / (b - a)))
    (ax, ay), (bx, by), (cx, cy) = pts[a], pts[b], pts[c]
    dx = _lerp(bx - ax, cx - bx, t)
    dy = _lerp(by - ay, cy - by, t)
    d = math.hypot(dx, dy)
    if d < 1e-9:
        dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        d = math.hypot(dx, dy) or 1.0
    dx, dy = dx / d, dy / d
    return (_lerp(ax, bx, t), _lerp(ay, by, t)), (dx, dy), (-dy, dx), _lerp(rads[a], rads[b], t)


class TailSpecklesAccessory(Accessory):
    key = "tail_specks"
    title = {"zh": "尾巴斑点", "en": "Tail speckles"}
    default_color = (255, 255, 255)
    default_on = ("spearmaster",)
    color_group = "TAILSPECKLES"
    skin_group = "TAILSPECKLES"

    def draw_layers(self, pet):
        return (("over_tail", lambda gfx, p, atlas, ts: self._draw(gfx, p, atlas, ts)),)

    def _draw(self, gfx, p, atlas, ts):
        segs = gfx.tail_segs
        if segs is None or len(segs) < 2 or gfx._tail_hidden:
            return
        pts = [(_lerp(s.lx, s.x, ts), _lerp(s.ly, s.y, ts)) for s in segs]
        rads = [gfx._tail_rad[i] * segs[i].stretched for i in range(len(segs))]
        base = gfx._color("TAIL", gfx.BODY)
        flat = self.color is not None or self.color_group in gfx._gcol
        tip = accessory_color(self, gfx._gcol)
        if not flat and _luma(base) > LIGHT_BODY:
            flat, tip = True, GRAY
        elif not flat:
            tip = _mix(tip, base, TIP_MIX)
        for i in range(ROWS):
            f = i / (ROWS - 1)
            (x, y), (dx, dy), (px, py), rad = spine_at(pts, rads, _lerp(SPAN[0], SPAN[1], f**0.8))
            col = tip if flat else _mix(base, tip, BASE_MIX + (1.0 - BASE_MIX) * f**0.5)
            rot = _ang_from_up(dx, dy)
            for j in range(LINES):
                u = -1.0 + 2.0 * (j + (0.0 if i % 2 else 0.5)) / (LINES - 1)
                if u > 1.0:
                    u -= 2.0
                u = math.copysign(abs(u) ** 0.6, u)
                sx = min(1.0, max(0.0, (1.0 - abs(u)) / 0.6))
                off = (rad + 0.5) * u
                blit(p, atlas, FRAME, x + px * off, y + py * off, rot, sx, 1.0, col)
