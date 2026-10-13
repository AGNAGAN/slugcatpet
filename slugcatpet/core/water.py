"""水面波形内核：一维阻尼波方程点链，坐标 y↓。"""
from __future__ import annotations
import random

from .units import clampf, lerp, inv_lerp

# 波方程常量：R=C*dt/dx
DX_FACTOR = 0.0005
DT = 0.0045
WAVE_SPEED_C = 1.0
DAMPING = 0.99
HEIGHT_CLAMP = 40.0
TRIANGLE_WIDTH = 20.0


class _RippleRing:
    __slots__ = ("x", "rad", "speed", "width", "intensity", "life", "life_dec")

    def __init__(self, x: float, rad: float, speed: float, width: float,
                 life_time: float, intensity: float):
        self.x = x
        self.rad = rad
        self.speed = speed
        self.width = width
        self.intensity = intensity
        self.life = 1.0
        self.life_dec = 1.0 / life_time


class WaterSurface:

    def __init__(self, width: float, base_y: float, spacing: float = TRIANGLE_WIDTH,
                 wave_amp: float = 0.0, seed: int | None = None):
        self.width = float(width)
        self.base_y = float(base_y)
        self.spacing = float(spacing)
        self.n = max(3, int(round(self.width / self.spacing)) + 1)
        self.spacing = self.width / (self.n - 1)   # 均分到末点正好落在右边界
        # Courant 数，须 R<1 保稳定
        dx = DX_FACTOR * self.spacing
        self.r = WAVE_SPEED_C * DT / dx
        assert self.r < 1.0, f"R={self.r:.3f} must be < 1 for stability (spacing={self.spacing})"
        self.r2 = self.r * self.r
        self.wave_amp = float(wave_amp)
        self._rng = random.Random(seed)
        self.height = [0.0] * self.n
        self.last_height = [0.0] * self.n
        self.next_height = [0.0] * self.n
        self._rings: list[_RippleRing] = []
        self.splash_stop = 0

    def point_x(self, i: int) -> float:
        return i * self.spacing

    def step(self) -> None:
        if self.splash_stop > 0:
            self.splash_stop -= 1
        h, lh, nh = self.height, self.last_height, self.next_height
        n, r, r2 = self.n, self.r, self.r2
        mean_acc = 0.0
        for i in range(n):
            if i == 0:
                nh[i] = (2.0 * h[i] + (r - 1.0) * lh[i] + 2.0 * r2 * (h[i + 1] - h[i])) / (1.0 + r)
            elif i == n - 1:
                nh[i] = (2.0 * h[i] + (r - 1.0) * lh[i] + 2.0 * r2 * (h[i - 1] - h[i])) / (1.0 + r)
            else:
                nh[i] = r2 * (h[i - 1] + h[i + 1]) + 2.0 * (1.0 - r2) * h[i] - lh[i]
            if self.wave_amp > 0.0:
                nh[i] += lerp(-self.wave_amp, self.wave_amp, self._rng.random()) * 0.005
            nh[i] *= DAMPING
            mean_acc += h[i]
        mean_acc /= n * 1.5
        for i in range(n):
            lh[i] = h[i]
            v = nh[i] - mean_acc
            if 0 < i < n - 1:
                v = lerp(v, lerp(nh[i - 1], nh[i + 1], 0.5), 0.01)
            h[i] = clampf(v, -HEIGHT_CLAMP, HEIGHT_CLAMP)
        if self._rings:
            self._step_rings()

    def _prev_point(self, x: float) -> int:
        i = int(x / self.spacing)
        if i < 0:
            return 0
        if i > self.n - 2:
            return self.n - 2
        return i

    def _closest_point(self, x: float) -> int:
        i = int(x / self.spacing + 0.5)
        if i < 0:
            return 0
        if i > self.n - 1:
            return self.n - 1
        return i

    def level_at(self, x: float) -> float:
        i = self._prev_point(x)
        j = i + 1
        t = inv_lerp(self.point_x(i), self.point_x(j), x)
        return self.base_y + lerp(self.height[i], self.height[j], t)

    def energy(self) -> float:
        m = 0.0
        for v in self.height:
            a = v if v >= 0.0 else -v
            if a > m:
                m = a
        return m

    def waterfall_hit(self, left: float, right: float, flow: float) -> None:
        i_first = self._prev_point(left)
        i_last = self._prev_point(right) + 1
        if i_last > self.n - 1:
            i_last = self.n - 1
        for i in range(i_first, i_last + 1):
            if self._rng.random() < flow:
                edge = -1.0 if (i == i_first or i == i_last) else 1.0
                self.height[i] += (1.9 * lerp(-1.0, 0.5, self._rng.random())
                                   * edge * lerp(0.6, 1.0, flow))

    def drain_affect(self, left: float, right: float, flow: float) -> None:
        i_first = self._prev_point(left)
        i_last = self._prev_point(right) + 1
        if i_last > self.n - 1:
            i_last = self.n - 1
        for i in range(i_first, i_last + 1):
            if self._rng.random() < flow:
                edge = 0.5 if (i == i_first or i == i_last) else 1.0
                self.height[i] -= 1.6 * lerp(0.5, 1.5, self._rng.random()) * edge * flow

    def splash(self, x: float, impulse: float) -> None:
        c = self._closest_point(x)
        self.height[c] += impulse / 2.0
        if c > 0:
            self.height[c - 1] += impulse / 6.0
        if c < self.n - 1:
            self.height[c + 1] += impulse / 6.0

    def ripple_ring(self, x: float, rad: float = 5.0, speed: float = 17.0,
                    width: float = 70.0, life_time: float = 20.0, intensity: float = 1.0) -> None:
        self._rings.append(_RippleRing(x, rad, speed, width, life_time, intensity))

    def _step_rings(self):
        alive = []
        for ring in self._rings:
            ring.rad += ring.speed
            ring.life -= ring.life_dec
            fade = inv_lerp(0.0, 0.5, ring.life)
            for i in range(self.n):
                dist = abs(abs(self.point_x(i) - ring.x) - ring.rad)
                near = inv_lerp(ring.width, ring.width / 3.0, dist) * fade
                if near > 0.0:
                    self.height[i] += lerp(-1.0, 1.0, self._rng.random()) * 0.1 * near * ring.intensity
            if ring.life > 0.0:
                alive.append(ring)
        self._rings = alive
