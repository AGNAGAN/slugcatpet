"""累倒喘气。"""

from __future__ import annotations

from ...brain.state import T_ACTIVITY, IDLE, State
from ..base import Behavior


class CatchBreath(State):
    name = "CatchBreath"
    tier = T_ACTIVITY
    energy = IDLE

    def enter(self):
        b = self.fsm.body
        b.stop_walk()
        b.set_posture(True)

    def tick(self, cursor, disturbed):
        if not self.fsm.body.exhausted:
            self.fsm.settle()


class CatchBreathBehavior(Behavior):
    key = "catch_breath"
    title = {"zh": "累倒喘气", "en": "Catch breath"}
    doc = "累倒后停在原地喘气，缓过来再做别的。"
    requires = ("heavy",)

    def mount(self, fsm):
        fsm.add_state(CatchBreath)
        b = fsm.body

        def winded(cursor):
            if b.exhausted and fsm.state == "IdleStand" and b.on_floor():
                fsm._transition("CatchBreath")

        fsm.register_rule(winded)
