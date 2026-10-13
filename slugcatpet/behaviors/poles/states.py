"""内置行为状态：竖杆攀爬 / 横杆玩耍。"""
from __future__ import annotations

from ... import tuning
from ...brain.state import EN_DRAIN_LIGHT, T_ACTIVITY, VIGOROUS, State
from ...items.base import CLIMBABLE


def pole_free(fsm, p):
    """竖杆没被别的猫占着，或占用者已经待太久（可以把它顶下去）。"""
    return fsm.social.free_for(fsm.win, p, patience=tuning.POLE_SHARE_PATIENCE, steal=None)


class PoleClimb(State):
    name = "PoleClimb"
    climber = None
    mood = "pole_climb"
    tier = T_ACTIVITY
    energy = VIGOROUS

    def energy_delta(self, drain_fac):
        pc = self.climber
        if pc is not None and pc.phase == "tip":
            return -EN_DRAIN_LIGHT * drain_fac          # 站杆顶不算剧烈
        return super().energy_delta(drain_fac)

    def enter(self):
        fsm = self.fsm
        from ...brain.skills.pole_climb import PoleClimber
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        pole = self._pick_climbable_pole()
        self.climber = PoleClimber(fsm.win, pole, fsm.rng) if pole is not None else None

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if self.climber is None or self.climber.pole not in fsm.items(CLIMBABLE):
            on_floor = fsm.body.on_floor()
            self._pole_release()
            fsm._transition("IdleStand" if on_floor else "Airborne")
            return
        want_dismount = fsm.body.energy <= tuning.TIP_TIRED_ENERGY
        done = self.climber.update(want_dismount)
        if done:
            giveup = self.climber.giveup
            on_floor = fsm.body.on_floor()
            self._pole_release()
            fsm._transition("IdleStand" if (giveup or on_floor) else "Airborne")

    def brk(self):
        self._pole_release()

    def kill_break(self):
        self._pole_release()

    def _pick_climbable_pole(self):
        fsm = self.fsm
        best = None
        hx = fsm.body.chunk1.x
        for p in fsm.items(CLIMBABLE):
            if p.kind != "vertical" or not pole_free(fsm, p):
                continue
            if best is None or abs(p.x - hx) < abs(best.x - hx):
                best = p
        if best is not None:
            fsm.social.claim(fsm.win, "pole", best, "PoleClimb")
        return best

    def _pole_release(self):
        fsm = self.fsm
        if self.climber is not None:
            self.climber.release()
            self.climber = None
        fsm.body.chunk0.pinned = False
        fsm.body.chunk1.pinned = False
        fsm.body.on_pole = False
        fsm.body.animation = None
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None


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
