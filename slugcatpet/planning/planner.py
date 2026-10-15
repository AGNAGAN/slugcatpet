"""规划器：列出能用的够取方式，去掉体力不够的，按耗时排序。"""

from __future__ import annotations
import time

from .climb_reach import ClimbPathReach
from .reach import Candidate
from .cooldown import CooldownRegistry
from .jump_reach import JumpReach
from .walk_reach import WalkReach


class Planner:
    """pet 只要像 PetUnit：有 body、cat，以及世界的 _WL、_HL、world_version、poles。"""

    def __init__(self, pet, clock=time.monotonic):
        self.pet = pet
        self._cooldown = CooldownRegistry(clock)
        self._ability_cache = None  # 够取方式没有状态，建一次后复用

    def _abilities(self):
        if self._ability_cache is not None:
            return self._ability_cache
        out = [WalkReach(self.pet), JumpReach(self.pet)]
        for ab in getattr(self.pet, "abilities", {}).values():
            out += ab.reaches(self.pet)
        out.append(ClimbPathReach(self.pet))
        self._ability_cache = out
        return out

    def _usable(self):
        """眼下用得上的够取方式：人在杆上时只有能从杆上出发的。"""
        on_pole = self.pet.body.on_pole
        return [ab for ab in self._abilities() if ab.from_pole or not on_pole]

    def _candidates(self, goal, question):
        energy = self.pet.body.energy
        out = []
        for ab in self._usable():
            est = getattr(ab, question)(goal)
            if est is None or est.energy_est > energy:
                continue
            out.append(
                Candidate(ab.key, est.time_est, est.energy_est, lambda ab=ab, g=goal: ab.make_controller(g))
            )
        out.sort(key=lambda c: c.time_est)
        return out

    def touch_candidates(self, goal):
        return self._candidates(goal, "can_touch")

    def stay_candidates(self, goal):
        return self._candidates(goal, "can_stay")

    def any_touch(self, goal):
        energy = self.pet.body.energy
        for ab in self._usable():
            est = ab.can_touch(goal)
            if est is None or est.energy_est > energy:
                continue
            return True
        return False

    def can_touch(self, goal):
        return bool(self.touch_candidates(goal))

    def can_stay(self, goal):
        return bool(self.stay_candidates(goal))

    def world_version(self):
        return getattr(self.pet, "world_version", 0)

    def on_giveup(self, goal):
        self._cooldown.add(goal.key(), self.world_version())

    def in_cooldown(self, goal):
        return self._cooldown.active(goal.key(), self.world_version())
