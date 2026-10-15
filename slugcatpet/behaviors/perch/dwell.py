"""在落脚点待着的小动作。"""

from __future__ import annotations

from ...planning.climbmoves import (
    PullUpMotion,
    climb_tick,
    climb_toward,
    hang_tick,
    stand_tick,
    stand_toward,
    tip_step,
)

STAND_SHIFT_PROB = 1.0 / 180.0  # 站横杆时每 tick 挪几步的概率
STAND_SHIFT = (8.0, 26.0)
HANG_PULLUP_PROB = 1.0 / 700.0  # 吊着时每 tick 翻上去的概率
CLING_SHIFT_PROB = 1.0 / 220.0  # 爬竖杆时每 tick 挪一挪的概率
CLING_SHIFT = (10.0, 30.0)


class Dwell:
    """一处落脚点上的小动作；kind 为 T / S / H / V，吊着翻上去后变成 S。"""

    def __init__(self, fsm, bar, spot):
        self.fsm = fsm
        self.body = fsm.body
        self.gfx = fsm.gfx
        self.bar = bar
        self.kind = spot[0]
        b = self.body
        self.x = b.chunk1.x if self.kind == "S" else b.chunk0.x
        self.y = b.chunk0.y
        self.goal = None
        self.pull = None
        self.fell = False

    def step(self, cursor):
        self.gfx.look_at = self.fsm._ambient_look(cursor)
        getattr(self, "_" + self.kind)()

    def _shift(self, lo, hi, rng_span):
        r = self.fsm.rng
        d = r.uniform(*rng_span) * (1 if r.random() < 0.5 else -1)
        return min(max(self._pos() + d, lo), hi)

    def _pos(self):
        return self.y if self.kind == "V" else self.x

    def _T(self):
        if not tip_step(self.body, self.bar):
            self.fell = True

    def _S(self):
        b, bar, r = self.body, self.bar, self.fsm.rng
        if self.goal is None and r.random() < STAND_SHIFT_PROB:
            self.goal = self._shift(bar.lo, bar.hi, STAND_SHIFT)
        if self.goal is not None:
            if stand_toward(b, bar, self.goal):
                self.x, self.goal = b.chunk1.x, None
        else:
            stand_tick(b, bar, 0)

    def _H(self):
        b, bar, r = self.body, self.bar, self.fsm.rng
        if self.pull is not None:
            r = self.pull.step()
            if r is None:
                self.fell = True
            elif r:
                self.kind = "S"
                self.x = b.chunk1.x
                self.pull = None
            return
        hang_tick(b, bar, 0)
        if b.energy > 0.5 and r.random() < HANG_PULLUP_PROB:
            self.pull = PullUpMotion(b, bar, b.facing or 1)

    def _V(self):
        b, bar, r = self.body, self.bar, self.fsm.rng
        if self.goal is None and r.random() < CLING_SHIFT_PROB:
            self.goal = self._shift(bar.lo, bar.hi, CLING_SHIFT)
        if self.goal is not None and climb_toward(b, bar, self.goal):
            self.y, self.goal = b.chunk0.y, None
        elif self.goal is None:
            climb_tick(b, bar, 0)

    def done(self):
        """收尾。"""
