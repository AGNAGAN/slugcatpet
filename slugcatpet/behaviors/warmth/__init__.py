"""取暖。"""
from __future__ import annotations

from ... import tuning
from ...brain.desire import Candidate
from ...brain.state import COLD
from ...items.base import WARM
from ..base import Behavior
from .goal import WarmGoal
from .state import SeekWarmth


class Warmth(Behavior):
    key = "warmth"
    title = {"zh": "取暖", "en": "Seek warmth"}
    doc = "冷了去暖源旁边取暖，冷度越高越想去；冷到阈值就强制去。"
    requires = (WARM,)

    def mount(self, fsm):
        wg = WarmGoal(fsm)
        fsm.add_state(SeekWarmth).warm = wg
        fsm.provide("cold_urgent", wg.urgent)

        def gate(ctx):
            warm = wg.available()
            return warm and ctx.cold > 0.05

        fsm.mood.add(Candidate(
            "seek_warmth", base=tuning.COLD_SEEK_BASE, start=0.1, quit=0.0,
            decay=0.0, recover=1.0,
            gate=gate,
            energy_factor=lambda e: 1.0,
            temper_factor=lambda t: 1.0,
            cold_factor=lambda c: c,
            one_shot=True))
        fsm.register_mood_entry("seek_warmth", "SeekWarmth")

        def rule(cursor):
            if wg.urgent() and not fsm.grab.active and not fsm._zerog():
                fsm.interrupt(COLD, "SeekWarmth")

        fsm.register_rule(rule, COLD)
