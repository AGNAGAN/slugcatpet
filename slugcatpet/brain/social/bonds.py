"""猫际关系：每对猫一个亲疏值（-1 到 1），相处时看双方亲和慢慢变好或变差，分享、被顶、被误伤时变化，平时慢慢回到初始值。"""

from __future__ import annotations

import math

from ... import tuning

LYING = ("LieDown", "Sleep")


def _key(a, b):
    return (a.id, b.id) if a.id < b.id else (b.id, a.id)


def kin(a, b) -> float:
    """两种猫的初始关系：双方猫种 kin 里写了的取平均，都没写为 0。"""
    pair = (a.cat.personality.kin.get(b.variant), b.cat.personality.kin.get(a.variant))
    vals = [v for v in pair if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


class Bonds:
    def __init__(self, social):
        self.social = social
        self._v = {}  # (id, id) → 值，没记的按初始关系
        self._t = 0

    def get(self, a, b) -> float:
        return self._v.get(_key(a, b), kin(a, b))

    def nudge(self, a, b, d):
        if a is b:
            return
        self._v[_key(a, b)] = max(-1.0, min(1.0, self.get(a, b) + d))

    def drop(self, pet):
        """移除一只猫时清掉它的所有关系。"""
        self._v = {k: v for k, v in self._v.items() if pet.id not in k}

    def tick(self):
        """每 BOND_TICK 结算一次：离得近的按双方亲和变好或变差（一起趴着变好更快），都慢慢回到初始值。"""
        self._t += 1
        if self._t < tuning.BOND_TICK:
            return
        self._t = 0
        pets = [p for p in self.social.win.pets if getattr(p, "body", None) is not None]
        for i, a in enumerate(pets):
            for b in pets[i + 1 :]:
                v = self.get(a, b)
                base = kin(a, b)
                v += (base - v) * tuning.BOND_RELAX
                if _near(a, b):
                    soc = self.social
                    warm = tuning.BOND_NEAR_BASE + (soc.affinity(a) + soc.affinity(b)) / 2
                    g = tuning.BOND_NEAR_GAIN * warm
                    if g > 0.0 and soc.state_of(a) in LYING and soc.state_of(b) in LYING:
                        g *= tuning.BOND_REST_MULT
                    v += g
                self._v[_key(a, b)] = max(-1.0, min(1.0, v))

    def load(self, raw, pets):
        """读存档 {"id|id": 值}，只留现有猫之间的。"""
        ids = {p.id for p in pets}
        self._v = {}
        if not isinstance(raw, dict):
            return
        for k, v in raw.items():
            a, sep, b = k.partition("|") if isinstance(k, str) else ("", "", "")
            if sep and a in ids and b in ids and a != b and isinstance(v, (int, float)):
                self._v[(a, b) if a < b else (b, a)] = max(-1.0, min(1.0, float(v)))

    def dump(self) -> dict:
        return {f"{a}|{b}": round(v, 4) for (a, b), v in self._v.items()}


def _near(a, b):
    if a.body.dead or b.body.dead:
        return False
    c, d = a.body.chunk0, b.body.chunk0
    return math.hypot(c.x - d.x, c.y - d.y) < tuning.BOND_NEAR
