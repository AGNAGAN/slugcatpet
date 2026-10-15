"""上横杆：吊上去翻上来，再交给爬架。"""

from __future__ import annotations

from ...items.base import CLIMBABLE
from ..base import Behavior
from .states import HPole


class Poles(Behavior):
    key = "poles"
    title = {"zh": "上横杆", "en": "Get onto bars"}
    doc = "吊上横杆、翻上来站好（舌头猫甩舌头、溪流后空翻抓杆都走这里），站稳后交给爬架行为。"
    requires = (CLIMBABLE,)

    def mount(self, fsm):
        hang = fsm.add_state(HPole)

        def on_stun():
            if hang.ctl is not None:
                hang.ctl.release()
                hang.ctl = None

        fsm.on_stun(on_stun)
