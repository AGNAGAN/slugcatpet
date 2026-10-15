"""多猫协调：互相感知、目标占用、通行让路。行为只经这里了解别的猫。"""

from __future__ import annotations

import math

from .traffic import Traffic

STEAL_FRAC = 0.5  # 比占用者近到一半以内才抢目标


class Claim:
    __slots__ = ("owner", "slot", "target", "state", "since")

    def __init__(self, owner, slot, target, state, since):
        self.owner = owner
        self.slot = slot
        self.target = target
        self.state = state
        self.since = since


class Social:
    def __init__(self, win):
        self.win = win
        self.now = 0
        self._claims = {}  # id(target) → Claim
        self._held = {}  # (owner, slot) → Claim
        self.traffic = Traffic(self)

    def tick(self):
        self.now += 1
        self.traffic.update()

    def others(self, me):
        return [p for p in self.win.pets if p is not me and getattr(p, "body", None) is not None]

    @staticmethod
    def state_of(pet):
        beh = getattr(pet, "behavior", None)
        return beh.state if beh is not None else None

    def others_x(self, me):
        return [p.body.chunk1.x for p in self.others(me)]

    def count(self):
        return len(self.win.pets)

    def order(self, me):
        """这一 tick 给我的让路指令；没有 None。"""
        return self.traffic.orders.get(me)

    def _valid(self, target):
        c = self._claims.get(id(target))
        if c is None or c.target is not target:
            return None
        if c.owner not in self.win.pets or (c.state is not None and self.state_of(c.owner) != c.state):
            self._drop(c)
            return None
        return c

    def _drop(self, c):
        if self._claims.get(id(c.target)) is c:
            del self._claims[id(c.target)]
        if self._held.get((c.owner, c.slot)) is c:
            del self._held[(c.owner, c.slot)]

    def claim(self, me, slot, target, state=None):
        """占用 target；同一 slot 原先占的自动放掉。"""
        old = self._held.get((me, slot))
        if old is not None:
            self._drop(old)
        prev = self._valid(target)
        if prev is not None and prev.owner is not me:
            self._drop(prev)
        c = Claim(me, slot, target, state, self.now)
        self._claims[id(target)] = c
        self._held[(me, slot)] = c

    def release(self, me, slot):
        c = self._held.get((me, slot))
        if c is not None:
            self._drop(c)

    def held(self, me, slot):
        c = self._held.get((me, slot))
        return None if c is None else c.target

    def taken(self, me, target) -> bool:
        c = self._valid(target)
        return c is not None and c.owner is not me

    def free_for(self, me, target, patience=None, steal=STEAL_FRAC) -> bool:
        """target 我能不能去：没人占 / 我占着 / 占用者待太久 / 我近得多。"""
        c = self._valid(target)
        if c is None or c.owner is me:
            return True
        if patience is not None and self.now - c.since >= patience:
            return True
        if steal is None:
            return False
        return _dist(me, target) < steal * _dist(c.owner, target)


def _dist(pet, target):
    c = pet.body.chunk0
    return math.hypot(target.x - c.x, target.y - c.y)
