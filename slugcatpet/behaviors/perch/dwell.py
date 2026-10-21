"""在落脚点待着：原地扶稳，吊着时偶尔翻上去站着。"""

from __future__ import annotations

from ...planning.climbmoves import PullUpMotion, climb_tick, hang_tick, stand_tick, tip_step

HANG_PULLUP_PROB = 1.0 / 700.0  # 吊着时每 tick 翻上去的概率


class Dwell:
    """一处落脚点上待着；kind 为 T / S / H / V，吊着翻上去后变成 S。"""

    def __init__(self, fsm, bar, spot):
        self.fsm = fsm
        self.body = fsm.body
        self.gfx = fsm.gfx
        self.bar = bar
        self.kind = spot[0]
        self.pull = None
        self.fell = False

    def step(self, cursor):
        self.gfx.look_at = self.fsm._ambient_look(cursor)
        getattr(self, "_" + self.kind)()

    def _T(self):
        if not tip_step(self.body, self.bar):
            self.fell = True

    def _S(self):
        stand_tick(self.body, self.bar, 0)

    def _H(self):
        b, bar = self.body, self.bar
        if self.pull is not None:
            r = self.pull.step()
            if r is None:
                self.fell = True
            elif r:
                self.kind = "S"
                self.pull = None
            return
        hang_tick(b, bar, 0)
        if b.energy > 0.5 and self.fsm.rng.random() < HANG_PULLUP_PROB:
            self.pull = PullUpMotion(b, bar, b.facing or 1)

    def _V(self):
        climb_tick(self.body, self.bar, 0)

    def done(self):
        """收尾。"""
