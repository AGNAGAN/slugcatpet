"""取暖。"""

from __future__ import annotations

from ... import tuning
from ...brain.intent import smooth
from ...brain.state import COLD
from ...items.base import WARM
from ..base import Behavior
from .goal import WarmGoal
from .state import SeekWarmth


class Warmth(Behavior):
    key = "warmth"
    title = {"zh": "取暖", "en": "Seek warmth"}
    doc = "冷了去暖源旁边取暖：冷度越高越想去，和别的事按比例挑；冷到阈值就强制去。"
    requires = (WARM,)

    def mount(self, fsm):
        wg = WarmGoal(fsm)
        fsm.add_state(SeekWarmth).warm = wg
        fsm.provide("cold_urgent", wg.urgent)

        def want_warm():
            if not wg.available():
                return 0.0
            return tuning.WARM_UTIL * smooth(0.03, tuning.COLD_SEEK_ENTER, fsm.body.cold)

        def start_warm():
            fsm._transition("SeekWarmth")
            return True

        fsm.intents.add("warm", want_warm, start_warm)

        def rule(cursor):
            if wg.urgent() and not fsm.grab.active and not fsm._zerog():
                fsm.interrupt(COLD, "SeekWarmth")

        fsm.register_rule(rule, COLD)
