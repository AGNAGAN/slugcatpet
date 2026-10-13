"""失重时朝漂去的方向随手吐舌。"""

from __future__ import annotations

import math

from ...abilities.base import Param
from ...abilities.tongue.aim import fire, tongue_of
from ..base import Behavior


class ZeroGLick(Behavior):
    key = "zerog_lick"
    title = {"zh": "失重吐舌", "en": "Zero-G licks"}
    doc = "失重漂着（闲逛或追食物）时，偶尔朝要去的地方吐舌，粘住墙就借力。"
    requires = ("tongue",)
    params = {
        "prob": Param(0.02, 0.0, 1.0, "每 tick 吐舌的概率"),
        "min_dist": Param(60.0, 0.0, 1000.0, "离目标这么远才吐"),
    }

    def mount(self, fsm):
        pet, p = fsm.win, self.p

        def aim(x, y):
            c0 = pet.body.chunk0
            if (
                tongue_of(pet).is_idle()
                and math.hypot(x - c0.x, y - c0.y) > p.min_dist
                and fsm.rng.random() < p.prob
            ):
                fire(pet, x, y)
            return False

        fsm.add_task("zerog_aim", aim)
