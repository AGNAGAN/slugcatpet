"""杆网的后台预算：杆变了以后，各只猫的杆网按固定额度每 tick 轮流算一部分。"""

from __future__ import annotations

from ..items.base import CLIMBABLE
from .climbmap import map_for

SPOTS_PER_TICK = 30  # 每 tick 一共算这么多个杆网位置的出边
SEARCHES_PER_TICK = 2  # 每 tick 最多现算几次寻路（命中缓存的不算）


class PlanBudget:
    def __init__(self):
        self._next = 0
        self._searches = SEARCHES_PER_TICK

    def take_search(self):
        """这一 tick 还能不能现算一次寻路。"""
        if self._searches <= 0:
            return False
        self._searches -= 1
        return True

    def run(self, pets):
        """推进一 tick 的后台工作。"""
        self._searches = SEARCHES_PER_TICK
        n = len(pets)
        left = SPOTS_PER_TICK
        for k in range(n):
            pet = pets[(self._next + k) % n]
            if not pet.items_affording(CLIMBABLE):
                continue
            cm = map_for(pet)
            if cm.ready:
                continue
            left -= cm.warm(left)
            if left <= 0:
                self._next = (self._next + k) % n  # 没算完的这只下 tick 接着算
                return
        self._next = 0
