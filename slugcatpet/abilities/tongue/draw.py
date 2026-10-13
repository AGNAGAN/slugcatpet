"""舌头渲染：渲染链每 tick 推进（Verlet），绘制时只画不推。"""
from __future__ import annotations

import math

from ...core.gfxmath import _hsl2rgb, TONGUE_WIDTH_SCALE
from ...core.units import damp60
from ...rendering.primitives import ribbon

N = 20


class TongueRope:
    """渲染链：pts[0]=舌尖，pts[-1]=嘴。"""

    def __init__(self):
        self.pts = None
        self.vel = None
        self._damp = damp60(0.98)
        self._pull_vel = 0.2
        self._pull_pos = 0.4

    def update(self, t):
        if t is None or not t.visible:
            self.pts = None
            self.vel = None
            return

        mx, my = t.mouth
        tx, ty = t.x, t.y

        rope = self.pts
        rope_v = self.vel
        # 无链/长度变/跳变>80px 时重建
        if (rope is None or len(rope) != N
                or rope_v is None or len(rope_v) != N
                or math.hypot(rope[-1][0] - mx, rope[-1][1] - my) > 80.0):
            rope = [(tx + (mx - tx) * (i / (N - 1)),
                     ty + (my - ty) * (i / (N - 1))) for i in range(N)]
            rope_v = [(0.0, 0.0)] * N

        pts = list(rope)
        vel = list(rope_v)
        pts[0] = (tx, ty)
        pts[-1] = (mx, my)
        vel[0] = (0.0, 0.0)
        vel[-1] = (0.0, 0.0)

        damp = self._damp
        kv = self._pull_vel
        kp = self._pull_pos

        for i in range(1, N - 1):
            gt = i / (N - 1)
            gx = tx + (mx - tx) * gt
            gy = ty + (my - ty) * gt
            x, y = pts[i]
            vx, vy = vel[i]
            x = x + vx
            y = y + vy
            vx *= damp
            vy *= damp
            vx += (gx - x) * kv
            vy += (gy - y) * kv
            x = x + (gx - x) * kp
            y = y + (gy - y) * kp
            pts[i] = (x, y)
            vel[i] = (vx, vy)

        # 约束求解，rest=总长/N*0.1
        rope_total_len = getattr(t, "total", 200.0)
        rest = (rope_total_len / N) * 0.1
        for i in range(1, N):
            ax, ay = pts[i - 1]
            bx, by = pts[i]
            dx, dy = bx - ax, by - ay
            d = math.hypot(dx, dy)
            if d < 1e-6:
                continue
            over = (d - rest)
            ux, uy = dx / d, dy / d
            if i - 1 != 0:
                pax, pay = pts[i - 1]
                pts[i - 1] = (pax + ux * over * 0.5, pay + uy * over * 0.5)
                pvx, pvy = vel[i - 1]
                vel[i - 1] = (pvx + ux * over * 0.5, pvy + uy * over * 0.5)
            if i != N - 1:
                pbx, pby = pts[i]
                pts[i] = (pbx - ux * over * 0.5, pby - uy * over * 0.5)
                qvx, qvy = vel[i]
                vel[i] = (qvx - ux * over * 0.5, qvy - uy * over * 0.5)
        pts[0] = (tx, ty)
        pts[-1] = (mx, my)
        self.pts = pts
        self.vel = vel


def draw_tongue(t, rope, p):
    if t is None or not t.visible:
        return

    pts = rope.pts
    if pts is None:
        return

    mx, my = t.mouth

    travel = math.hypot(t.x - mx, t.y - my)
    tot = getattr(t, "total", 200.0)
    req = min(getattr(t, "requested", travel), tot)
    b_denom = travel + 80.0
    b = ((tot + req) * 0.5) / b_denom if b_denom > 1e-6 else 1.0
    b = b ** (0.4 if b >= 1.0 else 1.6)
    if getattr(t, "mode", None) == "attached":
        b = b + (1.0 - b) * 0.5

    PI = math.pi
    tip_x, tip_y = pts[0]
    n1x, n1y = pts[1]
    ddx, ddy = tip_x - n1x, tip_y - n1y
    dl = math.hypot(ddx, ddy) or 1.0
    # 舌尖端外延 1px
    line = [(tip_x + ddx / dl, tip_y + ddy / dl)]
    line += [pts[k] for k in range(1, N - 2)]
    line.append((mx, my))
    m = len(line)
    widths = []
    for i in range(m):
        frac = i / (m - 1)
        taper = math.sin(frac * PI) ** 0.7
        amp = 1.0 + (b - 1.0) * taper
        widths.append((0.2 + 1.6 * amp) * TONGUE_WIDTH_SCALE)

    fog = (185, 195, 200)
    HA, HB, HSL_SL, A2, B2 = 0.95, 1.0, 1.0, 0.75, 0.9

    vcolors = []
    for j in range(m):
        mid_t = max(0.0, min(1.0, math.sin(j / max(1, m - 1) * PI)))
        h = HA + (HB - HA) * mid_t
        lv = A2 + (B2 - A2) * (mid_t ** 0.15)
        gr, gg, gb = _hsl2rgb(h, HSL_SL, lv)
        cr = int(fog[0] + (gr * 255.0 - fog[0]) * 0.7)
        cg = int(fog[1] + (gg * 255.0 - fog[1]) * 0.7)
        cb = int(fog[2] + (gb * 255.0 - fog[2]) * 0.7)
        vcolors.append((cr, cg, cb))

    ribbon(p, line, widths, vcolors)
