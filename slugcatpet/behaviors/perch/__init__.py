"""爬架：在杆上挑个落脚点走过去待着。"""

from __future__ import annotations

from ... import tuning
from ...brain.intent import smooth
from ...items.base import CLIMBABLE
from ...planning.climbmap import map_for
from ..base import Behavior
from .state import Perch


class PerchBehavior(Behavior):
    key = "perch"
    title = {"zh": "爬架", "en": "Climbing frame"}
    doc = "闲下来时去杆上随机一处待一阵，待够了换个地方或下来；合群的猫爱往别的猫旁边凑。"
    requires = (CLIMBABLE,)

    def mount(self, fsm):
        st = fsm.add_state(Perch)
        b = fsm.body

        def want():
            if fsm._zerog() or b.swimming:
                return 0.0
            cm = map_for(fsm.win)
            if not cm.bars or not cm.ready or not cm.floor_reach():
                return 0.0
            return (
                tuning.PERCH_UTIL
                * smooth(0.25, 0.6, b.energy)
                * (1.0 - 0.6 * smooth(0.5, 0.9, b.sleepiness))
                * fsm.ask("listless", 1.0)
            )

        def start():
            fsm._transition("Perch")
            return True

        st.want = want
        fsm.intents.add("perch", want, start)
        fsm.on_stun(st.brk)
