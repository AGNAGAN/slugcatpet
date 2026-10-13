"""多猫协调：互相感知、目标占用、让路裁决、杆顶挤人。行为只经这里了解别的猫。"""

from __future__ import annotations

import math

STEAL_FRAC = 0.5  # 比占用者近到一半以内才抢目标


class Claim:
    __slots__ = ("owner", "slot", "target", "state", "since")

    def __init__(self, owner, slot, target, state, since):
        self.owner = owner
        self.slot = slot
        self.target = target
        self.state = state
        self.since = since


class Crowd:
    __slots__ = ("shoved", "yield_to", "blocked", "yield_cd", "jump_cd")

    def __init__(self):
        self.shoved = 0
        self.yield_to = None
        self.blocked = 0
        self.yield_cd = 0
        self.jump_cd = 0


class Social:
    def __init__(self, win):
        self.win = win
        self.now = 0
        self._claims = {}  # id(target) → Claim
        self._held = {}  # (owner, slot) → Claim
        self._crowd = {}
        self._tip = {}  # id(pole) → 站在杆顶的猫们
        self._evicted = set()

    def tick(self):
        self.now += 1

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

    def crowd(self, me) -> Crowd:
        c = self._crowd.get(me)
        if c is None:
            c = self._crowd[me] = Crowd()
        return c

    def yielding_to(self, me):
        if hasattr(me, "win"):  # 传入的是状态机
            me = me.win
        c = self._crowd.get(me)
        return None if c is None else c.yield_to

    def at_tip(self, me, pole, on):
        s = self._tip.setdefault(id(pole), set())
        if on:
            s.add(me)
        else:
            s.discard(me)

    def leave_tips(self, me):
        for s in self._tip.values():
            s.discard(me)

    def tip_holders(self, pole, me):
        s = self._tip.get(id(pole))
        if not s:
            return []
        return [p for p in self.win.pets if p is not me and p in s and self.state_of(p) == "PoleClimb"]

    def push_off(self, pet):
        self._evicted.add(pet)

    def take_push(self, me) -> bool:
        if me in self._evicted:
            self._evicted.discard(me)
            return True
        return False


def _dist(pet, target):
    c = pet.body.chunk0
    return math.hypot(target.x - c.x, target.y - c.y)
