"""舌取够取：走进射程，射舌粘住，收绳拉近，荡过目标时松舌借势。"""

from __future__ import annotations
import math

from ... import tuning
from . import consts
from .aim import fire_at, tongue_of
from ...core.units import clampf
from ...planning.reach import Reach, Estimate, RUNNING, GIVEUP, reach_assist, walk_band

FETCH_IDEAL = 10.0
FETCH_REEL = 3.0
FLYBY_TRIGGER = 1.4  # 荡到目标上方、水平距离在 GRAB_REACH 的这么多倍以内时松舌借势
APPROACH_TIMEOUT = 240
TONGUE_UNDER_TOL = 40.0


def mouth_pos(pet):
    gfx = getattr(pet, "gfx", None)
    if gfx is not None:
        return gfx.mouth_world()
    c0 = pet.body.chunk0
    return c0.x, c0.y


def reset_tongue(pet, owner=None):
    """收舌、恢复默认参数、解除吊挂；舌头被别人占着时什么都不做。"""
    tg = tongue_of(pet)
    if tg is not None:
        if tg.owned_by_other(owner):
            return
        tg.retract()
        tg.reset_config()
    pet.body.suspended = False


def tongue_fire_range(pet):
    return tongue_of(pet).total * consts.PLAN_TONGUE_RANGE_FRAC


class TongueReach(Reach):
    key = "tongue"

    def can_touch(self, goal):
        pet = self.pet
        gx, gy = goal.pos()
        rng = tongue_fire_range(pet)
        best = None
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        d = math.hypot(gx - fx, gy - (pet._HL - consts.PLAN_MOUTH_H))
        if d <= rng:
            t = (
                abs(pet.body.chunk1.x - fx) / tuning.PLAN_WALK_SPEED
                + d / consts.PLAN_TONGUE_SPEED
                + tuning.PLAN_STARTUP_TICKS
            )
            best = Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)
        mox, moy = mouth_pos(pet)
        dm = math.hypot(gx - mox, gy - moy)
        if dm <= rng:
            t = dm / consts.PLAN_TONGUE_SPEED + tuning.PLAN_STARTUP_TICKS
            if best is None or t < best.time_est:
                best = Estimate(t, t * tuning.PLAN_EN_RATE_LIGHT)
        return best

    def make_controller(self, goal):
        return TongueApproachController(self.pet, goal)


class TongueApproachController:
    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.timer = 0
        self._fired = False  # 只射一发，收回后就放弃

    def update(self):
        pet = self.pet
        body = pet.body
        tg = tongue_of(pet)
        self.timer += 1
        gx, gy = self.goal.pos()
        reach_assist(pet, self.goal, gx, gy)
        mox, moy = mouth_pos(pet)
        c0 = body.chunk0
        xmin, xmax = walk_band(pet)
        fx = clampf(gx, xmin, xmax)
        in_range = math.hypot(gx - mox, gy - moy) <= tongue_fire_range(pet)
        under = abs(body.chunk1.x - fx) <= TONGUE_UNDER_TOL

        if tg.is_idle():
            if self._fired:
                reset_tongue(pet)
                return GIVEUP
            if not (in_range and under):
                if body.on_floor():
                    if under and not in_range:
                        return GIVEUP
                    body.walk_to(fx)
                self.timer = 0
                return RUNNING
            body.stop_walk()
            if body.on_floor() and gy < c0.y - tuning.GRAB_REACH:
                body.request_jump("stand")
            if self.goal.obj is not None:
                fire_at(pet, self.goal.obj.x, self.goal.obj.y, self.goal.obj)
            else:
                fire_at(pet, gx, gy)
            self._fired = True
            self.timer = 0
            return RUNNING

        if tg.attached:
            tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)
            if self._should_flyby(gx, gy):
                tg.retract()
            elif self.timer > 2 * APPROACH_TIMEOUT:
                reset_tongue(pet)
                return GIVEUP
            return RUNNING

        if self.timer > APPROACH_TIMEOUT:
            reset_tongue(pet)
            return GIVEUP
        return RUNNING

    def _should_flyby(self, gx, gy):
        c0 = self.pet.body.chunk0
        if c0.y >= gy:
            return False
        return abs(c0.x - gx) < tuning.GRAB_REACH * FLYBY_TRIGGER

    def cancel(self):
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
