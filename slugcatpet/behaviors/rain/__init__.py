"""下雨：大雨推动、砸晕露天的猫；雨将变大时躲到窗口下。"""

from __future__ import annotations

from ...brain.state import RAIN, STUN
from ...world.rain import push_force
from ..base import Behavior
from .state import SeekShelter, exposed, shelter_x

T_CHECK = 8  # 每隔几 tick 判断一次要不要躲雨
BUFFET_TICKS = 80  # 被雨推后这段时间内摔落不致死、不记仇


class RainBehavior(Behavior):
    key = "rain"
    title = {"zh": "躲雨", "en": "Shelter from rain"}
    doc = "大雨时露天的猫会被推动、砸晕，被光标拎着和定身时不受影响；雨将变大时走到最近的窗口下躲雨。"

    def mount(self, fsm):
        st = fsm.add_state(SeekShelter)
        self.check = 0

        def push():
            rain = fsm.win.rain
            if not rain.active or fsm.grab.active or fsm.win.held is not None:
                return
            force = push_force(rain.intensity)
            b = fsm.body
            if force <= 0.0 or (fsm.blocked(STUN) and not b.dead):
                return
            ticks = None
            for c in (b.chunk0, b.chunk1):
                if not c.pinned:
                    n = rain.kick(c, force, c.on_floor, 2)
                    if n is not None:
                        ticks = max(ticks or 0, n)
            if ticks is None:
                return
            pet = fsm.win
            pet.buffeted_until = pet.world_tick + BUFFET_TICKS
            if ticks and not b.dead:
                if fsm.state == "Stunned":
                    b.stun = max(b.stun, ticks)
                else:
                    fsm.apply_stun(ticks, blame=False)

        def rule(cursor):
            if st.cooldown > 0:
                st.cooldown -= 1
            if not fsm.win.rain.dangerous() or fsm.grab.active or fsm._zerog():
                return
            self.check = (self.check + 1) % T_CHECK
            if self.check == 0 and st.cooldown <= 0 and exposed(fsm) and shelter_x(fsm) is not None:
                fsm.interrupt(RAIN, "SeekShelter")

        fsm.register_ticker(push)
        fsm.register_rule(rule, RAIN)
