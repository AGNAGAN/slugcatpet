"""定身：用户让猫停在原地摆姿势。"""

from __future__ import annotations

from ...brain.state import HOLD, T_BODY
from ..base import Behavior
from .state import AROUND, CURSOR, LIE, LOCK, SLEEP, STAND, Hold, HoldSpec, pole_spot

__all__ = ["HoldBehavior", "HoldSpec", "STAND", "LIE", "SLEEP", "CURSOR", "AROUND", "LOCK"]


class HoldBehavior(Behavior):
    key = "hold"
    title = {"zh": "定身", "en": "Hold still"}
    doc = "用户让它定身时停在原地保持姿势，只留看向、眨眼、呼吸和尾巴；需求和寒冷不变。被晕、被拖、游泳之后在落点接着定身。"
    essential = True

    def mount(self, fsm):
        st = fsm.add_state(Hold)
        pet, b = fsm.win, fsm.body

        def rule(cursor):
            if pet.held is None or fsm.state == "Hold":
                return
            if b.dead or fsm.state == "Dead":
                pet.held = None
                return
            if b.swimming or fsm._cur().tier >= T_BODY:
                return
            st.spot = pole_spot(fsm)
            if not fsm.interrupt(HOLD, "Hold"):
                st.spot = None

        fsm.register_rule(rule, HOLD)
