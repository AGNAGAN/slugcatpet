"""用嘴吃：饿了取果、水里和失重时就近吃、顺手捡个果子留着。"""

from __future__ import annotations


from ... import tuning
from ...brain.hands import EAT_LATER
from ...brain.needs import bedtime_hunger, hunger
from ...brain.state import HUNGER
from ...items.base import EDIBLE
from ...abilities.base import MOUTH, Param
from ..base import Behavior
from .drift import DriftForage
from .fetcher import fetch_ready
from .state import FetchFruit, Forage

T_FETCH_CHECK = 8  # 每隔几 tick 判断一次要不要取果


def _skewered(fsm):
    """手里武器上串着的、自己能吃的东西：(东西, 空手)；没有返回 None。"""
    b = fsm.body
    side = b.free_hand()
    if side is None:
        return None
    for w in b.held_items():
        for o, _ in getattr(w, "impaled", ()):
            if o.state == "free" and o.held_by_hand is None and fsm.win.can_eat(o):
                return o, side
    return None


def _ready(fsm):
    """够得着、没被占、不是刚放下的可吃物。"""
    me = fsm.win
    free = [
        f
        for f in fsm.items(EDIBLE)
        if fsm.social.free_for(me, f) and not fsm.hands.forbidden(f) and not me.rain.keeps_out(f.x, f.y)
    ]
    return fetch_ready(fsm.planner, free, fsm.traits)


class Fetch(Behavior):
    key = "fetch"
    title = {"zh": "取果", "en": "Fetch food"}
    doc = (
        "饿了去拿能吃的东西（果子、黏菌、蝙蝠、蛋虫蛋）。真饿了拿到就吃；"
        "只是有点饿时可能先揣着到处走，过一阵或真饿了再吃。手里留着一个就不再去拿。"
        "游泳和失重时游 / 飘过去抓住就地吃。"
        "会啃肉的猫（猎手、工匠、大胃王）也啃蛋虫尸体：拿起来伏下身子啃，啃完扔开。"
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
            if self.check == 0 and b.food < b.food_max and fsm.hands.held(EAT_LATER) is None:
                sk = _skewered(fsm)
                if sk is not None and not fsm.grab.active and not fsm.blocked(HUNGER):
                    b.grab(sk[0], sk[1])  # 从手里的武器上取下一只留着吃
                    fsm.hands.adopt(sk[0], EAT_LATER)
            if (
                self.check == 0
                and b.food < b.food_max
                and free()
                and not fsm.blocked(HUNGER)
                and (
                    st.wants_saved()
                    or (
                        fsm.hands.held(EAT_LATER) is None
                        and bedtime_hunger(b) >= tuning.EAT_URGENT
                        and _ready(fsm)
                    )
                )
            ):
                if not b.on_pole:
                    fsm._break_active_controllers()  # 在杆上取果就地开始，不先松杆
                fsm._act_or_wake("FetchFruit")

        def free():
            return (
                not fsm.grab.active
                and not fsm.ask("exhausted")
                and not fsm.ask("cold_urgent")
                and not fsm._zerog()
                and st.cooldown <= 0
            )

        def want_eat():
            if b.food >= b.food_max or not free() or fsm.hands.held(EAT_LATER) is not None:
                return 0.0
            ready = _ready(fsm)
            if not ready:
                return 0.0
            value = max(fsm.traits.nourishment(f) for f in ready) / 4.0
            return hunger(b, value)

        def start_eat():
            fsm._transition("FetchFruit")
            return True

        def on_stun():
            if st.fetcher is not None:
                st.fetcher.release()
                st.fetcher = None

        fsm.register_rule(rule, HUNGER)
        fsm.intents.add("eat", want_eat, start_eat)
        fsm.provide("food_ready", lambda: bool(_ready(fsm)))
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
