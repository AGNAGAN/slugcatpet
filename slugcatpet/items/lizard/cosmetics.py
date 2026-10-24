"""LizardCosmetics：已有品种会挑到的装饰件，及按原版 LizardGraphics 构造函数挑选的 build_cosmetics。

装饰件的随机数调用顺序、短路求值与原版逐句对应（rng 代替 UnityEngine.Random）。
绘制层级 sprites_overlap：BehindHead 画在头后面，InFront 画在头前面。
"""

from __future__ import annotations

import math
import random

from .draw import BLACK_COLOR, body_color, frame_at, head_color, quantize, spine_in, spine_position
from .limbs import GenericBodyPart
from .physics import vslerp
from .rw import (
    DEG,
    deg_to_vec,
    dir_vec,
    lerp_map,
    rnv,
    V2,
    inverse_lerp,
    lerp,
    color_lerp,
    clamped_random_variation,
    random_range_int,
    sign,
)


class LizardScale:
    """LizardScale：一片长鳞的质点。位置、速度用 float 存（每 tick 每片都要更新）。"""

    __slots__ = ("cosmetic", "length", "width", "x", "y", "lx", "ly", "vx", "vy")

    def __init__(self, owner, cosmetic):
        self.cosmetic = cosmetic
        self.length = 0.0
        self.width = 0.0
        self.x = self.y = self.lx = self.ly = self.vx = self.vy = 0.0


class Template:
    sprites_overlap = "BehindHead"

    def __init__(self, gfx, rng: random.Random):
        self.gfx = gfx
        self.rng = rng

    def update(self) -> None:
        pass

    def reset(self) -> None:
        pass

    def apply_palette(self) -> None:
        pass

    def draw(self, cv, ts: float) -> None:
        pass


class BodyScales(Template):
    """BodyScales：scales_positions 是 (横向 -1..1, 沿脊线 0..1)。"""

    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        self.graphic = 0
        self.scale_x = 0.0
        self.colored = False
        self.scales_positions: list[V2] = []

    def generate_patch_pattern(self, start_point, num_of_scales, max_length, length_exponent) -> None:
        r = self.rng.random
        g = self.gfx
        num = lerp(start_point + 0.1, max(start_point + 0.2, max_length), r() ** length_exponent)
        bl = g.body_length / g.body_and_tail_length
        self.scales_positions = []
        for _ in range(num_of_scales):
            v = deg_to_vec(r() * 360.0) * r()
            y = lerp(start_point * bl, num * bl, (v.y + 1.0) / 2.0)
            self.scales_positions.append(V2(v.x, y))

    def generate_two_lines(self, start_point, max_length, length_exponent, spacing_scale) -> None:
        r = self.rng.random
        num = lerp(start_point + 0.1, max(start_point + 0.2, max_length), r() ** length_exponent)
        num2 = num * self.gfx.body_and_tail_length
        num3 = lerp(2.0, 9.0, r())
        if self.gfx.lizard.lizard_params.key == "blue":
            num3 = 2.0
        num3 *= spacing_scale
        num4 = max(3, int(num2 / num3))
        pos = []
        for i in range(num4):
            y = lerp(0.0, num, i / (num4 - 1))
            x = 0.6 + 0.4 * math.sin(i / (num4 - 1) * math.pi)
            pos.append(V2(x, y))
            pos.append(V2(-x, y))
        self.scales_positions = pos

    def generate_segments(self, start_point, max_length, length_exponent) -> None:
        r = self.rng.random
        num = lerp(start_point + 0.1, max(start_point + 0.2, max_length), r() ** length_exponent)
        num2 = num * self.gfx.body_and_tail_length
        num3 = lerp(7.0, 14.0, r())
        if self.gfx.lizard.lizard_params.key == "red":
            num3 = min(num3, 11.0) * 0.75
        num4 = max(3, int(num2 / num3))
        num5 = random_range_int(self.rng, 1, 4) * 2
        pos = []
        for i in range(num4):
            y = lerp(0.0, num, i / (num4 - 1))
            for j in range(num5):
                x = 0.6 + 0.6 * math.sin(i / (num4 - 1) * math.pi)
                x *= lerp(-1.0, 1.0, j / (num5 - 1))
                pos.append(V2(x, y))
        self.scales_positions = pos

    def get_back_pos(self, i: int, ts: float):
        """GetBackPos(changeDepthRotation: true)：(x, y, 外缘 x, 外缘 y, dir x, dir y, depthRotation)。"""
        sp = self.scales_positions[i]
        sd = spine_position(self.gfx, sp.y, ts)
        num = max(-1.0, min(1.0, sp.x + sd.depth_rotation))
        k = num * sd.rad
        return (sd.x, sd.y, sd.x + sd.px * k, sd.y + sd.py * k, sd.dx, sd.dy, num)


class ShortBodyScales(BodyScales):
    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        green = gfx.lizard.lizard_params.key == "green"
        pink = gfx.lizard.lizard_params.key == "pink"
        r = rng.random
        num = random_range_int(rng, 0, 3)
        if green and r() < 0.7:
            num = 2
        elif gfx.lizard.lizard_params.key == "blue" and r() < 0.93:
            num = 1
        if num == 0:
            self.generate_patch_pattern(0.1, random_range_int(rng, 4, 15), 0.9, 1.2)
        elif num == 1:
            self.generate_two_lines(0.1, 1.0, 1.5, 1.0)
        else:
            self.generate_segments(0.1, 0.9, 1.5 if pink else 0.6)

    def draw(self, cv, ts):
        g = self.gfx
        col = head_color(g, ts)
        for i in range(len(self.scales_positions)):
            _, _, ox, oy, dx, dy, _ = self.get_back_pos(i, ts)
            cv.block(ox, oy, math.degrees(math.atan2(-dx, -dy)), 2.0, 3.0, col)


class LongBodyScales(BodyScales):
    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        self.scale_objects: list[LizardScale] = []
        self.backwards_factors: list[float] = []
        self.rigor = 0.0
        self._placed = False
        self._height = None
        self._colors_a: list = []
        self._color_b = None

    def update(self) -> None:
        g = self.gfx
        sd = g.show_dominance
        scales = self.scale_objects
        if not self._placed:
            self._sx = [p.x for p in self.scales_positions]
            self._sy = [p.y for p in self.scales_positions]
            self._hfac = [inverse_lerp(0.2, 0.0, y) ** 2 * 2.0 if y < 0.2 else 0.0 for y in self._sy]
        fr = frame_at(g, 1.0)
        sample = fr.sp
        hs = hc = 0.0
        if any(self._hfac):
            hr = g.head_rotation(1.0) * DEG  # 每 tick 只算一次
            hs, hc = math.sin(hr), math.cos(hr)
        sd_f = lerp(1.0, 15.0, sd)
        clamp_m = lerp(10.0, 20.0, sd)
        div = lerp(5.0, 1.5, self.rigor)
        damp = lerp(1.0, 0.8, self.rigor)
        bf, hfac, sxs, sys_ = self.backwards_factors, self._hfac, self._sx, self._sy
        sqrt, hypot = math.sqrt, math.hypot
        for i, sc in enumerate(scales):
            y = sys_[i]
            s = sample.get(y)
            if s is None:
                s = sample[y] = spine_in(g, fr, y, 1.0)
            depth = max(-1.0, min(1.0, sxs[i] + s.depth_rotation))
            k = depth * s.rad
            px, py, dx, dy = s.x, s.y, s.dx, s.dy
            ox, oy = px + s.px * k, py + s.py * k
            # a = Lerp(dir, DirVec(pos, outer), |depth|)
            if px == ox and py == oy:
                vx, vy = 0.0, 1.0
            else:
                m = hypot(ox - px, oy - py)
                vx, vy = ((ox - px) / m, (oy - py) / m) if m > 1e-5 else (0.0, 0.0)
            t = abs(depth)
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            ax, ay = dx + (vx - dx) * t, dy + (vy - dy) * t
            f = hfac[i]
            if f > 0.0:
                ax, ay = ax - hs * f, ay - hc * f
            t = bf[i] ** sd_f
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            ax, ay = ax + (dx - ax) * t, ay + (dy - ay) * t
            m = hypot(ax, ay)
            ax, ay = (ax / m, ay / m) if m > 1e-5 else (0.0, 0.0)
            length = sc.length
            tx, ty = ox + ax * length, oy + ay * length
            if not self._placed:
                sc.x = sc.lx = tx
                sc.y = sc.ly = ty
            x, y_, vvx, vvy = sc.x, sc.y, sc.vx, sc.vy
            half = length / 2.0
            if not hypot(x - tx, y_ - ty) < half:
                if x == tx and y_ == ty:
                    ux, uy = 0.0, 1.0
                else:
                    m = hypot(tx - x, ty - y_)
                    ux, uy = ((tx - x) / m, (ty - y_) / m) if m > 1e-5 else (0.0, 0.0)
                d = hypot(x - tx, y_ - ty) - half
                x, y_ = x + ux * d, y_ + uy * d
                vvx, vvy = vvx + ux * d, vvy + uy * d
            ex, ey = tx - x, ty - y_
            q = ex * ex + ey * ey
            if q > clamp_m * clamp_m:
                kk = clamp_m / sqrt(q)
                ex, ey = ex * kk, ey * kk
            vvx, vvy = vvx + ex / div, vvy + ey / div
            vvx, vvy = vvx * damp, vvy * damp
            if sd > 0.0:
                ang = (self.rng.random() * 360.0) * DEG
                kk = lerp(0.0, 6.0, sd)
                vvx, vvy = vvx + math.sin(ang) * kk, vvy + math.cos(ang) * kk
            # ConnectToPoint(outer, length, push: true, ...)
            d = hypot(x - ox, y_ - oy)
            if x == ox and y_ == oy:
                ux, uy = 0.0, 1.0
            else:
                m = hypot(ox - x, oy - y_)
                ux, uy = ((ox - x) / m, (oy - y_) / m) if m > 1e-5 else (0.0, 0.0)
            ux, uy = ux * (length - d), uy * (length - d)
            x, y_ = x - ux, y_ - uy
            vvx, vvy = vvx - ux, vvy - uy
            # Update
            vvx, vvy = vvx * 0.9, vvy * 0.9
            sc.lx, sc.ly = x, y_
            sc.x, sc.y = x + vvx, y_ + vvy
            sc.vx, sc.vy = vvx, vvy
        self._placed = True

    def apply_palette(self) -> None:
        g = self.gfx
        self._colors_a = [body_color(g, sp.y) for sp in self.scales_positions]
        self._color_b = g.effect_color

    def _colors(self, ts):
        return self._colors_a

    def draw(self, cv, ts):
        if self._height is None:
            self._height = cv.source_height(f"LizardScaleA{self.graphic}")
        cols = self._colors(ts)
        placed = []
        for i, sc in enumerate(self.scale_objects):
            _, _, ox, oy, _, _, depth = self.get_back_pos(i, ts)
            rot = math.degrees(math.atan2(sc.lx + (sc.x - sc.lx) * ts - ox, sc.ly + (sc.y - sc.ly) * ts - oy))
            placed.append((ox, oy, rot, sc.width * sign(depth), sc.length / self._height))
        for i, (x, y, rot, sx, sy) in enumerate(placed):
            cv.sprite(f"LizardScaleA{self.graphic}", x, y, rot, sx, sy, cols[i], 1.0, 0.5, 0.1)
        if self.colored:
            for x, y, rot, sx, sy in placed:
                cv.sprite(f"LizardScaleB{self.graphic}", x, y, rot, sx, sy, self._color_b, 1.0, 0.5, 0.1)


class LongHeadScales(LongBodyScales):
    sprites_overlap = "InFront"

    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        r = rng.random
        self.rigor = r()
        y = lerp(0.0, 0.07, r())
        num = lerp(0.5, 1.5, r())
        self.scales_positions = [V2(-num, y), V2(num, y)]
        num = (r() ** 0.7) * gfx.lizard.lizard_params.head_size
        self.colored = r() < 0.5
        self.graphic = random_range_int(rng, 4, 6)
        if num < 0.5 and r() < 0.5:
            self.graphic = 6
        elif num > 0.8:
            self.graphic = 5
        if num < 0.2:
            self.colored = True
        value = r()
        num2 = r() ** 0.85
        for _ in self.scales_positions:
            sc = LizardScale(gfx, self)
            sc.length = lerp(5.0, 35.0, num)
            sc.width = lerp(0.65, 1.2, value * num)
            self.scale_objects.append(sc)
            self.backwards_factors.append(num2)

    def _colors(self, ts):
        return [head_color(self.gfx, ts)] * len(self.scale_objects)


class LongShoulderScales(LongBodyScales):
    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        key = gfx.lizard.lizard_params.key
        green, pink, red = key == "green", key == "pink", key == "red"
        r = rng.random
        self.rigor = 0.0
        num = 0
        if not pink or r() < 1.0 / 3.0:
            num = random_range_int(rng, 0, 3)
        elif green or r() < 0.5:
            num = 2
        if num == 0:
            self.generate_patch_pattern(0.05, random_range_int(rng, 4, 15), 0.9, 2.0)
        elif num == 1:
            self.generate_two_lines(0.07, 1.0, 1.5, 3.0)
        else:
            self.generate_segments(0.1, 0.8, 5.0)
        self._move_scales_towards_head()
        n = len(self.scales_positions)
        num2 = lerp(1.0, 1.0 / lerp(1.0, n, r() ** 2.0), 0.5)
        num3 = lerp(5.0, 15.0, r()) * num2
        b = lerp(num3, 35.0, r() ** 0.5) * num2
        if red:
            if n > 8:
                self._stretch_down_on_back(0.3 if num == 0 else 0.5)
            num2 = max(0.5, num2)
            num3 = max(10.0, num3) * 1.2
            b = max(25.0, b) * 1.2
        self.colored = green or red or r() < 0.4
        if r() < 0.1:
            self.graphic = random_range_int(rng, 0, 7)
        else:
            self.graphic = random_range_int(rng, 3, 6)
        if pink and r() < 0.25:
            self.graphic = 0
        if red:
            self.graphic = 0
            if r() < 0.3:
                self.graphic = 3
                self.scale_x = -1.0 if r() < 0.5 else 1.0
        hi = max(p.y for p in self.scales_positions)
        lo = min(p.y for p in self.scales_positions)
        hi = max(hi, 0.0)
        lo = min(lo, 1.0)
        p = lerp(0.1, 0.9, r())
        for pos in self.scales_positions:
            sc = LizardScale(gfx, self)
            k = inverse_lerp(lo, hi, pos.y) ** p
            m = lerp(math.sin(k * math.pi), 1.0, 0.5 if k < 0.5 else 0.0)
            sc.length = lerp(num3, b, m)
            sc.width = lerp(0.8, 1.2, m) * num2
            self.scale_objects.append(sc)
            self.backwards_factors.append(pos.y * 0.7)

    def _move_scales_towards_head(self) -> None:
        num = min([1.0] + [p.y for p in self.scales_positions])
        if num > 0.07:
            num -= 0.07
            self.scales_positions = [V2(p.x, p.y - num) for p in self.scales_positions]

    def _stretch_down_on_back(self, stretch_to: float) -> None:
        lo = min([1.0] + [p.y for p in self.scales_positions])
        hi = max([0.0] + [p.y for p in self.scales_positions])
        if not hi > stretch_to:
            self.scales_positions = [
                V2(p.x, lerp_map(p.y, lo, hi, lo, stretch_to)) for p in self.scales_positions
            ]


class TailTuft(LongBodyScales):
    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        key = gfx.lizard.lizard_params.key
        blue, red = key == "blue", key == "red"
        r = rng.random
        self.rigor = 0.0
        if r() < 1.0 / 7.0 or (r() < 0.9 and blue) or red:
            if blue or red:
                self.generate_two_lines(0.0, 0.3 if red else 0.7, 1.0, 3.0)
            else:
                self.generate_two_lines(0.0, 0.4, 1.2, 1.3)
        else:
            self.generate_patch_pattern(0.0, random_range_int(rng, 3, 7), 1.6, 1.5)
        top = max([0.0] + [p.y for p in self.scales_positions])
        self.scales_positions = [V2(p.x, p.y + 0.9 - top) for p in self.scales_positions]
        n = len(self.scales_positions)
        num = lerp(1.0, 1.0 / lerp(1.0, n, r() ** 2.0), 0.5)
        if red:
            num = max(num, 0.4) * 1.1
        a = lerp(5.0, 10.0, r()) * num
        b = lerp(a, 25.0, r() ** 0.5) * num
        self.colored = r() < 0.8
        self.graphic = random_range_int(rng, 3, 7)
        if self.graphic == 3:
            self.graphic = 1
        if r() < 1.0 / 30.0:
            self.graphic = random_range_int(rng, 0, 7)
        if r() < 0.8 or red:
            for c in gfx.cosmetics:
                if isinstance(c, (LongBodyScales, SpineSpikes)):
                    self.graphic = c.graphic
                    break
        hi = max([0.0] + [p.y for p in self.scales_positions])
        lo = min([1.0] + [p.y for p in self.scales_positions])
        num4 = lerp(1.0, 1.5, r())
        for k, pos in enumerate(self.scales_positions):
            sc = LizardScale(gfx, self)
            t = inverse_lerp(lo, hi, pos.y)
            sc.length = lerp(a, b, t)
            sc.width = lerp(0.8, 1.2, t) * num
            self.scale_objects.append(sc)
            self.backwards_factors.append(0.3 + 0.7 * inverse_lerp(0.75, 1.0, pos.y))
            self.scales_positions[k] = V2(pos.x * inverse_lerp(1.05, 0.85, pos.y) * num4, pos.y)


class SpineSpikes(Template):
    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        key = gfx.lizard.lizard_params.key
        green, pink = key == "green", key == "pink"
        r = rng.random
        num = lerp(5.0, 8.0, r() ** 0.7)
        self.spine_length = lerp(0.2, 0.95, r()) * gfx.body_and_tail_length
        self.size_min = lerp(0.1, 0.5, r() ** 2.0)
        self.size_max = lerp(self.size_min, 1.1, r())
        if r() < 0.5:
            self.size_max = 1.0
        if key == "blue":
            self.size_min = min(self.size_min, 0.3)
            self.size_max = min(self.size_max, 0.6)
        elif not green and r() < 0.7:
            self.size_min *= 0.7
            self.size_max *= 0.7
        elif green and r() < 0.7:
            self.size_min = lerp(self.size_min, 1.1, 0.1)
            self.size_max = lerp(self.size_max, 1.1, 0.4)
        self.size_skew_exponent = lerp(0.1, 0.9, r())
        self.bumps = int(self.spine_length / num)
        self.scale_x = 1.0
        self.graphic = random_range_int(rng, 0, 5)
        if self.graphic == 1:
            self.graphic = 0
        if self.graphic == 4:
            self.graphic = 3
        elif self.graphic == 3 and r() < 0.5:
            self.scale_x = -1.0
        elif r() < 1.0 / 15.0:
            self.scale_x = -1.0
        if pink and r() < 0.7:
            self.graphic = 0
        elif green and r() < 0.5:
            self.graphic = 3
        self.colored = random_range_int(rng, 0, 3)
        if pink and r() < 0.5:
            self.colored = 0
        elif green and r() < 0.5:
            self.colored = 2
        elif green and r() < 0.5:
            self.colored = 1
        self._cols_a: list = []
        self._cols_b: list = []

    def _f(self, i):
        return lerp(
            0.05, self.spine_length / self.gfx.body_and_tail_length, inverse_lerp(0, self.bumps - 1, i)
        )

    def apply_palette(self) -> None:
        g = self.gfx
        self._cols_a, self._cols_b = [], []
        for i in range(self.bumps):
            f = self._f(i)
            ca = body_color(g, f)
            self._cols_a.append(ca)
            if self.colored == 1:
                self._cols_b.append(g.effect_color)
            elif self.colored == 2:
                f2 = inverse_lerp(0, self.bumps - 1, i)
                self._cols_b.append(color_lerp(g.effect_color, ca, f2**0.5))

    def draw(self, cv, ts):
        g = self.gfx
        placed = []
        k = abs(g.depth_rotation)
        ssy = max(0.2, inverse_lerp(0.0, 0.5, k))
        for i in range(self.bumps):
            f2 = inverse_lerp(0, self.bumps - 1, i)
            sd = spine_position(g, lerp(0.05, self.spine_length / g.body_and_tail_length, f2), ts)
            rot = math.degrees(math.atan2(sd.px * sd.depth_rotation, sd.py * sd.depth_rotation))
            n3 = lerp(self.size_min, self.size_max, math.sin((f2**self.size_skew_exponent) * math.pi))
            placed.append((sd.ox, sd.oy, rot, sign(g.depth_rotation) * self.scale_x * n3, n3 * ssy))
        for i, (x, y, rot, sx, sy) in enumerate(placed):
            cv.sprite(f"LizardScaleA{self.graphic}", x, y, rot, sx, sy, self._cols_a[i], 1.0, 0.5, 0.15)
        if self.colored > 0:
            for i, (x, y, rot, sx, sy) in enumerate(placed):
                cv.sprite(f"LizardScaleB{self.graphic}", x, y, rot, sx, sy, self._cols_b[i], 1.0, 0.5, 0.15)


class TailFin(Template):
    """尾鳍：尾段上下两排鳞片（下排是 undersideSize 倍的倒影）。"""

    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        r = rng.random
        num = lerp(4.0, 7.0, r() ** 0.7)
        self.spine_length = clamped_random_variation(rng, 0.5, 0.17, 0.5) * gfx.body_and_tail_length
        self.underside_size = lerp(0.3, 0.9, r())
        self.size_min = lerp(0.1, 0.3, r() ** 2.0)
        self.size_max = lerp(self.size_min, 0.6, r())
        self.size_skew_exponent = lerp(0.5, 1.5, r())
        self.graphic = random_range_int(rng, 0, 6)
        if gfx.lizard.lizard_params.key == "red":
            self.graphic = 0
            for c in gfx.cosmetics:
                if isinstance(c, LongBodyScales):
                    self.graphic = c.graphic
                    break
            self.size_min *= 2.0
            self.size_max *= 1.5
            self.spine_length = clamped_random_variation(rng, 0.3, 0.17, 0.5) * gfx.body_and_tail_length
        self.bumps = int(self.spine_length / num)
        self.scale_x = lerp(1.0, 2.0, r())
        if self.graphic == 3 and r() < 0.5:
            self.scale_x = -self.scale_x
        elif self.graphic != 0 and r() < 1.0 / 15.0:
            self.scale_x = -self.scale_x
        self.colored = r() > 1.0 / 3.0
        self._cols: list = []

    def apply_palette(self) -> None:
        g = self.gfx
        n = self.bumps
        self._cols = [
            body_color(g, lerp(0.05, self.spine_length / g.body_and_tail_length, inverse_lerp(0, n - 1, j)))
            for j in range(n)
        ]

    def draw(self, cv, ts):
        g = self.gfx
        n = self.bumps
        dr = g.depth_rotation
        ssy = max(0.2, inverse_lerp(0.0, 0.5, abs(dr)))
        start = 1.0 - self.spine_length / g.body_and_tail_length
        under_alpha = inverse_lerp(0.3, 1.0, abs(dr)) ** 0.2
        for side in (1.0, -1.0):
            placed = []
            for j in range(n):
                t = inverse_lerp(0, n - 1, j)
                sd = spine_position(g, lerp(start, 1.0, t), ts)
                if side > 0:
                    x, y = sd.ox, sd.oy
                else:
                    x, y = sd.x + (sd.x - sd.ox) * 0.85, sd.y + (sd.y - sd.oy) * 0.85
                rx = lerp(sd.px * sd.depth_rotation, sd.dx * side, t)
                ry = lerp(sd.py * sd.depth_rotation, sd.dy * side, t)
                n4 = lerp(self.size_min, self.size_max, math.sin((t**self.size_skew_exponent) * math.pi))
                sy = n4 * ssy * (1.0 if side > 0 else -self.underside_size)
                placed.append((x, y, math.degrees(math.atan2(rx, ry)), sign(dr) * self.scale_x * n4, sy))
            for j, (x, y, rot, sx, sy) in enumerate(placed):
                cv.sprite(f"LizardScaleA{self.graphic}", x, y, rot, sx, sy, self._cols[j], 1.0, 0.5, 0.15)
            if self.colored:
                a = 1.0 if side > 0 else under_alpha
                for x, y, rot, sx, sy in placed:
                    cv.sprite(f"LizardScaleB{self.graphic}", x, y, rot, sx, sy, g.effect_color, a, 0.5, 0.15)


class BumpHawk(Template):
    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        r = rng.random
        self.colored_hawk = r() < 0.5
        if self.colored_hawk:
            num = lerp(3.0, 8.0, r() ** 0.7)
            self.spine_length = lerp(0.3, 0.7, r()) * gfx.body_and_tail_length
            self.size_min = lerp(0.1, 0.2, r())
            self.size_max = lerp(self.size_min, 0.35, r() ** 0.5)
        else:
            num = lerp(6.0, 12.0, r() ** 0.5)
            self.spine_length = lerp(0.3, 0.9, r()) * gfx.body_and_tail_length
            self.size_min = lerp(0.2, 0.3, r() ** 0.5)
            self.size_max = lerp(self.size_min, 0.5, r())
        self.size_skew_exponent = lerp(0.1, 0.7, r())
        self.bumps = int(self.spine_length / num)
        self._cols: list = []

    def apply_palette(self) -> None:
        if not self.colored_hawk:
            g = self.gfx
            n = self.bumps
            self._cols = [
                body_color(
                    g, lerp(0.05, self.spine_length / g.body_and_tail_length, inverse_lerp(0, n - 1, i))
                )
                for i in range(n)
            ]

    def draw(self, cv, ts):
        g = self.gfx
        n = self.bumps
        for i in range(n):
            f2 = inverse_lerp(0, n - 1, i)
            f = lerp(0.05, self.spine_length / g.body_and_tail_length, f2)
            sd = spine_position(g, f, ts)
            s = lerp(
                self.size_min,
                self.size_max,
                lerp(math.sin((f2**self.size_skew_exponent) * math.pi), 1.0, 0.5 if f2 < 0.5 else 0.0),
            )
            col = color_lerp(head_color(g, ts), body_color(g, f), f2) if self.colored_hawk else self._cols[i]
            cv.circle(sd.ox, sd.oy, 10.0 * s, col)


_drng = random.Random()  # 绘制时的随机（不动模拟的随机序列）
_WHITE = (1.0, 1.0, 1.0)


def _is_anim(g, name: str) -> bool:
    return getattr(g.lizard.animation, "name", "") == name


def _norm(x: float, y: float):
    m = math.hypot(x, y)
    return (x / m, y / m) if m > 1e-5 else (0.0, 0.0)


def _dv(ax: float, ay: float, bx: float, by: float):
    """Custom.DirVec：重合返回 (0, 1)。"""
    if ax == bx and ay == by:
        return (0.0, 1.0)
    return _norm(bx - ax, by - ay)


class WingScales(Template):
    """青蜥蜴背上的两侧翅鳞（每侧 2 或 3 片）：质点系，随头 / 脊线深度旋转摆动。"""

    sprites_overlap = "InFront"

    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        r = rng.random
        cols = 3 if r() < 0.2 else 2
        self.graphic = 0 if r() < 0.4 else random_range_int(rng, 0, 5)
        self.sturdy = r()
        self.pos_squeeze = r()
        self.scale_length = lerp(5.0, 40.0, r() ** (0.75 + 1.25 * self.sturdy))
        self.front_dir = lerp(-0.1, 0.2, r())
        self.back_dir = lerp(max(0.0, self.front_dir), self.front_dir + cols * 0.2, r())
        chunk = gfx.lizard.body_chunks[1]
        self.scales = [
            [GenericBodyPart(gfx, 2.0, 0.5, lerp(0.8, 0.999, self.sturdy), chunk) for _ in range(cols)]
            for _ in range(2)
        ]
        self.cols = cols
        self._height = None

    def reset(self) -> None:
        for row in self.scales:
            for s in row:
                s.pos = s.connection.pos
                s.last_pos = s.connection.pos
                s.vel = V2()

    def _sample(self, i: int) -> float:
        return 0.025 + (0.025 + 0.15 * i) * self.pos_squeeze

    def update(self) -> None:
        g = self.gfx
        L = g.lizard
        chunk1 = L.body_chunks[1]
        for i in range(self.cols):
            num = lerp_map(i, 0.0, self.cols - 1, self.front_dir, self.back_dir)
            sd = spine_position(g, self._sample(i), 1.0)
            f = lerp(g.head_depth_rotation, sd.depth_rotation, 0.3 + 0.2 * i)
            pos, perp, fwd = V2(sd.x, sd.y), V2(sd.px, sd.py), V2(sd.dx, sd.dy)
            for j in range(2):
                side = -1.0 if j == 0 else 1.0
                vector = pos + perp * (side * sd.rad * (1.0 - abs(f)))
                v2 = perp * (side * (1.0 - abs(f)))
                v2 = vslerp(v2, fwd * num, abs(num))
                v2 = vslerp(v2, perp * sign(f), abs(f) * 0.5)
                v3 = vector + v2 * (self.scale_length * 1.5)
                s = self.scales[j][i]
                s.update()
                s.connect_to_point(
                    vector,
                    self.scale_length * (0.6 if i > 1 else 1.0),
                    False,
                    0.0,
                    chunk1.vel,
                    0.1 + 0.2 * self.sturdy,
                    0.0,
                )
                s.vel = s.vel + (v3 - s.pos) * lerp(0.1, 0.3, self.sturdy)
                s.pos = s.pos + (v3 - s.pos) * (0.6 * self.sturdy**3)
        if not _is_anim(g, "PrepareToJump") or not L.consious:
            return
        r = self.rng.random
        toward = dir_vec(chunk1.pos, L.body_chunks[0].pos)
        for row in self.scales:
            for s in row:
                s.vel = s.vel + rnv(self.rng) * (3.0 * r()) + toward * (r() * 5.0)
                s.pos = s.pos + rnv(self.rng) * (3.0 * r())

    def draw(self, cv, ts):
        g = self.gfx
        name = f"LizardScaleA{self.graphic}"
        if self._height is None:
            self._height = cv.source_height(name)
        out = []
        for j in range(2):
            side = -1.0 if j == 0 else 1.0
            for i in range(self.cols):
                sd = spine_position(g, self._sample(i), ts)
                k = side * sd.rad * (1.0 - abs(sd.depth_rotation))
                x, y = sd.x + sd.px * k, sd.y + sd.py * k
                s = self.scales[j][i]
                lp, pp = s.last_pos, s.pos
                ex, ey = lp.x + (pp.x - lp.x) * ts, lp.y + (pp.y - lp.y) * ts
                out.append(
                    (
                        x,
                        y,
                        math.degrees(math.atan2(ex - x, ey - y)),
                        side,
                        math.hypot(x - ex, y - ey) / self._height,
                    )
                )
        for x, y, rot, side, sy in out:
            cv.sprite(name, x, y, rot, side, sy, BLACK_COLOR, 1.0, 0.5, 0.0)


class TailGeckoScales(Template):
    """青蜥蜴尾上的壁虎鳞：小星点；尾巴有色时是随深度旋转的大圆鳞。"""

    def __init__(self, gfx, rng):
        super().__init__(gfx, rng)
        r = rng.random
        self.rows = random_range_int(rng, 7, 14)
        self.lines = random_range_int(rng, 3, random_range_int(rng, 3, 4))
        self.big = False
        tc = gfx.i_vars.tail_color
        if tc > 0.1 and r() < lerp(0.7, 0.99, tc):
            self.big = True
            for c in gfx.cosmetics:
                if isinstance(c, WingScales):
                    if c.scale_length > 10.0:
                        self.big = False
                    break
        if r() < 0.5:
            self.rows += random_range_int(rng, 0, random_range_int(rng, 0, 7))
            self.lines += random_range_int(rng, 0, random_range_int(rng, 0, 3))

    def draw(self, cv, ts):
        g = self.gfx
        rows, lines = self.rows, self.lines
        depth = lerp(g.last_depth_rotation, g.depth_rotation, ts)
        eff = g.effect_color
        tc = g.i_vars.tail_color
        if self.big:
            prev = spine_position(g, 0.4, ts)
            for i in range(rows):
                num = inverse_lerp(0.0, rows - 1, i)
                num2 = lerp(0.5, 0.99, num**0.8)
                sd = spine_position(g, num2, ts)
                a = body_color(g, num2)
                for j in range(lines):
                    num3 = -1.0 + 2.0 * ((j + (0.5 if i % 2 == 0 else 0.0)) / (lines - 1)) + depth
                    if num3 < -1.0:
                        num3 += 2.0
                    elif num3 > 1.0:
                        num3 -= 2.0
                    k1, k2 = (prev.rad + 0.5) * num3, (sd.rad + 0.5) * num3
                    vx, vy = prev.x + prev.px * k1, prev.y + prev.py * k1
                    wx, wy = sd.x + sd.px * k2, sd.y + sd.py * k2
                    ang = math.degrees(math.atan2(wx - vx, wy - vy))
                    sx = lerp_map(abs(num3), 0.4, 1.0, sd.rad * 3.5 / rows, 0.0) / 10.0
                    sy = math.hypot(wx - vx, wy - vy) * 1.1 / 20.0
                    if tc > 0.0:
                        ux, uy = _dv(wx, wy, vx, vy)
                        e = (-45.0 + 120.0 * num3) * DEG
                        n4 = inverse_lerp(0.5, 1.0, abs(ux * math.sin(e) + uy * math.cos(e)))
                        n4 = lerp_map(abs(num3), 0.5, 1.0, 0.3, 0.0) + 0.7 * (n4 * tc**0.3) ** lerp(
                            2.0, 0.5, num
                        )
                        if num < 0.5:
                            n4 *= lerp_map(num, 0.0, 0.5, 0.2, 1.0)
                        n4 = n4 ** lerp(2.0, 0.5, num)
                        if n4 < 0.5:
                            col = color_lerp(a, eff, inverse_lerp(0.0, 0.5, n4))
                        else:
                            col = color_lerp(eff, _WHITE, inverse_lerp(0.5, 1.0, n4))
                    else:
                        t = lerp_map(abs(num3), 0.5, 1.0, 0.8, 0.4)
                        col = color_lerp(a, eff, lerp_map(num, 0.0, 0.8, 0.2, t, 0.8))
                    cv.sprite("Circle20", (vx + wx) * 0.5, (vy + wy) * 0.5, ang, sx, sy, quantize(col))
                prev = sd
            return
        for k in range(rows):
            f = inverse_lerp(0.0, rows - 1, k)
            num5 = lerp(0.4, 0.95, f**0.8)
            sd = spine_position(g, num5, ts)
            col = quantize(color_lerp(body_color(g, num5), eff, 0.2 + 0.8 * f**0.5))
            rot = math.degrees(math.atan2(sd.dx, sd.dy))
            for n in range(lines):
                n6 = -1.0 + 2.0 * ((n + (0.5 if k % 2 == 0 else 0.0)) / (lines - 1)) + depth
                if n6 < -1.0:
                    n6 += 2.0
                elif n6 > 1.0:
                    n6 -= 2.0
                n6 = sign(n6) * abs(n6) ** 0.6
                kk = (sd.rad + 0.5) * n6
                cv.sprite(
                    "tinyStar",
                    sd.x + sd.px * kk,
                    sd.y + sd.py * kk,
                    rot,
                    lerp_map(abs(n6), 0.4, 1.0, 1.0, 0.0),
                    1.0,
                    col,
                )


class JumpRings(Template):
    """青蜥蜴脖子上的两圈跳跃环：准备起跳时亮起。"""

    sprites_overlap = "InFront"

    def draw(self, cv, ts):
        g = self.gfx
        L = g.lizard
        b = lerp(g.last_depth_rotation, g.depth_rotation, ts)
        a = lerp(g.last_head_depth_rotation, g.head_depth_rotation, ts)
        color = head_color(g, ts)
        num = 1.0
        if _is_anim(g, "PrepareToJump"):
            num = 0.5 + 0.5 * inverse_lerp(L.time_to_remain_in_animation, 0.0, L.time_in_animation)
            color = quantize(color_lerp(color, color_lerp(_WHITE, g.effect_color, num), _drng.random()))
        fr = frame_at(g, ts)
        d0x, d0y, hx, hy = fr.dx[0], fr.dy[0], fr.hx, fr.hy
        tx, ty = fr.tx[0], fr.ty[0]
        hdx, hdy = _dv(d0x, d0y, hx, hy)
        parts: list = [[], []]
        for i in range(2):
            sd = spine_position(g, 0.06 + 0.12 * i, ts)
            dx, dy = sd.dx, sd.dy
            if i == 0:
                dx, dy = _norm(dx - hdx, dy - hdy)
            qx, qy = -dy, dx
            m = math.hypot(qx, qy)
            if m > 1e-5:
                qx, qy = qx / m, qy / m
            num2 = 50.0 * lerp(a, b, 0.25 if i == 0 else 0.5)
            for j in range(2):
                e = (num2 + (-40.0 if j == 0 else 40.0)) * DEG
                v3x, v3y = math.sin(e), math.cos(e)
                px, py = sd.x + qx * (sd.rad * v3x), sd.y + qy * (sd.rad * v3x)
                if i != 0:
                    ux, uy = _dv(px, py, tx, ty)
                    v4x, v4y = _norm(dx + ux * (2.0 * abs(v3y)), dy + uy * (2.0 * abs(v3y)))
                else:
                    ux, uy = _dv(px, py, hx, hy)
                    v4x, v4y = _norm(dx - ux * (2.0 * abs(v3y)), dy - uy * (2.0 * abs(v3y)))
                rot = math.degrees(math.atan2(v4x, v4y))
                k = (sd.rad + 2.0 * min(1.0, abs(v3x) * abs(v3y)) ** 0.5) * v3x
                p2x = sd.x + qx * k - v4x * ((1.0 - num) * 4.0)
                p2y = sd.y + qy * k - v4y * ((1.0 - num) * 4.0)
                t = min(1.0, abs(v3x)) ** 2
                s0 = lerp(0.45, 0.0, t) if v3y > 0.0 else 0.0
                s1 = lerp(0.27, 0.0, t) * num if v3y > 0.0 else 0.0
                parts[0].append((px, py, rot, s0, 0.55, color))
                parts[1].append((p2x, p2y, rot, s1, 0.33 * num, BLACK_COLOR))
        # RingSprite(ring, side, part) = part * 4 + side * 2 + ring，按序号从低到高画
        for part in range(2):
            for side in range(2):
                for ring in range(2):
                    x, y, rot, sx, sy, col = parts[part][ring * 2 + side]
                    if sx > 0.0:
                        cv.sprite("Circle20", x, y, rot, sx, sy, col)


def build_cosmetics(gfx, rng: random.Random) -> list:
    """LizardGraphics 构造函数里挑装饰件的那一段。gfx.cosmetics 边建边填，TailTuft / TailFin 要读它。"""
    key = gfx.lizard.lizard_params.key
    green, pink, blue, red = key == "green", key == "pink", key == "blue", key == "red"
    r = rng.random
    out: list = []
    gfx.cosmetics = out
    r()  # blackSalamander = Random.value < 1/3：盐螈才用，随机数照常消耗
    if key == "cyan":
        if r() < 0.75:
            out.append(WingScales(gfx, rng))
        if r() < 0.5 and gfx.i_vars.tail_color == 0.0:
            out.append(TailTuft(gfx, rng))
        else:
            out.append(TailGeckoScales(gfx, rng))
        out.append(JumpRings(gfx, rng))
        return out
    if key == "white":
        return out
    num8 = 0
    flag = False
    flag2 = False
    # 脊刺条件里 (Random.value < 0.7f && 黑蜥蜴) 的随机数也照取
    if r() < 1.0 / 15.0 or (r() < 0.8 and green) or (r() < 0.7 and False):
        out.append(SpineSpikes(gfx, rng))
        num8 += 1
    elif r() < 1.0 / 30.0:
        out.append(BumpHawk(gfx, rng))
        num8 += 1
    elif r() < 1.0 / 21.0 or (pink and r() < 0.5) or (red and r() < 0.9):
        out.append(LongShoulderScales(gfx, rng))
        flag = True
        num8 += 1
    elif r() < 0.0625 or (blue and r() < 0.5):
        out.append(ShortBodyScales(gfx, rng))
        flag2 = True
        num8 += 1
    elif green and r() < 0.5:
        out.append(ShortBodyScales(gfx, rng))
        flag2 = True
        num8 += 1
    if r() < 1.0 / 9.0 or (num8 == 0 and r() < 0.7) or (pink and r() < 0.6) or (blue and r() < 0.96):
        out.append(TailTuft(gfx, rng))
    elif num8 < 2 and green and r() < 0.7:
        if r() < 0.5 or flag or flag2:
            out.append(TailTuft(gfx, rng))
        else:
            out.append(LongShoulderScales(gfx, rng))
            flag = True
            num8 += 1
    if r() < (0.7 if num8 == 0 else 0.1) and ((not flag and r() < 0.9) or r() < 1.0 / 30.0):
        out.append(LongHeadScales(gfx, rng))
    if red:
        out.append(LongShoulderScales(gfx, rng))
        out.append(SpineSpikes(gfx, rng))
        out.append(TailFin(gfx, rng) if r() < 0.5 else TailTuft(gfx, rng))
    return out
