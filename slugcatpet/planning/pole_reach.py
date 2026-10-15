"""竖杆够取的共用部分（舌头的竖杆舌钩用）。"""

from __future__ import annotations

from .. import tuning
from ..items.base import CLIMBABLE

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
    """杆上 chunk0 能到的 y 区间 (顶端, 近地端)，y↓。"""
    return (pole.top_y - POLE_TIP_C0_H, pet._HL - POLE_TIP_C0_H)


def _climb_cost_to(pet, pole, hy):
    walk_t = abs(pet.body.chunk1.x - pole.x) / tuning.PLAN_WALK_SPEED
    climb_t = max(0.0, (pet._HL - POLE_TIP_C0_H) - hy) / tuning.PLAN_CLIMB_SPEED
    return (walk_t + climb_t, walk_t * tuning.PLAN_EN_RATE_LIGHT + climb_t * tuning.PLAN_EN_RATE_VIGOROUS)


def _search_height(arc, gx, gy, pole_x, hy_lo, hy_hi, radius, pet, pole):
    """在 [hy_lo, hy_hi] 里找总耗时最少的 chunk0 起跳高度，返回 (hy, 飞行 tick, 爬耗时, 爬体力)。"""
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
    """混入类：爬到指定高度。_step_to_height() 返回 running / ready / fail，_drop_pole() 松手。"""

    def _ensure_climber(self):
        if self.climber is None:
            from ..brain.skills.pole_climb import PoleClimber

            self.climber = PoleClimber(self.pet, self.pole)

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
        # 中途起跳：已经上杆（climb / tip）且 chunk0 爬到了起跳高度
        if phase in ("climb", "tip") and pet.body.chunk0.y <= release_hy + LAUNCH_ARRIVE_EPS:
            return "ready"
        if phase == "tip":
            return "ready"
        return "fail" if done else "running"

    def _drop_pole(self):
        if self.climber is not None:
            self.climber.release()
            self.climber = None
