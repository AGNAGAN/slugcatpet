"""内置行为状态：被砸后生气 / 扔石头。"""
from __future__ import annotations

from ...brain.state import T_ACTIVITY, State, LIGHT, IDLE
from ...brain.fsm import T_POSTTHROW_STAND
from ...brain.skills import motor


class PostThrowWander(State):
    name = "PostThrowWander"
    energy = LIGHT

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(True)
        motor.wander(fsm)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        motor.point_if_near(fsm, cursor)
        if not fsm.body.is_moving():
            motor.wander(fsm)
        if fsm.anger <= T_POSTTHROW_STAND:
            fsm._clear_hands()
            fsm._transition("PostThrowStand")


class PostThrowStand(State):
    name = "PostThrowStand"
    energy = IDLE

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(True)
        b.stop_walk()

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        fsm.gfx.look_at = cursor
        motor.point_if_near(fsm, cursor)
        if fsm.anger <= 0:
            fsm._clear_hands()
            fsm._transition("IdleStand")


class AngryStone(State):
    name = "AngryStone"
    thrower = None
    tier = T_ACTIVITY
    energy = LIGHT

    def enter(self):
        fsm = self.fsm
        from .thrower import StoneThrower
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        self.thrower = StoneThrower(fsm.win, fsm.rng, fsm)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if self.thrower is None:
            fsm._transition("IdleStand")
            return
        status = self.thrower.update(fsm.anger > 0)
        if status in ("thrown", "idle"):
            self._angrystone_release()
            fsm._transition("IdleStand")
        elif status == "revert_wander":
            self._angrystone_release()
            if fsm.anger <= 0:
                fsm._transition("IdleStand")
            elif fsm.anger <= T_POSTTHROW_STAND:
                fsm._transition("PostThrowStand")
            else:
                fsm._transition("PostThrowWander")

    def brk(self):
        self._angrystone_release()

    def kill_break(self):
        self._angrystone_release()

    def _angrystone_release(self):
        fsm = self.fsm
        if fsm.body.carried_stone is not None:
            fsm.body.release_stone(to_free=True)
        fsm.body.stop_walk()
        self.thrower = None
        fsm.body.arm_aim["l"] = None
        fsm.body.arm_aim["r"] = None
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
