"""能力三问接口：can_touch / can_stay / make_controller。"""

from __future__ import annotations
import math

from dataclasses import dataclass

from .. import tuning

RUNNING = "running"
DONE = "done"
GIVEUP = "giveup"
HOLD = "hold"  # 到位持续维持驻留：不重规划/不计超时/不计失败

HOLDING = "holding"

MODE_TOUCH = "touch"
MODE_STAY = "stay"


@dataclass(frozen=True)
class Estimate:
    """粗线性代价：预估耗时 tick / 预估体力开销。"""

    time_est: float
    energy_est: float


@dataclass
class Candidate:
    ability_key: str
    time_est: float
    energy_est: float
    _factory: object

    def make_controller(self):
        return self._factory()


class Reach:
    """够取方式基类；控制器协议：update() -> running|done|giveup，cancel() 清理。"""

    key = ""

    def __init__(self, pet):
        self.pet = pet

    def can_touch(self, goal):
        return None

    def can_stay(self, goal):
        return None

    def make_controller(self, goal):
        raise NotImplementedError


class PointTarget:
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y


def walk_band(pet):
    body = pet.body
    xmin = getattr(body, "walk_min", None)
    xmax = getattr(body, "walk_max", None)
    return (0.0 if xmin is None else xmin, pet._WL if xmax is None else xmax)


def reach_assist(pet, goal, gx, gy):
    """近目标探身：距目标 < arm_full_reach*REACH_GATE_K 才伸臂。"""
    body = pet.body
    c0 = body.chunk0
    if math.hypot(gx - c0.x, gy - c0.y) < body.arm_full_reach * tuning.REACH_GATE_K:
        tgt = goal.obj if goal.obj is not None else PointTarget(gx, gy)
        body.reach_for(tgt, "r" if gx >= c0.x else "l")
