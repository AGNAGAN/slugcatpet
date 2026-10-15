"""上横杆的状态。"""

from __future__ import annotations

from ...brain.state import T_ACTIVITY, VIGOROUS, State
from ...items.base import CLIMBABLE


class HPole(State):
    name = "HPole"
    ctl = None
    mood = "hpole"
    tier = T_ACTIVITY
    energy = VIGOROUS

    def enter(self):
        fsm = self.fsm
        from ...brain.skills.hpole import HPoleController

        pole = fsm.social.held(fsm.win, "hpole")
        fsm.social.release(fsm.win, "hpole")
        self.ctl = HPoleController(fsm.win, pole, fsm.rng) if pole is not None else None

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if self.ctl is None or self.ctl.pole not in fsm.items(CLIMBABLE):
            self._hpole_release()
            fsm.settle()
            return
        if self.ctl.phase == "stand" and "Perch" in fsm._states:
            self.ctl = None  # 站稳了，不松手交给爬架
            fsm._transition("Perch")
            return
        done = self.ctl.update()
        if done:
            self._hpole_release()
            fsm.settle()

    def brk(self):
        self._hpole_release()

    def kill_break(self):
        self._hpole_release()

    def _hpole_release(self):
        fsm = self.fsm
        if self.ctl is not None:
            self.ctl.release()
            self.ctl = None
        fsm.body.chunk0.pinned = False
        fsm.body.chunk1.pinned = False
        fsm.body.on_pole = False
        fsm.body.animation = None
        fsm.body.suspended = False
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
