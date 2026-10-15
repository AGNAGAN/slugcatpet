"""休息。"""

from __future__ import annotations

from ... import tuning
from ...brain.intent import smooth
from ...brain.state import EXHAUST, SLEEPY
from ..base import Behavior
from .states import (
    EXHAUST as WHY_EXHAUST,
    HIBERNATE,
    NAP,
    REST_A_BIT,
    SLEEPS,
    LieDown,
    Sleep,
    WakeSequence,
    lie_down,
    lying_for,
    too_cold_to_sleep,
)


def sleep_now(fsm):
    """困了睡：食物够就冬眠，不够就打盹。"""
    b = fsm.body
    return lie_down(fsm, HIBERNATE if b.food >= b.food_hibernate else NAP)


class Rest(Behavior):
    key = "rest"
    title = {"zh": "休息", "en": "Rest"}
    doc = (
        "累了歇一会，体力告急强制趴下。困了睡：食物够就冬眠（扣食物、回满体力），不够就打个盹；"
        "困到撑不住就地睡。"
    )
    essential = True

    def mount(self, fsm):
        for cls in (LieDown, Sleep, WakeSequence):
            fsm.add_state(cls)
        b = fsm.body

        def calm():
            return not fsm.grab.active and not fsm._zerog() and not b.swimming

        def exhausted():
            return b.energy < tuning.EXHAUST_ENTER_ENERGY or lying_for(fsm) == WHY_EXHAUST

        def exhaust(cursor):
            if (
                b.energy < tuning.EXHAUST_ENTER_ENERGY
                and lying_for(fsm) is None
                and fsm.state != "Airborne"
                and calm()
                and not fsm.ask("cold_urgent")
                and not fsm.blocked(EXHAUST)
            ):
                fsm._break_active_controllers()
                fsm._clear_hands()
                if b.on_floor():
                    lie_down(fsm, WHY_EXHAUST)
                else:
                    fsm.settle()
                    if fsm.state == "Airborne":
                        fsm._states["Airborne"].land_then = lambda: lie_down(fsm, WHY_EXHAUST)  # 落定后再趴下

        def sleepy(cursor):
            if (
                b.sleepiness < 1.0
                or lying_for(fsm) in SLEEPS
                or not calm()
                or not b.on_floor()
                or too_cold_to_sleep(fsm)
            ):
                return
            if lying_for(fsm) is not None:
                sleep_now(fsm)  # 趴着歇的时候困到撑不住，就接着睡
            elif not fsm.blocked(SLEEPY):
                fsm._break_active_controllers()
                sleep_now(fsm)

        def want_sleep():
            if too_cold_to_sleep(fsm):
                return 0.0
            return smooth(tuning.SLEEP_WANT_LO, tuning.SLEEP_WANT_HI, b.sleepiness)

        def want_rest():
            return smooth(tuning.REST_WANT_HI, tuning.REST_WANT_LO, b.energy)

        fsm.provide("exhausted", exhausted)
        fsm.register_rule(exhaust, EXHAUST)
        fsm.register_rule(sleepy, SLEEPY)
        fsm.intents.add("sleep", want_sleep, lambda: sleep_now(fsm))
        fsm.intents.add("rest", want_rest, lambda: lie_down(fsm, REST_A_BIT))
