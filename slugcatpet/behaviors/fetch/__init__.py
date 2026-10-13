"""取果。"""
from __future__ import annotations


from ...brain.state import FETCH
from ...items.base import EDIBLE
from ..base import Behavior
from .fetcher import fetch_ready
from .state import FetchFruit

T_FETCH_CHECK = 8   # 取果闸重算间隔


class Fetch(Behavior):
    key = "fetch"
    title = {"zh": "取果", "en": "Fetch food"}
    doc = "饿了去拿能吃的东西（果子、黏菌、蝙蝠），叼回来吃。"
    requires = (EDIBLE,)

    def mount(self, fsm):
        self.check = 0
        st = fsm.add_state(FetchFruit)
        b = fsm.body

        def rule(cursor):
            if st.cooldown > 0:
                st.cooldown -= 1
            self.check = (self.check + 1) % T_FETCH_CHECK
            if (self.check == 0
                    and b.food < b.food_max
                    and not fsm.grab.active and not fsm._exhausted
                    and not fsm.ask("cold_urgent") and not fsm._zerog()
                    and st.cooldown <= 0
                    and not fsm.blocked(FETCH)):
                me = fsm.win
                free = [f for f in fsm.items(EDIBLE) if fsm.social.free_for(me, f)]
                cands = fetch_ready(fsm.planner, free, fsm.traits)
                if cands:
                    fsm._break_active_controllers()
                    fsm._act_or_wake("FetchFruit")

        def on_stun():
            if st.fetcher is not None:
                st.fetcher.release()
                st.fetcher = None

        fsm.register_rule(rule, FETCH)
        fsm.provide("fetch_cooling", lambda: st.cooldown > 0)
        fsm.on_stun(on_stun)
