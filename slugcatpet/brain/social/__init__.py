"""多猫协调：互相感知、目标占用、通行让路、猫际关系。行为只经这里了解别的猫。"""

from __future__ import annotations

import math

from ... import tuning
from ..hands import EAT_LATER
from .bonds import LYING, Bonds
from .traffic import CONTACT, Traffic

STEAL_FRAC = 0.5  # 比占用者近到一半以内才抢目标
SETTLING_REACH = 3.0  # 正要趴下、预约了位置的猫，按臀半径的这么多倍占地


class Claim:
    __slots__ = ("owner", "slot", "target", "state", "since", "until")

    def __init__(self, owner, slot, target, state, since, until=None):
        self.owner = owner
        self.slot = slot
        self.target = target
        self.state = state
        self.since = since
        self.until = until  # 到这个 tick 自动失效，None 为不限时


class Social:
    def __init__(self, win):
        self.win = win
        self.now = 0
        self._claims = {}  # id(target) → Claim
        self._held = {}  # (owner, slot) → Claim
        self.traffic = Traffic(self)
        self.bonds = Bonds(self)

    def tick(self):
        self.now += 1
        self.traffic.update()
        self.bonds.tick()

    def others(self, me):
        return [p for p in self.win.pets if p is not me and getattr(p, "body", None) is not None]

    @staticmethod
    def state_of(pet):
        beh = getattr(pet, "behavior", None)
        return beh.state if beh is not None else None

    def bond(self, me, other) -> float:
        return self.bonds.get(me, other)

    def affinity(self, me) -> float:
        """我对猫的一般态度：1 爱凑近，-1 爱躲开；只看亲和。"""
        return max(-1.0, min(1.0, tuning.SOCIAL_SYM_PULL * (me.traits.sympathy - 0.5)))

    def pull(self, me, other) -> float:
        """我想离 other 多近：1 凑过去，-1 躲开；看我的亲和和我们的关系。"""
        w = self.affinity(me) + tuning.SOCIAL_BOND_PULL * self.bond(me, other)
        return max(-1.0, min(1.0, w))

    def lying_beside(self, me) -> int:
        """我趴在地上时，身子挨着我趴着的猫有几只。"""
        mine = me.body.lying_span()
        if mine is None:
            return 0
        gap = tuning.HUDDLE_TOUCH
        return sum(
            1
            for o in self.others(me)
            if (s := o.body.lying_span()) is not None
            and me.body.same_floor(o.body)
            and s[0] - gap < mine[1]
            and mine[0] < s[1] + gap
        )

    def wants_food(self, pet, item) -> bool:
        """pet 饿着（不够冬眠）、能吃 item、手里也没留着吃的。"""
        b = pet.body
        fsm = getattr(pet, "behavior", None)
        return (
            fsm is not None
            and not b.dead
            and b.food < b.food_hibernate
            and pet.can_eat(item)
            and fsm.hands.held(EAT_LATER) is None
        )

    def others_pull(self, me):
        """别的猫的 [(我挨着它站的位置 x, 想靠近它多少)]；位置在它靠我这一侧，不压到它。"""
        x = me.body.chunk1.x
        gap = CONTACT["F"]
        return [
            (p.body.chunk1.x + math.copysign(gap, x - p.body.chunk1.x), self.pull(me, p))
            for p in self.others(me)
        ]

    def count(self):
        return len(self.win.pets)

    def order(self, me):
        """这一 tick 给我的让路指令；没有 None。"""
        return self.traffic.orders.get(me)

    def _valid(self, target):
        c = self._claims.get(id(target))
        if c is None or c.target is not target:
            return None
        if (
            c.owner not in self.win.pets
            or (c.state is not None and self.state_of(c.owner) != c.state)
            or (c.until is not None and self.now > c.until)
        ):
            self._drop(c)
            return None
        return c

    def _drop(self, c):
        if self._claims.get(id(c.target)) is c:
            del self._claims[id(c.target)]
        if self._held.get((c.owner, c.slot)) is c:
            del self._held[(c.owner, c.slot)]

    def claim(self, me, slot, target, state=None, ttl=None):
        """占用 target；同一 slot 原先占的自动放掉。state 给定时我离开这个状态就失效，ttl 给定时这么多 tick 后失效。"""
        old = self._held.get((me, slot))
        if old is not None:
            self._drop(old)
        prev = self._valid(target)
        if prev is not None and prev.owner is not me:
            self._drop(prev)
        c = Claim(me, slot, target, state, self.now, None if ttl is None else self.now + ttl)
        self._claims[id(target)] = c
        self._held[(me, slot)] = c

    def release(self, me, slot):
        c = self._held.get((me, slot))
        if c is not None:
            self._drop(c)

    def held(self, me, slot):
        """me 在 slot 上占着且仍有效的目标；没有 None。"""
        c = self._held.get((me, slot))
        return c.target if c is not None and self._valid(c.target) is c else None

    def floor_spans(self, me):
        """同一层地面上别的猫占的 [(左, 右)]：趴着的、正要趴下的、预约了挨着睡的位置。"""
        out = []
        for o in self.others(me):
            ob = o.body
            if not me.body.same_floor(ob):
                continue
            reach = SETTLING_REACH * ob.chunk1.rad
            span = ob.lying_span()
            if span is None and self.state_of(o) in LYING:
                span = (ob.chunk1.x - reach, ob.chunk1.x + reach)
            if span is not None:
                out.append(span)
            m = self.held(o, "huddle")
            if m is not None:
                out.append((m.x - reach, m.x + reach))
        return out

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
