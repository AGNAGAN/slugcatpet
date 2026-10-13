"""取暖目标：场上提供 warm 用法的暖源。"""

from __future__ import annotations

from ... import tuning
from ...items.base import WARM
from ...planning import obj_goal


def warm_source(fsm):
    for src in fsm.items(WARM):
        return src
    return None


class WarmGoal:
    def __init__(self, fsm):
        self.fsm = fsm
        self._goal = None

    def goal(self):
        fsm = self.fsm
        src = warm_source(fsm)
        if src is None:
            self._goal = None
            return None
        g = self._goal
        if g is None or g.obj is not src:
            g = obj_goal(src, valid=lambda s: warm_source(fsm) is s, radius=src.arrive_radius)
            self._goal = g
        return g

    def urgent(self):
        fsm = self.fsm
        src = warm_source(fsm)
        if src is None or fsm.body.cold < tuning.COLD_SEEK_ENTER:
            return False
        if src.in_warm_zone(fsm.body.chunk1.x, fsm.body.chunk1.y):
            return False
        return not fsm.planner.in_cooldown(self.goal())

    def available(self):
        if warm_source(self.fsm) is None:
            return False
        return not self.fsm.planner.in_cooldown(self.goal())
