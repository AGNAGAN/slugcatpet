"""竖杆舌钩够取：爬到竖杆合适高度，从杆上射舌够目标。"""

from __future__ import annotations
import math

from ... import tuning
from . import consts
from ...core.units import clampf
from ...planning.pole_reach import (
    LAUNCH_ARRIVE_EPS,
    POLE_TIP_C0_H,
    _PoleClimb,
    _c0_range,
    _climb_cost_to,
    _vpoles,
)
from ...planning.reach import Reach, Estimate, RUNNING, GIVEUP, reach_assist
from .reach import FETCH_IDEAL, FETCH_REEL, APPROACH_TIMEOUT, reset_tongue
from .aim import fire_at, tongue_of


class PoleTongueReach(Reach):
    key = "poletongue"

    def _plan(self, goal):
        pet = self.pet
        tg = tongue_of(pet)
        if tg is None:
            return None
        gx, gy = goal.pos()
        rng = tg.total * consts.PLAN_TONGUE_RANGE_FRAC
        best = None
        best_t = None
        for pole in _vpoles(pet):
            hy_lo, hy_hi = _c0_range(pet, pole)
            hy = clampf(gy, hy_lo, hy_hi)
            d = math.hypot(gx - pole.x, gy - hy)
            if d <= rng:
                ct, ce = _climb_cost_to(pet, pole, hy)
                t = ct + d / consts.PLAN_TONGUE_SPEED + tuning.PLAN_STARTUP_TICKS
                if best_t is None or t < best_t:
                    best_t = t
                    best = (
                        pole,
                        hy,
                        Estimate(t, ce + (d / consts.PLAN_TONGUE_SPEED) * tuning.PLAN_EN_RATE_LIGHT),
                    )
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        return plan[2] if plan is not None else None

    def make_controller(self, goal):
        plan = self._plan(goal)
        return PoleTongueController(self.pet, goal, plan[0] if plan else None, plan[1] if plan else None)


class PoleTongueController(_PoleClimb):
    def __init__(self, pet, goal, pole, release_hy):
        self.pet = pet
        self.goal = goal
        self.pole = pole
        self.release_hy = release_hy
        self.climber = None
        self.phase = "climb"
        self.timer = 0

    def update(self):
        pet = self.pet
        gx, gy = self.goal.pos()
        if self.pole is None:
            return GIVEUP
        reach_assist(pet, self.goal, gx, gy)
        if self.phase == "climb":
            tip_c0y = self.pole.top_y - POLE_TIP_C0_H
            st = self._step_to_height(
                self.release_hy, want_tip=(self.release_hy <= tip_c0y + LAUNCH_ARRIVE_EPS)
            )
            if st == "fail":
                return GIVEUP
            if st == "ready":
                self._drop_pole()
                pet.body.release_to_air(move_dir=0)
                self.phase = "fire"
            return RUNNING
        tg = tongue_of(pet)
        if self.phase == "fire":
            if tg is None:
                return GIVEUP
            if tg.is_idle():
                if self.goal.obj is not None:
                    fire_at(pet, self.goal.obj.x, self.goal.obj.y, self.goal.obj)
                else:
                    fire_at(pet, gx, gy)
                self.phase = "reel"
                self.timer = 0
            return RUNNING
        self.timer += 1
        if tg.attached:
            tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)
            if self.timer > 2 * APPROACH_TIMEOUT:
                reset_tongue(pet)
                return GIVEUP
            return RUNNING
        if self.timer > APPROACH_TIMEOUT:
            reset_tongue(pet)
            return GIVEUP
        return RUNNING

    def cancel(self):
        self._drop_pole()
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
