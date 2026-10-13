"""竖杆够取族：爬杆后斜跳 / 杆顶直跳 / 松杆落体。"""

from __future__ import annotations

from .. import tuning
from ..items.base import CLIMBABLE
from .reach import Reach, Estimate, RUNNING, DONE, GIVEUP, reach_assist
from .jump_arc import get_arc, get_drop_arc, get_pole_jump_arc, sweep_hit

POLE_TIP_C0_H = 17.0  # 杆顶/站立时 chunk0 距顶高
LAUNCH_ARRIVE_EPS = 6.0


def _climbables(pet):
    items = getattr(pet, "items_affording", None)
    return items(CLIMBABLE) if items is not None else getattr(pet, "poles", ())


def _vpoles(pet):
    """底端着地的竖杆（含竖扎在地上的矛）。"""
    return [
        p for p in _climbables(pet) if getattr(p, "kind", None) == "vertical" and getattr(p, "grounded", True)
    ]


def _c0_range(pet, pole):
    """杆上 chunk0 可及 y 区间 [顶端高, 近地高]（y↓，顶端 y 最小）。"""
    return (pole.top_y - POLE_TIP_C0_H, pet._HL - POLE_TIP_C0_H)


def _climb_cost_to(pet, pole, hy):
    walk_t = abs(pet.body.chunk1.x - pole.x) / tuning.PLAN_WALK_SPEED
    climb_t = max(0.0, (pet._HL - POLE_TIP_C0_H) - hy) / tuning.PLAN_CLIMB_SPEED
    return (walk_t + climb_t, walk_t * tuning.PLAN_EN_RATE_LIGHT + climb_t * tuning.PLAN_EN_RATE_VIGOROUS)


def _search_height(arc, gx, gy, pole_x, hy_lo, hy_hi, radius, pet, pole):
    """找最省 (hy, tick, 爬耗时, 爬体力)，hy∈[hy_lo,hy_hi] 为 chunk0 发射高。"""
    best = None
    best_c = None
    for i, (px, py) in enumerate(arc.points):
        hy = gy - py
        if not (hy_lo <= hy <= hy_hi):
            continue
        if abs((pole_x + px) - gx) > radius:
            continue
        ct, ce = _climb_cost_to(pet, pole, hy)
        c = ct + (i + 1)
        if best_c is None or c < best_c:
            best_c = c
            best = (hy, i + 1, ct, ce)
    return best


class _PoleClimb:
    """爬杆到指定高度混入：_step_to_height() 回 running/ready/fail；_drop_pole() 收 PoleClimber。"""

    def _ensure_climber(self):
        if self.climber is None:
            from ..brain.skills.pole_climb import PoleClimber

            self.climber = PoleClimber(self.pet, self.pole, getattr(self.pet, "rng", None))

    def _step_to_height(self, release_hy, want_tip):
        pet = self.pet
        if self.pole not in _climbables(pet):
            return "fail"
        self._ensure_climber()
        done = self.climber.update(want_dismount=False)
        if self.climber.giveup:
            return "fail"
        phase = self.climber.phase
        if want_tip:
            return "ready" if phase == "tip" else ("fail" if done else "running")
        # 中途高度：须已抓上杆（phase climb/tip）且 chunk0 爬到发射高
        if phase in ("climb", "tip") and pet.body.chunk0.y <= release_hy + LAUNCH_ARRIVE_EPS:
            return "ready"
        if phase == "tip":
            return "ready"
        return "fail" if done else "running"

    def _drop_pole(self):
        if self.climber is not None:
            self.climber.release()
            self.climber = None


class PoleJumpReach(Reach):
    key = "polejump"

    def _plan(self, goal):
        pet = self.pet
        gx, gy = goal.pos()
        stats = pet.cat.stats
        best = None
        best_t = None

        def consider(pole, kind, params, hy, t, e):
            nonlocal best, best_t
            if best_t is None or t < best_t:
                best_t = t
                best = (pole, kind, params, hy, t, e)

        for pole in _vpoles(pet):
            hy_lo, hy_hi = _c0_range(pet, pole)
            tip_c0y = hy_lo
            ct, ce = _climb_cost_to(pet, pole, tip_c0y)
            for md in (0, 1, -1):
                done = False
                for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                    hit = sweep_hit(get_arc(stats, hold, md), gx - pole.x, gy - tip_c0y, tuning.GRAB_REACH)
                    if hit is not None:
                        consider(
                            pole,
                            "tip",
                            (hold, md),
                            tip_c0y,
                            ct + hit + tuning.PLAN_STARTUP_TICKS,
                            ce + hit * tuning.PLAN_EN_RATE_VIGOROUS,
                        )
                        done = True
                        break
                if done:
                    break
            for d in (1, -1):
                r = _search_height(
                    get_pole_jump_arc(stats, d), gx, gy, pole.x, hy_lo, hy_hi, tuning.GRAB_REACH, pet, pole
                )
                if r is not None:
                    hy, hit, ct2, ce2 = r
                    consider(
                        pole,
                        "beam",
                        (d,),
                        hy,
                        ct2 + hit + tuning.PLAN_STARTUP_TICKS,
                        ce2 + hit * tuning.PLAN_EN_RATE_VIGOROUS,
                    )
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        return Estimate(plan[4], plan[5])

    def make_controller(self, goal):
        return PoleLaunchController(self.pet, goal, self._plan(goal))


class PoleDropReach(Reach):
    key = "poledrop"

    def _plan(self, goal):
        pet = self.pet
        gx, gy = goal.pos()
        stats = pet.cat.stats
        best = None
        best_t = None
        for pole in _vpoles(pet):
            hy_lo, hy_hi = _c0_range(pet, pole)
            for md in (0, 1, -1):
                r = _search_height(
                    get_drop_arc(stats, md), gx, gy, pole.x, hy_lo, hy_hi, tuning.GRAB_REACH, pet, pole
                )
                if r is not None:
                    hy, hit, ct, ce = r
                    t = ct + hit + tuning.PLAN_STARTUP_TICKS
                    if best_t is None or t < best_t:
                        best_t = t
                        best = (pole, "drop", (md,), hy, t, ce + hit * tuning.PLAN_EN_RATE_LIGHT)
        return best

    def can_touch(self, goal):
        plan = self._plan(goal)
        if plan is None:
            return None
        return Estimate(plan[4], plan[5])

    def make_controller(self, goal):
        return PoleLaunchController(self.pet, goal, self._plan(goal))


class PoleLaunchController(_PoleClimb):
    """爬杆到发射高度 → 按 kind（tip/beam/drop）起跳/落体 → 落地报 done。"""

    def __init__(self, pet, goal, plan):
        self.pet = pet
        self.goal = goal
        self.plan = plan
        self.pole = plan[0] if plan else None
        self.kind = plan[1] if plan else None
        self.params = plan[2] if plan else None
        self.release_hy = plan[3] if plan else None
        self.climber = None
        self.phase = "climb"
        self._airborne = False
        self._md = 0

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        if self.pole is None:
            return GIVEUP
        if self.phase == "climb":
            reach_assist(pet, self.goal, gx, gy)
            st = self._step_to_height(self.release_hy, want_tip=(self.kind == "tip"))
            if st == "fail":
                return GIVEUP
            if st == "ready":
                self.phase = "launch"
            return RUNNING
        if self.phase == "launch":
            self._drop_pole()
            if self.kind == "tip":
                hold, md = self._pick_tip(gx, gy)
                body.tip_launch(hold_ticks=hold, move_dir=md)
                self._md = md
            elif self.kind == "beam":
                d = self.params[0]
                body.pole_jump(d)
                self._md = d
            else:
                md = self.params[0]
                body.release_to_air(move_dir=md)
                self._md = md
            self.phase = "air"
            return RUNNING
        reach_assist(pet, self.goal, gx, gy)
        if not body.on_floor():
            self._airborne = True
            body.move_dir = self._md
        elif self._airborne:
            body.stop_walk()
            return DONE
        return RUNNING

    def _pick_tip(self, gx, gy):
        c0 = self.pet.body.chunk0
        stats = self.pet.cat.stats
        for md in (0, 1, -1):
            for hold in tuning.PLAN_JUMP_HOLD_GEARS:
                if sweep_hit(get_arc(stats, hold, md), gx - c0.x, gy - c0.y, tuning.GRAB_REACH) is not None:
                    return hold, md
        return self.params

    def cancel(self):
        self._drop_pole()
        self.pet.body.stop_walk()
