"""取暖状态：走到暖源旁待着。"""

from __future__ import annotations

from ... import tuning
from ...planning import GIVEUP, HOLDING, MODE_STAY, PlanExecutor
from ...planning.climbmoves import release
from ...brain.state import T_WARM, State, LIGHT
from .goal import warm_source


class SeekWarmth(State):
    name = "SeekWarmth"
    tier = T_WARM
    energy = LIGHT
    warm = None  # WarmGoal（挂载时设）

    def __init__(self, fsm):
        super().__init__(fsm)
        self._warm_exec = None

    def enter(self):
        fsm = self.fsm
        fsm.gfx.sleeping = False
        fsm.body.sleeping = False
        fsm.gfx.sleep_curl = 0.0
        fsm.body.set_posture(True)
        fsm._clear_hands()
        fsm.climb = None
        self._warm_exec = None
        g = self.warm.goal()
        if g is None:
            return
        if not fsm.planner.stay_candidates(g):
            fsm.planner.on_giveup(g)
            return
        self._warm_exec = PlanExecutor(fsm.win, fsm.planner, g, mode=MODE_STAY)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        src = warm_source(fsm)
        if src is None or self._warm_exec is None:
            self._seekwarmth_break()
            fsm.settle()
            return
        fsm.gfx.look_at = src.look_point
        status = self._warm_exec.update()
        if status == GIVEUP:
            self._seekwarmth_break()
            fsm.settle()
            return
        if status == HOLDING:
            storm = bool(getattr(fsm.win, "blizzard_on", False))
            if b.cold <= tuning.COLD_SEEK_EXIT and not storm:
                self._seekwarmth_break()
                fsm.settle()

    def brk(self):
        self._seekwarmth_break()
        self._let_go()

    def kill_break(self):
        self._seekwarmth_break()
        self._let_go()

    def _let_go(self):
        """被打断：接下来的状态不在杆上做，还抓着杆就松手。"""
        b = self.fsm.body
        if b.on_pole:
            release(b)

    def _seekwarmth_break(self):
        fsm = self.fsm
        if self._warm_exec is not None:
            self._warm_exec.cancel()
            self._warm_exec = None
        fsm.release_organs()
        fsm.body.stop_walk()
        fsm.climb = None
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
