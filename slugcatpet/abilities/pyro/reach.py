"""爆跳够取：普通起跳后在空中爆冲，够远处或高处的目标。"""

from __future__ import annotations
import math

from ... import tuning
from ...core.units import clampf
from ...planning.reach import Reach, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band
from ...planning.backflip_reach import SETTLE_MAX, SETTLE_VX, best_launch_hit, sweep_hit_topsafe, takeoff_c0_h
from ...planning.jump_arc import get_pyro_arc, PYRO_INPUTS
from ...planning.jump_reach import JumpReach, PLAN_HIT_RADIUS
from . import mechanics as pyro

PYRO_REACH_MIN_DX = 140.0  # 水平距离小于此不考虑爆跳
_VARIANTS = ("vert", "side+", "side-", "diag+", "diag-")


def _fuel_ok(pet, body):
    """燃料加一不超过 heat_cap 才爆跳。"""
    return pet.abilities["pyro"].fuel_ok(body)


class PyroJumpReach(Reach):
    key = "pyrojump"

    def _plan(self, goal):
        pet = self.pet
        body = pet.body
        if getattr(body, "swimming", False) or getattr(body, "zerog", False):
            return None
        if not _fuel_ok(pet, body):
            return None
        gx, gy = goal.pos()
        hip = body.chunk1
        if math.hypot(gx - hip.x, gy - hip.y) < PYRO_REACH_MIN_DX:
            return None
        xmin, xmax = walk_band(pet)
        stats = pet.cat.stats
        launch_y = pet._HL - takeoff_c0_h(stats)
        best = None
        for v in _VARIANTS:
            r = best_launch_hit(get_pyro_arc(stats, v), gx, gy, launch_y, xmin, xmax, PLAN_HIT_RADIUS, hip.x)
            if r is not None and (best is None or r[2] < best[3]):
                best = (r[0], v, r[1], r[2])
        if best is None:
            return None
        jump_est = JumpReach(pet).can_touch(goal)
        if jump_est is not None and jump_est.time_est <= best[3]:
            return None
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        _, _, hit, t = plan
        walk_t = t - hit - tuning.PLAN_STARTUP_TICKS
        return Estimate(t, walk_t * tuning.PLAN_EN_RATE_LIGHT + hit * tuning.PLAN_EN_RATE_VIGOROUS)

    def make_controller(self, goal):
        return PyroJumpReachController(self.pet, goal)


class PyroJumpReachController:
    def on_geometry(self):
        """只在地上走、跳，不受杆增删影响。"""
        return True

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.phase = "walk"
        self._settle = 0
        self._air = 0
        self._fired = False
        self._airborne = False
        plan = PyroJumpReach(pet)._plan(goal)
        self._launch_x = plan[0] if plan is not None else None
        self._variant = plan[1] if plan is not None else None

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        reach_assist(pet, self.goal, gx, gy)
        if self._launch_x is None:
            return GIVEUP
        xmin, xmax = walk_band(pet)
        lx = clampf(self._launch_x, xmin, xmax)
        if self.phase == "walk":
            if body.on_floor() and abs(body.chunk1.x - lx) <= tuning.PLAN_JUMP_TAKEOFF_EPS:
                body.stop_walk()
                self.phase = "settle"
                return RUNNING
            if not body.walk_to(lx, tuning.PLAN_JUMP_TAKEOFF_EPS):
                return GIVEUP  # 起跳点走不到
            return RUNNING
        if self.phase == "settle":
            body.stop_walk()
            self._settle += 1
            still = abs(body.chunk0.vx) < SETTLE_VX and abs(body.chunk1.vx) < SETTLE_VX
            if body.on_floor() and (still or self._settle > SETTLE_MAX):
                v = self._pick_at_launch(gx, gy)
                if v is None:
                    return GIVEUP  # 还没起跳，直接放弃，不白耗燃料
                self._variant = v
                body.request_jump("stand")
                self.phase = "air"
            return RUNNING
        if not body.on_floor():
            self._airborne = True
            self._air += 1
            if not self._fired and self._air >= tuning.PYRO_BOOST_AIR_TICKS:
                self._fired = True
                if _fuel_ok(pet, body):
                    ix, iy = PYRO_INPUTS[self._variant]
                    pyro.fire_air_jump(pet, body, ix, iy)
        elif self._airborne:
            self._cleanup()
            return DONE
        return RUNNING

    def _pick_at_launch(self, gx, gy):
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        order = (self._variant,) + tuple(v for v in _VARIANTS if v != self._variant)
        for v in order:
            if (
                sweep_hit_topsafe(get_pyro_arc(stats, v), gx - c0.x, gy - c0.y, tuning.GRAB_REACH, c0.y)
                is not None
            ):
                return v
        return None

    def _cleanup(self):
        # 自动行为没有 ANIM_RESET 兜底，结束时手动清理
        body = self.pet.body
        body.animation = None
        body.jump_boost = 0.0
        body.stop_walk()
        body.set_posture(True)
        if self._variant is not None:
            ix = PYRO_INPUTS[self._variant][0]
            if ix:
                body.facing = ix

    def cancel(self):
        self._cleanup()
