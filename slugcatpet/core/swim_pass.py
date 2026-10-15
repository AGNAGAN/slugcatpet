"""水里错开别的猫的动作：下潜从下面过，或从水面小跳过去；谁错开由多猫通行决定。"""

from __future__ import annotations

import random

from .. import tuning
from .units import clampf, lerp


class SwimPass:
    def __init__(self, body):
        self.body = body
        self.cd = 0
        self.ticks = 0
        self.dive = False
        self.side = 0.0
        self.target_y = None
        self._want = None  # 待执行的 (下潜, 对方 x, 对方 vx)

    @property
    def active(self):
        return self.ticks > 0

    @property
    def busy(self):
        """正在错开、刚错开完或已有待执行的请求。"""
        return self.ticks > 0 or self.cd > 0 or self._want is not None

    def request(self, dive, ox, ovx):
        """错开对方：dive 下潜，否则从水面小跳过去。"""
        if not self.busy:
            self._want = (dive, ox, ovx)

    def reset(self):
        self.ticks = 0
        self.target_y = None
        self._want = None

    def step(self, ws):
        b = self.body
        want, self._want = self._want, None
        if b.stun > 0 or b.dead:
            return
        if self.ticks > 0:
            self.ticks -= 1
            self._apply(ws)
            if self.ticks == 0:
                self.cd = tuning.SWIM_PASS_COOLDOWN
                self.target_y = None
            return
        if self.cd > 0:
            self.cd -= 1
            return
        if want is not None:
            dive, ox, ovx = want
            self._start(ws, dive=dive, ovx=ovx, ox=ox)

    def mode(self):
        if self.ticks <= 0:
            return None
        return "deep" if self.dive else "surface"

    def _start(self, ws, dive, ovx=0.0, ox=None):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        self.dive = bool(dive)
        if self.dive:
            if ovx > 0.0:
                sx = -1.0
            elif ovx < 0.0:
                sx = 1.0
            else:
                sx = 1.0 if c0.x >= b.W * 0.5 else -1.0
        else:
            sx = -1.0 if (ox is None or c0.x >= ox) else 1.0
        self.side = sx
        self.ticks = tuning.SWIM_PASS_TICKS
        self.target_y = None
        if self.dive:
            c0.vy += tuning.SWIM_PASS_DIVE_KICK
        else:
            f = b.stats.swim_leap_fac
            c0.vy -= tuning.SWIM_LEAP_HEAD * f
            c1.vy -= tuning.SWIM_LEAP_FEET * f
            c0.vx += sx * tuning.SWIM_LEAP_VX * f
            c1.vx += sx * tuning.SWIM_LEAP_VX * f
        self._apply(ws)

    def _apply(self, ws):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        if self.dive:
            if self.target_y is None:
                lvl = ws.level_at(c0.x) if ws is not None else c0.y
                self.target_y = lvl + lerp(
                    tuning.SWIM_PASS_DIVE_MIN, tuning.SWIM_PASS_DIVE_MAX, random.random()
                )
            for c in (c0, c1):
                c.vy += clampf(
                    (self.target_y - c.y) * tuning.SWIM_PASS_SINK_GAIN,
                    -tuning.SWIM_PASS_SINK_ACCEL_CAP,
                    tuning.SWIM_PASS_SINK_ACCEL_CAP,
                )
                c.vy = min(c.vy, tuning.SWIM_PASS_DIVE_CAP)
            evade = tuning.SWIM_PASS_EVADE_VX
        else:
            for c in (c0, c1):
                c.vy = min(c.vy, tuning.SWIM_LEAP_FALL_CAP)
            evade = tuning.SWIM_LEAP_EVADE_VX
        sx, _ = b._swim_dir()
        if sx > tuning.SWIM_TURN_DOT:
            tgt = b.stats.swim_surface_speed
        elif sx < -tuning.SWIM_TURN_DOT:
            tgt = -b.stats.swim_surface_speed
        else:
            tgt = self.side * evade
        c0.vx += (tgt - c0.vx) * 0.22
        c1.vx += (tgt - c1.vx) * 0.22
