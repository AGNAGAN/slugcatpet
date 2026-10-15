"""引擎自带的状态：被拖 / 空中 / 砸晕 / 死亡。"""

from __future__ import annotations

import math

from .. import tuning
from .state import T_BODY, T_FORCED, T_LOCKED, State
from .fsm import ANGER_TOTAL


class Dragged(State):
    name = "Dragged"
    tier = T_FORCED

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(True)
        b.stop_walk()

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        fsm._clear_hands()
        ch = fsm.grab.chunk
        if ch is not None and math.hypot(ch.vx, ch.vy) > tuning.TEMPER_SWING_SPEED:
            fsm.body.temper_shift(tuning.TEMPER_SWING_RATE)
        if fsm.drag_takeover is not None and fsm.drag_takeover(fsm.grab.frames):
            return
        if not fsm.grab.active:
            fsm._transition("Airborne")


class Airborne(State):
    name = "Airborne"

    def __init__(self, fsm):
        super().__init__(fsm)
        self._settle = 0
        self.land_then = None  # 落定后做的事 fn()；None 就站着

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(True)
        b.stop_walk()
        self._settle = 0
        self.land_then = None

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        sp = math.hypot(b.chunk1.vx, b.chunk1.vy) + math.hypot(b.chunk0.vx, b.chunk0.vy)
        if b.on_floor() and sp < 1.2 and b.chunk0.y < b.chunk1.y - 2:
            self._settle += 1
        else:
            self._settle = 0
        if self._settle >= 4:
            then, self.land_then = self.land_then, None
            if then is None:
                fsm._transition("IdleStand")
            else:
                then()


class Stunned(State):
    name = "Stunned"
    tier = T_BODY

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(False)
        b.stop_walk()
        fsm.gfx.stunned = True

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        fsm._clear_hands()
        if fsm.body.stun <= 0:
            fsm.gfx.stunned = False
            fsm.body.set_posture(True)
            if fsm.grab.active:
                fsm._transition("Dragged")
                return
            if not fsm.stun_blame:
                fsm.settle()
                return
            if fsm.stun_takeover is not None and fsm.stun_takeover():
                return
            fsm.anger = ANGER_TOTAL
            fsm._transition("PostThrowWander")


class Dead(State):
    name = "Dead"
    tier = T_LOCKED

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.die()
        fsm.gfx.dead = True

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        fsm._clear_hands()
        if fsm._revive_timer > 0:
            fsm._revive_timer -= 1
            if fsm._revive_timer <= 0:
                if fsm._reincarnate:
                    fsm._reincarnate = False
                    fsm.win._reincarnate_pending = True
                    return
                fsm.body.revive()
                fsm.gfx.dead = False
                fsm.gfx.sleeping = False
                fsm.body.sleeping = False
                fsm.gfx.sleep_curl = 0.0
                fsm.body.set_posture(False)
                fsm._transition("WakeSequence")


CORE_STATES = (Dragged, Airborne, Dead, Stunned)
