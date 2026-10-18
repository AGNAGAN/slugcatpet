"""玩珍珠：闲着时去拿一颗落在地上的珍珠，拿着晃一会儿，再放下或随手抛开。"""

from __future__ import annotations

from ...abilities.base import Param
from ...brain.skills.throw import wieldable_items
from ...items.base import TOY
from ..base import Behavior, mood_candidate, mood_params
from .state import PearlPlay


class PearlPlayBehavior(Behavior):
    key = "pearl_play"
    title = {"zh": "玩珍珠", "en": "Play with pearls"}
    doc = (
        "闲着时去拿一颗落在地上的珍珠，拿着走走看看，最后放下或随手抛开；去吃东西、拿武器要腾手时会先放下它。"
    )
    requires = (TOY,)
    mood = "pearl_play"
    params = mood_params(
        1.00,
        0.60,
        0.30,
        0.90,
        0.0030,
        0.00050,
        hold_min=Param(150, 30, 2000, "拿着晃的最短帧数"),
        hold_max=Param(420, 30, 2000, "拿着晃的最长帧数"),
        stroll_prob=Param(0.012, 0.0, 1.0, "拿着时每 tick 想走几步的概率"),
        toss_prob=Param(0.5, 0.0, 1.0, "玩够了随手抛开（而不是放下）的概率"),
        toss_speed=Param(7.0, 1.0, 30.0, "抛出的初速（逻辑 px/tick）"),
    )

    def mount(self, fsm):
        st = fsm.add_state(PearlPlay)
        st.p = self.p
        b = fsm.body

        def gate(ctx):
            return (
                not ctx.submerged
                and b.free_hand() is not None
                and fsm.hands.held(None) is None
                and bool(wieldable_items(fsm, use=TOY))
            )

        mood_candidate(fsm, "pearl_play", self.p, gate)
        fsm.register_mood_entry("pearl_play", "PearlPlay")
