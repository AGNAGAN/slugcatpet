"""内置行为状态：趴下 / 睡眠 / 起身。"""
from __future__ import annotations

from ... import tuning
from ...brain.skills import motor
from ...brain.state import T_REST, T_WARM, State, LIGHT, REST


def too_cold_to_sleep(fsm):
    return fsm.body.cold >= tuning.COLD_NOSLEEP


T_POINT_WAKE = 160               # 起身后指光标最长时长（tick）
WAKE_STABILIZE_TICKS = 30        # 落地稳定多久才算醒透


class LieDown(State):
    name = "LieDown"
    tier = T_REST
    energy = REST

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(False)
        b.stop_walk()

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if fsm._hibernating:
            if too_cold_to_sleep(fsm):
                fsm._hibernating = False
                fsm._transition("WakeSequence")
                return
            if fsm.timer >= tuning.LIE_SETTLE_TICKS:
                fsm._transition("Sleep")
            return
        if fsm.body.energy >= tuning.EXHAUST_EXIT_ENERGY:
            fsm._exhausted = False
            fsm._transition("WakeSequence")


class Sleep(State):
    name = "Sleep"
    tier = T_REST
    energy = REST

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(False)
        b.stop_walk()

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        fsm.gfx.sleeping = True
        fsm.body.sleeping = True
        if too_cold_to_sleep(fsm):
            fsm._hibernating = False
            fsm._transition("WakeSequence")
            return
        if fsm.timer >= tuning.HIBERNATE_TICKS:
            fsm.body.karma_gain()
            fsm.body.food_eat(-fsm.body.food_hibernate)
            fsm.body.energy = 1.0
            fsm._hibernating = False
            fsm._transition("WakeSequence")


class WakeSequence(State):
    name = "WakeSequence"
    tier = T_WARM
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self._wake_stable = 0
        self.protest_left = 0

    def enter(self):
        fsm = self.fsm
        fsm.gfx.sleeping = False
        fsm.body.sleeping = False
        fsm.phase = 0
        self._wake_stable = 0
        fsm._wake_then = None

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        if fsm.phase == 0:
            fsm.gfx.sleeping = False
            b.sleeping = False
            b.set_posture(False)
            if fsm.gfx.sleep_curl <= 0.05:
                fsm.phase = 1
                b.request_jump("wake")
                b.set_posture(True)
        elif fsm.phase == 1:
            self._wake_stable = self._wake_stable + 1 if b.on_floor() else 0
            if fsm._wake_then is not None:
                if self._wake_stable > WAKE_STABILIZE_TICKS:
                    target = fsm._wake_then
                    fsm._wake_then = None
                    fsm._clear_hands()
                    fsm._transition(target)
                return
            if b.on_floor() and fsm.timer > 5:
                if fsm.rng.random() < 0.5:
                    fsm.phase = 2
                    fsm.timer = 0
                    fsm.point_side = 0
                else:
                    fsm.phase = 3
                    self.protest_left = fsm.rng.randint(1, 3)
                    fsm.timer = 0
        elif fsm.phase == 2:
            fsm.gfx.look_at = cursor
            motor.point_at_cursor(fsm, cursor, enforce_side=True)
            if fsm.timer >= T_POINT_WAKE or fsm._point_stopped:
                fsm._clear_hands()
                fsm._transition("IdleStand")
        elif fsm.phase == 3:
            if b.on_floor():
                if self.protest_left > 0 and fsm.timer > 16:
                    b.request_jump("protest")
                    self.protest_left -= 1
                    fsm.timer = 0
                elif self.protest_left <= 0 and fsm.timer > 16:
                    fsm._transition("IdleStand")
