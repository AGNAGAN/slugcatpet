"""雨 pip 环：照原版 RainMeter 的排布、消耗、展开与半程闪烁，40 tick/s。"""

from __future__ import annotations
import math

from .ladder import inv_lerp, lerp, s_curve

FADE_IN = 1.0 / 30.0
FADE_OUT = 0.1
PLOP_RATE = 0.05
BLINK_TICKS = 220  # 半程闪烁时长
RING_GAP = 8.5  # pip 环在业力符号外的距离

DRAIN, HOLLOW = "drain", "hollow"


class PipRing:
    """mode：drain 晴天逐个熄灭，hollow 空闲时全空心。"""

    def __init__(self):
        self.fade = 0.0
        self.plop = 0.0
        self.blink = 0
        self.tick_pulse = 0.0

    def update(self, show):
        self.fade = min(1.0, self.fade + FADE_IN) if show else max(0.0, self.fade - FADE_OUT)
        self.plop = min(1.0, self.plop + PLOP_RATE) if self.fade >= 0.7 else 0.0
        if self.blink > 0:
            self.blink -= 1
        self.tick_pulse = lerp(self.tick_pulse, 0.0, 0.1)

    def start_blink(self):
        self.blink = BLINK_TICKS

    def circles(self, n, frac, mode, radius):
        """各 pip 的 (x, y, 半径, 线宽)，y 向上为正，线宽 -1 为实心；frac 是剩余比例。"""
        out = []
        fade = self.fade
        if fade <= 0.0 or n <= 0:
            return out
        wave = lerp((1.0 - frac) * fade - 0.075, 1.075, self.plop**0.85)
        for i in range(n):
            num = i / (n - 1) if n > 1 else 0.0
            bulge = inv_lerp(0.075, 0.0, abs(1.0 - num - wave)) * 2.0 * fade
            if mode == DRAIN:
                value = inv_lerp(i / n, (i + 1) / n, frac)
                hollow = inv_lerp(0.5, 0.475, abs(0.5 - inv_lerp(1.0 / 30.0, 1.0, value)))
                if self.blink > 0:
                    hollow = max(hollow, 0.0 if self.blink % 15 < 7 else 1.0)
                rad = ((2.0 + hollow) * fade**2 + bulge) * inv_lerp(0.0, 1.0 / 30.0, value)
                thick = -1.0 if hollow == 0.0 else lerp(3.5, 1.0, hollow)
            else:
                hollow = 1.0
                rad = 3.0 * fade**2 + bulge
                thick = 1.0
            if rad <= 0.05:
                continue
            ang = math.radians((1.0 - i / n) * 360.0 * s_curve(fade ** (1.5 - num), 0.6))
            r = radius + RING_GAP + hollow + 4.0 * self.tick_pulse
            out.append((math.sin(ang) * r, math.cos(ang) * r, rad, thick))
        return out
