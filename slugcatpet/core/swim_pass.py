"""水里两只猫迎面或贴身时上下错开：一只小跳到水面、一只往下潜，交错游过去。"""

from __future__ import annotations

import math
import random
from typing import NamedTuple

from .. import tuning
from . import chunkphys as cp
from .units import clampf, lerp


class Neighbor(NamedTuple):
    x: float
    y: float
    vx: float
    ix: float  # 想游的方向
    iy: float
    yielding: bool  # 正在错开或刚错开完
    dive: bool  # 这一轮它负责下潜
    rank: int  # 猫的序号，双方对冲时据此分工
    detouring: bool  # 被夹住正在绕路


class SwimPass:
    def __init__(self, body):
        self.body = body
        self.neighbors = None
        self.rank = 0
        self.cd = 0
        self.ticks = 0
        self.dive = False
        self.side = 0.0
        self.target_y = None
        self.air_falling = 0
        self._air_prev = 1.0

    @property
    def active(self):
        return self.ticks > 0

    @property
    def detouring(self):
        return self.air_falling >= tuning.SWIM_DETOUR_DELAY

    def reset(self):
        self.neighbors = None
        self.ticks = 0
        self.target_y = None
        self.air_falling = 0

    def as_neighbor(self):
        b = self.body
        ix, iy = b._swim_dir()
        return Neighbor(
            b.chunk0.x, b.chunk0.y, b.chunk0.vx, ix, iy, self.cd > 0, self.dive, self.rank, self.detouring
        )

    def step(self, ws):
        b = self.body
        near, self.neighbors = self.neighbors, None
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
        if not near:
            self.dive = False
            return
        self._track_air()
        c0 = b.chunk0
        cx, cy = c0.x, c0.y
        contact = c0.rad + cp.RAD0 + tuning.SWIM_SHOVE_CONTACT_PAD
        mx, my = b._swim_dir()
        has_intent = mx != 0.0 or my != 0.0
        left = right = 0
        near_x, near_vx = None, 0.0
        for o in sorted(near, key=lambda n: (n.x, n.y, n.rank)):
            dx, dy = o.x - cx, o.y - cy
            d = math.hypot(dx, dy)
            if d > tuning.SWIM_AVOID_TRIGGER_DIST or d < 1e-6:
                continue
            if d <= contact and not o.detouring:
                if o.x < cx:
                    left += 1
                else:
                    right += 1
                if near_x is None:
                    near_x, near_vx = o.x, o.vx
            # 我正朝它游：它也朝我来（对冲）或已经贴上（堵路）才错开
            if not has_intent or o.yielding:
                continue
            if (mx * dx + my * dy) / d <= tuning.SWIM_INTENT_DOT:
                continue
            toward = (abs(o.ix) > 1e-3 or abs(o.iy) > 1e-3) and -(
                o.ix * dx + o.iy * dy
            ) / d > tuning.SWIM_INTENT_DOT
            if toward:
                self._start(ws, dive=self.rank < o.rank, ovx=o.vx, ox=o.x)
                return
            if d <= contact:
                self._start(ws, dive=o.dive, ovx=o.vx, ox=o.x)
                return
        if left and right:
            self._detour(ws, cx, near_x, near_vx)
            return
        self.air_falling = 0
        self.dive = False
        return

    def mode(self):
        if self.ticks <= 0:
            return None
        return "deep" if self.dive else "surface"

    def _track_air(self):
        b = self.body
        self.air_falling = self.air_falling + 1 if b.air_in_lungs < self._air_prev else 0
        self._air_prev = b.air_in_lungs

    def _detour(self, ws, cx, near_x, near_vx):
        b = self.body
        if not b.no_dive and not self.detouring:
            return
        self.air_falling = max(self.air_falling, tuning.SWIM_DETOUR_DELAY)
        if b.swim_resting and not b.no_dive:
            self._start(ws, dive=False, ovx=near_vx, ox=near_x)
        else:
            side = 1.0 if cx < b.W * 0.5 else -1.0
            self._start(ws, dive=True, ovx=-side, ox=near_x, ticks=tuning.SWIM_DETOUR_TICKS)
        return

    def _start(self, ws, dive, ovx=0.0, ox=None, ticks=None):
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
            sx = 1.0 if (ox is None or c0.x >= ox) else -1.0
        self.side = sx
        self.ticks = tuning.SWIM_PASS_TICKS if ticks is None else ticks
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
