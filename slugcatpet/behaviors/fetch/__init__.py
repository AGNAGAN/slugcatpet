"""用嘴吃：饿了取果、水里和失重时就近吃、顺手捡个果子留着。"""

from __future__ import annotations


from ...brain.hands import EAT_LATER
from ...brain.state import HUNGER
from ...items.base import EDIBLE
from ...abilities.base import MOUTH, Param
from ..base import Behavior
from .drift import DriftForage
from .fetcher import fetch_ready
from .state import FetchFruit, Forage

T_FETCH_CHECK = 8  # 取果闸重算间隔


def _ready(fsm):
    """够得着、没被占、不是刚放下的可吃物。"""
    me = fsm.win
    free = [f for f in fsm.items(EDIBLE) if fsm.social.free_for(me, f) and not fsm.hands.forbidden(f)]
    return fetch_ready(fsm.planner, free, fsm.traits)


class Fetch(Behavior):
    key = "fetch"
    title = {"zh": "取果", "en": "Fetch food"}
    doc = (
        "饿了去拿能吃的东西（果子、黏菌、蝙蝠）。真饿了拿到就吃；"
        "只是有点饿时可能先揣着到处走，过一阵或真饿了再吃。手里留着一个就不再去拿。"
        "游泳和失重时游 / 飘过去抓住就地吃。"
    )
    requires = (MOUTH, EDIBLE)
    params = {"carry_chance": Param(0.5, 0.0, 1.0, "有点饿时拿到先揣着、过会儿再吃的概率")}

    def mount(self, fsm):
        self.check = 0
        st = fsm.add_state(FetchFruit)
        st.carry_chance = self.p.carry_chance
        b = fsm.body
        drift = DriftForage(fsm, lambda: st.cooldown > 0)
        fsm.add_task("swim", drift.swim)
        fsm.add_task("zerog", drift.zerog)

        def rule(cursor):
            if st.cooldown > 0:
                st.cooldown -= 1
            self.check = (self.check + 1) % T_FETCH_CHECK
            if (
                self.check == 0
                and b.food < b.food_max
                and not fsm.grab.active
                and not fsm._exhausted
                and not fsm.ask("cold_urgent")
                and not fsm._zerog()
                and st.cooldown <= 0
                and not fsm.blocked(HUNGER)
                and (st.wants_saved() or (fsm.hands.held(EAT_LATER) is None and _ready(fsm)))
            ):
                fsm._break_active_controllers()
                fsm._act_or_wake("FetchFruit")

        def on_stun():
            if st.fetcher is not None:
                st.fetcher.release()
                st.fetcher = None

        fsm.register_rule(rule, HUNGER)
        fsm.on_stun(on_stun)


class ForageBehavior(Behavior):
    key = "forage"
    title = {"zh": "留个果子", "en": "Save a snack"}
    doc = "吃饱时附近还有能吃的，会顺手捡一个带着去睡，最多一个；醒来饿了先吃它。"
    requires = (MOUTH, EDIBLE)
    params = {"chance": Param(0.6, 0.0, 1.0, "吃饱时顺手捡一个的概率")}

    def mount(self, fsm):
        st = fsm.add_state(Forage)
        b = fsm.body
        p = self.p

        def after_meal():
            if (
                fsm.hands.held(EAT_LATER) is None
                and b.free_hand() is not None
                and not b.swimming
                and fsm.rng.random() < p.chance
                and _ready(fsm)
            ):
                return "Forage"
            return None

        def on_stun():
            if st.fetcher is not None:
                st.fetcher.release()
                st.fetcher = None

        fsm.provide("after_meal", after_meal)
        fsm.on_stun(on_stun)
