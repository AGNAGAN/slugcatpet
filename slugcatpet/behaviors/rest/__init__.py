"""休息。"""

from __future__ import annotations

from ... import tuning
from ...brain.state import EXHAUST
from ..base import Behavior
from .states import LieDown, Sleep, WakeSequence, too_cold_to_sleep


def enter_exhaustion(fsm):
    """体力告急：中断当前动作、收手，回地面准备趴下。"""
    fsm._break_active_controllers()
    fsm._clear_hands()
    fsm._transition("LieDown" if fsm.body.on_floor() else "Airborne")


class Rest(Behavior):
    key = "rest"
    title = {"zh": "休息", "en": "Rest"}
    doc = "体力告急强制趴下；困了睡觉、被叫醒；饱食满了冬眠。"
    essential = True

    def mount(self, fsm):
        for cls in (LieDown, Sleep, WakeSequence):
            fsm.add_state(cls)
        b = fsm.body

        def exhaust(cursor):
            if (
                not fsm._exhausted
                and not fsm._hibernating
                and not fsm.grab.active
                and not fsm.ask("cold_urgent")
                and not fsm._zerog()
                and b.energy < tuning.EXHAUST_ENTER_ENERGY
                and not fsm.blocked(EXHAUST)
            ):
                fsm._exhausted = True
                enter_exhaustion(fsm)

        def hibernate(cursor):
            if (
                not fsm._hibernating
                and not fsm.grab.active
                and not fsm._exhausted
                and not too_cold_to_sleep(fsm)
                and not fsm._zerog()
                and b.food >= b.food_max
                and fsm.state in ("IdleStand", "LieDown")
            ):
                fsm._hibernating = True
                if fsm.state == "IdleStand":
                    fsm._transition("LieDown")

        fsm.register_rule(exhaust, EXHAUST)
        fsm.register_rule(hibernate)
