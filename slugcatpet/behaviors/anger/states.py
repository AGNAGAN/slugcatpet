"""生气相关状态：闲逛、盯着光标、扔武器、揣石头。"""

from __future__ import annotations

from ...brain.state import T_ACTIVITY, State, LIGHT, IDLE
from ...brain.fsm import T_POSTTHROW_STAND
from ...brain.hands import WEAPON
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

    def hands_needed(self):
        return "any" if self.fsm.hands.held(WEAPON) is not None else "one"

    def enter(self):
        fsm = self.fsm
        from .thrower import WeaponThrower

        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        self.thrower = WeaponThrower(fsm.win, fsm.rng, fsm)
        stone = fsm.hands.held(WEAPON)
        if stone is not None:
            self.thrower.start_with(stone)

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
        _release_thrower(self.fsm, self.thrower)
        self.thrower = None


class ArmStone(State):
    """好感低时捡块石头揣着。"""

    name = "ArmStone"
    mood = "arm_stone"
    thrower = None
    tier = T_ACTIVITY
    energy = LIGHT
    hands = "one"

    def enter(self):
        fsm = self.fsm
        from .thrower import WeaponThrower

        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        self.thrower = WeaponThrower(fsm.win, fsm.rng, fsm, keep=True)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        status = "idle" if self.thrower is None else self.thrower.update(True)
        if status == "running":
            return
        _release_thrower(fsm, self.thrower)
        self.thrower = None
        fsm._transition("IdleStand")

    def brk(self):
        _release_thrower(self.fsm, self.thrower)
        self.thrower = None

    def kill_break(self):
        self.brk()


def _release_thrower(fsm, thrower):
    """收尾：没扔出去的武器留在手里。"""
    if thrower is not None:
        fsm.hands.adopt(thrower.target, WEAPON)
    fsm.body.stop_walk()
    fsm.body.arm_aim["l"] = None
    fsm.body.arm_aim["r"] = None
    fsm.gfx.hand_aim["l"] = None
    fsm.gfx.hand_aim["r"] = None
