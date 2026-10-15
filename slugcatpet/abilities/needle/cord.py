"""脐带：连着身体扔出的骨针从尾根牵出的一根细肉线，飞一阵后逐段断掉消失。"""

from __future__ import annotations

import math

from ...core.units import clampf, lerp
from ...rendering.primitives import ribbon

SEG = 6.0  # 相邻两点的距离
RED = (255, 0, 0)
THREAD = (242, 204, 140)
ROOT_DARK = (0, 0, 0)
MAX_HALF_W = 0.5


def _inv(a, b, v):
    return clampf((v - a) / (b - a), 0.0, 1.0)


class Cord:
    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "life", "rate", "needle")

    def __init__(self, root, needle, rng):
        n = rng.randint(10, 19)
        rx, ry = root
        self.needle = needle
        self.x, self.y, self.lx, self.ly, self.vx, self.vy, self.life, self.rate = ([] for _ in range(8))
        for _ in range(n):
            a = rng.uniform(0.0, math.tau)
            b = rng.uniform(0.0, math.tau)
            k = rng.random() * 1.5
            s = 0.3 * rng.random()
            self.x.append(rx + math.cos(a))
            self.y.append(ry + math.sin(a))
            self.lx.append(rx)
            self.ly.append(ry)
            self.vx.append(needle.vx * s + math.cos(b) * k)
            self.vy.append(needle.vy * s + math.sin(b) * k)
            self.life.append(2.0)
            self.rate.append(lerp(150.0, 200.0, rng.random() ** 0.3))

    def seg_life(self, i):
        return min(self.life[i], self.life[i - 1]) if i > 0 else self.life[i]

    def _end(self):
        return self.needle.rear()

    def update(self, root, floor_y, alive) -> bool:
        """推进一 tick；root 为尾根位置，alive=False 时尾根这头断开。返回是否还在。"""
        x, y, vx, vy, life = self.x, self.y, self.vx, self.vy, self.life
        n = len(x)
        left = False
        for i in range(n):
            self.lx[i], self.ly[i] = x[i], y[i]
            x[i] += vx[i]
            y[i] += vy[i]
            sp = math.hypot(vx[i], vy[i])
            k = lerp(0.99, 0.8, _inv(1.0, 30.0, sp))
            vx[i] *= k
            vy[i] *= k
            li = self.seg_life(i)
            vy[i] += lerp(0.1, 0.6, clampf(li, 0.0, 1.0))
            if li <= 0.0:
                continue
            if y[i] > floor_y:
                y[i] = floor_y
                vy[i] = min(vy[i], 0.0)
                vx[i] *= 0.7
            if i > 0:
                dx, dy = x[i - 1] - x[i], y[i - 1] - y[i]
                d = math.hypot(dx, dy)
                if d > SEG:
                    ux, uy = dx / d * (d - SEG), dy / d * (d - SEG)
                    x[i] += ux * 0.15
                    y[i] += uy * 0.15
                    vx[i] += ux * 0.25
                    vy[i] += uy * 0.25
                    x[i - 1] -= ux * 0.15
                    y[i - 1] -= uy * 0.15
                    vx[i - 1] -= ux * 0.25
                    vy[i - 1] -= uy * 0.25
            if i > 1 and self.seg_life(i - 1) > 0.0:
                dx, dy = x[i] - x[i - 2], y[i] - y[i - 2]
                d = math.hypot(dx, dy)
                if d > 1e-6:
                    vx[i] += dx / d * 0.6
                    vy[i] += dy / d * 0.6
                    vx[i - 2] -= dx / d * 0.6
                    vy[i - 2] -= dy / d * 0.6
            life[i] -= 1.0 / self.rate[i]
            if life[i] > 0.0:
                left = True
        if self.seg_life(0) > 0.0:
            x[0], y[0] = root
            vx[0] = vy[0] = 0.0
            if self.seg_life(1) <= 0.0 or not alive:
                life[0] -= 1.0
        last = n - 1
        if self.seg_life(last) > 0.0:
            ex, ey = self._end()
            x[last], y[last] = ex, ey
            vx[last] = vy[last] = 0.0
            s = self.needle
            dx, dy = ex - s.x, ey - s.y
            d = math.hypot(dx, dy) or 1.0
            vx[last - 1] += dx / d * 6.0
            vy[last - 1] += dy / d * 6.0
            vx[last - 2] += dx / d * 1.5
            vy[last - 2] += dy / d * 1.5
            if s.state == "gone":
                life[last] -= 1.0
        return left

    def draw(self, p, root, ts):
        """root 为插值后的尾根位置。"""
        n = len(self.x)
        pts, widths, cols = [], [], []
        for i in range(n):
            li = self.seg_life(i)
            if i < n - 1:
                li = min(li, self.seg_life(i + 1))
            if i == 0 and self.seg_life(0) > 0.0:
                pts.append(root)
            elif i == n - 1 and self.seg_life(i) > 0.0:
                ex, ey = self._end()
                k = ts - 1.0  # 针在脐带之后推进：按插值退回去
                pts.append(
                    (
                        ex + (self.needle.x - self.needle.last_x) * k,
                        ey + (self.needle.y - self.needle.last_y) * k,
                    )
                )
            else:
                pts.append((lerp(self.lx[i], self.x[i], ts), lerp(self.ly[i], self.y[i], ts)))
            widths.append(MAX_HALF_W * _inv(0.0, 0.3, li))
            f = i / (n - 1)
            k = clampf(0.1 + 0.9 * f ** (0.25 + max(0.0, li)), 0.0, 1.0)
            c = ROOT_DARK if i == 0 else tuple(int(lerp(r, t, k)) for r, t in zip(RED, THREAD))
            cols.append((*c, int(255 * clampf(li, 0.0, 1.0))))
        if max(widths) <= 0.0:
            return
        ribbon(p, pts, widths, cols)
