"""游泳。"""
from __future__ import annotations

from ... import tuning
from ...brain.fsm import _lerpmap
from ..base import Behavior
from .state import Swimming


class Swim(Behavior):
    key = "swim"
    title = {"zh": "游泳", "en": "Swim"}
    doc = "落水后的游泳状态：漂游、潜泳取食、在水面休息。喜不喜欢水看性格 swim_zeal。"
    essential = True

    def mount(self, fsm):
        z = fsm.traits.swim_zeal
        depth_max = _lerpmap(z, 0.0, 1.0, tuning.SWIM_DRIFT_DEPTH_MAX,
                                       tuning.SWIM_DRIFT_DEEP_MAX)
        fsm.body.swim_boost_dist = _lerpmap(z, 0.0, 1.0, tuning.SWIM_BOOST_DIST,
                                            tuning.SWIM_BOOST_DIST_ZEAL)
        fsm.add_state(Swimming).depth_max = depth_max
