"""让路。"""

from __future__ import annotations

from ... import tuning
from ...brain.state import CROWD
from ..base import Behavior
from .blocking import blocks_path
from .state import MakeWay


class MakeWayBehavior(Behavior):
    key = "makeway"
    title = {"zh": "让路", "en": "Make way"}
    doc = "挡了别的猫的路时让开（跳开或趴下让对方跳过）；自己被挡太久就跳过去。"

    def mount(self, fsm):
        fsm.add_state(MakeWay)
        b = fsm.body
        me = fsm.win
        social = fsm.social
        cr = social.crowd(me)

        def scan(cursor):
            if cr.jump_cd > 0:
                cr.jump_cd -= 1
            if cr.yield_cd > 0:
                cr.yield_cd -= 1
            myx = b.chunk1.x
            shover = None
            blocker = None
            for o in social.others(me):
                ob = o.body
                if not ob.on_floor():  # 悬空猫不参与挡路判定
                    continue
                if shover is None and blocks_path(
                    myx, ob.chunk1.x, ob.walk_target_x, tuning.SHOVE_CONTACT_DIST
                ):
                    shover = o
                if (
                    blocker is None
                    and social.state_of(o) != "MakeWay"
                    and blocks_path(ob.chunk1.x, myx, b.walk_target_x, tuning.SHOVE_CONTACT_DIST)
                ):
                    blocker = o
            if shover is not None:
                cr.shoved += 1
                cr.yield_to = shover
            else:
                cr.shoved = 0
                cr.yield_to = None
            cr.blocked = cr.blocked + 1 if blocker is not None else 0

            if (
                cr.shoved >= tuning.SHOVE_YIELD_TICKS
                and cr.yield_cd <= 0
                and not fsm.blocked(CROWD)
                and not fsm.grab.active
                and not fsm._zerog()
                and not b.swimming
                and not fsm._exhausted
                and not fsm.ask("cold_urgent")
                and b.on_floor()
            ):
                fsm._transition("MakeWay")
            elif (
                cr.blocked >= tuning.BLOCKED_JUMP_TICKS
                and cr.jump_cd <= 0
                and b.on_floor()
                and not fsm.grab.active
                and not fsm._zerog()
                and not b.swimming
            ):
                b.request_jump("stand", hold_ticks=tuning.JUMP_OVER_HOLD)
                cr.blocked = 0
                cr.jump_cd = tuning.JUMP_OVER_COOLDOWN

        fsm.register_rule(scan, CROWD)
