"""发呆；闲下来时由这里抽下一件事。"""
from __future__ import annotations

from ... import tuning
from ...brain.desire import Candidate, _lerp
from ..base import Behavior
from .state import IdleStand


class Idle(Behavior):
    key = "idle"
    title = {"zh": "发呆", "en": "Idle"}
    doc = "默认状态：站着发呆、东张西望、踱步、对视；无重力时漂浮。心情抽签也在这里发起。"
    essential = True

    def mount(self, fsm):
        fsm.add_state(IdleStand)
        fsm.mood.add(Candidate(
            "idle", base=tuning.IDLE_BASE, start=0.0, quit=0.0,
            decay=0.0, recover=1.0,
            gate=lambda ctx: True,
            energy_factor=lambda e: _lerp(e, tuning.IDLE_SF_KNEE, 1.0,
                                          tuning.IDLE_SF_TIRED, tuning.IDLE_SF_FRESH),
            temper_factor=lambda t: 1.0,
            one_shot=True, init=1.0))
