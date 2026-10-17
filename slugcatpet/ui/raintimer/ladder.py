"""业力梯：照原版雨眠后的 KarmaLadder 移植的升档与顶格动画，40 tick/s。"""

from __future__ import annotations
import math
import random

RESTING, DESELECTING, MOVING_A, MOVING_B, SETTLING, BUMP, CAPPED, CAP_BUMP = range(8)
SPACING = 100.0  # 相邻符号的竖直间距
SYMBOL = 63.0  # 符号贴图边长


def lerp(a, b, t):
    return a + (b - a) * t


def inv_lerp(a, b, v):
    if a == b:
        return 0.0
    return max(0.0, min(1.0, (v - a) / (b - a)))


def lerp_and_tick(frm, to, t, tick):
    v = lerp(frm, to, t)
    return min(v + tick, to) if v < to else max(v - tick, to)


def s_curve(x, k):
    x = x * 2.0 - 1.0
    if x < 0.0:
        x = abs(1.0 + x)
        return k * x / (k - x + 1.0) * 0.5
    k = -1.0 - k
    return 0.5 + k * x / (k - x + 1.0) * 0.5


class Symbol:
    def __init__(self, k):
        self.k = k
        self.energy = 1.0
        self.line_width = 0.0
        self.flicker = 0

    def update(self, ladder, nxt):
        """亮度回升与闪烁；line_width 是它和上一档之间的分隔线。"""
        if ladder.phase == MOVING_A:
            to = 1.0
        else:
            to = max(0.0, min(1.0, min(abs(self.k - ladder.scroll), abs(self.k + 1 - ladder.scroll))))
        if nxt is not None:
            self.line_width *= (self.energy + nxt.energy) / 2.0
        self.line_width = lerp_and_tick(self.line_width, to, 0.2, 0.1)
        rng = ladder.rng
        if rng.random() > inv_lerp(5.0, 40.0, self.flicker):
            self.energy = lerp_and_tick(self.energy, 1.0, 0.1, 1.0 / 70.0)
        if self.flicker > 0:
            self.flicker -= 1
            if rng.random() < inv_lerp(5.0, 19.0, self.flicker):
                p = 3.0 + (0.2 - 3.0) * inv_lerp(50.0, 2.0, self.flicker)
                self.energy = min(self.energy, lerp(self.energy, rng.random() ** p, 0.5))


class FadeCircle:
    def __init__(self, rad, speed, slow, life_ticks, thickness):
        self.rad, self.speed, self.slow = rad, speed, slow
        self.life_ticks, self.thickness0 = life_ticks, thickness
        self.life = 1.0

    def update(self):
        self.rad += self.speed
        self.speed *= self.slow
        self.life -= 1.0 / self.life_ticks

    @property
    def alpha(self):
        return max(0.0, self.life) ** 0.5 * 0.15

    @property
    def thickness(self):
        return max(0.0, self.life) * self.thickness0


class KarmaLadder:
    """display 为当前档，cap 为顶档；go_to 之后每 tick 调 update，sound(name) 在该响的时刻回调。"""

    def __init__(self, display, cap, sound=None, rng=None):
        self.cap = cap
        self.display = display
        self.move_to = display
        self.scroll = float(display)
        self.scroll_vel = 0.0
        self.last_scroll = self.scroll
        self.flat = 1.0
        self.circle_rad = 53.0
        self.circle_thick = 3.0
        self.selection_glow = 0.0
        self.selector_white = 0.0
        self.increasing = False
        self.capped = False
        self.started = False
        self.phase = RESTING
        self.ticks = 0
        self.symbols = [Symbol(k) for k in range(cap + 1)]
        self.fade_circles: list[FadeCircle] = []
        self.rng = rng or random.Random()
        self._sound = sound or (lambda name: None)

    @property
    def moving(self) -> float:
        """滚动速度，驱动转轮的循环音。"""
        return abs(self.scroll - self.last_scroll)

    @property
    def done(self) -> bool:
        return self.started and self.phase == RESTING and self.display == self.move_to

    def go_to(self, k):
        self.move_to = k
        self.increasing = k > self.display
        self.capped = k < 0 or k > self.cap
        self.started = True

    def update(self):
        self.last_scroll = self.scroll
        for i, s in enumerate(self.symbols):
            s.update(self, self.symbols[i + 1] if i + 1 < len(self.symbols) else None)
        for c in self.fade_circles:
            c.update()
        self.fade_circles = [c for c in self.fade_circles if c.life > 0.0]

        self.scroll += self.scroll_vel
        self.selection_glow = lerp_and_tick(self.selection_glow, 1.0, 0.2, 0.0125)
        self.circle_thick = 3.0
        self.selector_white = 0.0
        self.ticks += 1
        getattr(self, "_p%d" % self.phase)()

    # 各阶段，对应原版 KarmaLadder.Update

    def _p0(self):  # RESTING
        self.circle_rad = lerp_and_tick(self.circle_rad, 51.5, 0.08, 0.01)
        self.flat = 1.0
        self.scroll_vel *= 0.3
        self.scroll = lerp(self.scroll, self.display, 0.2)
        if self.display != self.move_to and self.started:
            self._new_phase(DESELECTING)

    def _p1(self):  # DESELECTING
        self.circle_rad = lerp_and_tick(self.circle_rad, 55.0, 0.08, 0.01)
        f = inv_lerp(0.0, 30.0, self.ticks)
        if self.rng.random() < f:
            self.selection_glow = lerp(self.rng.random(), 0.0, f)
        self.flat = 1.0 - f
        if f >= 1.0:
            if self.capped:
                self._new_phase(CAPPED)
            else:
                self._new_phase(MOVING_A)
                self.scroll_vel += math.copysign(0.01, self.display - self.move_to)

    def _p2(self):  # MOVING_A
        self._moving(True)

    def _p3(self):  # MOVING_B
        self._moving(False)

    def _moving(self, first):
        self.circle_rad = lerp_and_tick(self.circle_rad, 50.0, 0.1, 0.1)
        self.selection_glow = 0.0
        sign = math.copysign(1.0, self.move_to - self.display)
        goal = self.move_to + sign * -0.049 * (1.0 if first else 0.0)
        self.flat = 0.0
        self.scroll_vel += (goal - self.scroll) / (400.0 if first else 3.0)
        self.scroll_vel += math.copysign(0.001, goal - self.scroll)
        self.scroll_vel *= 0.95 if first else 0.9
        if ((self.scroll < goal) == (self.move_to < self.display)) == first:
            self._new_phase(MOVING_B if first else SETTLING)

    def _p4(self):  # SETTLING
        f = inv_lerp(0.0, 40.0, self.ticks)
        self.scroll_vel *= 0.6
        self.scroll = lerp(self.scroll, self.display, 0.2)
        if self.increasing:
            self.circle_rad = 51.5 + math.sin(f * math.pi * 1.5) * 3.0 + math.sin(f * math.pi) * 3.0
            if not self.capped:
                self.circle_thick = 3.0 + 3.0 * math.sin(f**5 * math.pi)
                self.selector_white = inv_lerp(0.3, 0.6, f)
            self.selection_glow = math.sin(f**5 * math.pi) * 0.4
            self.flat = 0.0
        else:
            self.circle_rad = 51.5 + math.sin(f * math.pi) * 3.0
            self.flat = lerp(self.flat, 1.0, f**4)
            self.selection_glow *= 0.9
        if f >= 1.0:
            if self.increasing and self.capped:
                self._new_phase(CAP_BUMP)
            elif self.increasing:
                self._new_phase(BUMP)
            else:
                self._new_phase(RESTING)

    def _p5(self):  # BUMP
        self._bump(50.0, 2.0, 1.0, (26.0, 0.88, 60.0, 6.0), "bump")
        if self.ticks == 5:
            for s in self.symbols:
                if s.k != self.display:
                    s.energy = 0.0
        elif self.ticks == 6:
            for s in self.symbols:
                if s.k != self.display:
                    s.flicker = max(s.flicker, self.rng.randint(12, self.rng.randint(40, 80)))
                    if abs(s.k - self.display) < 2:
                        s.flicker += self.rng.randint(20, 30)

    def _p6(self):  # CAPPED
        f = inv_lerp(0.0, 15.0, self.ticks)
        self.circle_rad = lerp_and_tick(self.circle_rad, 50.0, 0.1, 0.1)
        self.selection_glow = 0.0
        self.flat = 0.0
        self.scroll_vel *= lerp(1.0, 0.92, f**6)
        if self.ticks == 9:
            self._sound("cap_hit")
        away = math.copysign(0.001, self.display - self.move_to)
        self.scroll_vel += -away if f < 0.5 else away
        if f >= 1.0:
            self.move_to = self.display
            self._new_phase(SETTLING)

    def _p7(self):  # CAP_BUMP
        self._bump(20.0, 1.0, 0.5, (16.0, 0.82, 40.0, 6.0), "cap_bump")

    def _bump(self, swell, sink, glow, ring, sound):
        self.scroll_vel *= 0.4
        self.scroll = lerp(self.scroll, self.display, 0.2)
        f = inv_lerp(0.0, 45.0, self.ticks)
        self.circle_rad = 53.0 + lerp(swell, 0.0, f**0.13) - sink * inv_lerp(0.8, 1.0, f)
        self.selection_glow = (1.0 + glow * math.sin(f**0.2 * math.pi)) * (1.0 - f) ** 0.4
        self.flat = f**0.3
        if self.ticks == 4:
            self.fade_circles.append(FadeCircle(self.circle_rad, *ring))
            self._sound(sound)
        if f >= 1.0:
            self._new_phase(RESTING)

    def _new_phase(self, nxt):
        self.ticks = -1
        if nxt == DESELECTING:
            self._sound("deselect")
        elif nxt in (MOVING_A, CAPPED):
            self._sound("start_moving")
        elif nxt == SETTLING:
            self.display = self.move_to
        self.phase = nxt

    # 绘制用的读数，对应原版 KarmaSymbol.GrafUpdate

    def layout(self, k):
        """第 k 档符号相对中心的 (y 偏移, 竖直缩放)，转到背面时返回 None；y 向上为正。"""
        t = s_curve(self.flat, 0.09)
        r = lerp(250.0, 1000.0, t)
        circ = 2.0 * r * math.pi
        ang = (k - self.scroll) * (360.0 / circ) * 100.0
        if abs(ang) > 90.0:
            return None
        half = SYMBOL / circ * 180.0
        a = r * math.sin(math.radians(ang + half))
        b = r * math.sin(math.radians(ang - half))
        y = lerp((a + b) * 0.5, (k - self.scroll) * SPACING, t)
        return y, lerp(abs(a - b) / SYMBOL, 1.0, t)

    def line_y(self, k):
        """第 k 档与 k+1 档之间分隔线的 y 偏移，背面时为 None。"""
        t = s_curve(self.flat, 0.09)
        r = lerp(250.0, 1000.0, t)
        circ = 2.0 * r * math.pi
        if abs((k - self.scroll) * (360.0 / circ) * 100.0) > 90.0 or k >= self.cap:
            return None
        ang = (k + 0.5 - self.scroll) * (360.0 / circ) * 100.0
        return lerp(r * math.sin(math.radians(ang)), (k + 0.5 - self.scroll) * SPACING, t)

    def selected(self, k) -> float:
        """离选中位置的远近 0~1，0 为正中。"""
        return max(0.0, min(1.0, abs(k - self.scroll) / 0.75))

    def glow(self, k):
        """第 k 档的两层光晕 ((半径, 不透明度), (半径, 不透明度))，不亮时为 None。"""
        d = self.selected(k)
        if d >= 0.2:
            return None
        g = inv_lerp(0.2, 0.1, d) * (0.3 + 0.7 * max(0.0, min(1.0, self.selection_glow)))
        g2 = inv_lerp(1.0, 2.0, self.selection_glow)
        outer = (lerp(70.0, 150.0, g**0.5) + g2 * 50.0, lerp(0.2 * g**1.5, 0.4, g2))
        inner = (lerp(50.0, 90.0, g) + g2 * 100.0, lerp(0.4 * g**0.5, 0.8, g2))
        return outer, inner
