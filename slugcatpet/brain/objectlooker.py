"""东张西望：兴趣衰减换目标，偶尔谁也不看。"""

from __future__ import annotations
import math

from .. import tuning


class ObjectLooker:
    def __init__(self, rng, traits=None):
        self.rng = rng
        self.traits = traits  # 东张西望频率乘 traits.activity
        self.mode = "nothing"  # "cursor"、物体或 "nothing"
        self.time_looking = 0

    def _how_interesting(self, head, pt, base, vel):
        dx, dy = pt[0] - head[0], pt[1] - head[1]
        dist = math.hypot(dx, dy)
        interest = base
        if dist < tuning.LOOK_DIST_NEAR:
            interest *= 0.5 * vel + 1.5
        denom = 0.005 * (dist**1.5) + 0.995
        return interest / denom

    def _current_interest(self, head, candidates):
        for key, pt, base, vel in candidates:
            if key == self.mode:
                return self._how_interesting(head, pt, base, vel)
        return 0.0

    def _look_at_nothing(self):
        self.mode = "nothing"
        self.time_looking = 0

    def update(self, head, candidates):
        if self.mode != "nothing" and not any(c[0] == self.mode for c in candidates):
            self._look_at_nothing()
        act = 1.0 if self.traits is None else self.traits.activity
        if self.rng.random() < tuning.LOOK_UPDATE_PROB * act:
            self._reconsider(head, candidates)
        if self.rng.random() < tuning.LOOK_NOTHING_PROB:
            self._look_at_nothing()
        return self.look_point(candidates)

    def _reconsider(self, head, candidates):
        """看够了就换更有意思的目标；time_looking 按评估次数计。"""
        self.time_looking += 1
        if self.time_looking > 1:
            bonus = 0.5 if self.time_looking < tuning.LOOK_INTEREST_DECAY_UPDATES else -0.5
            best = self._current_interest(head, candidates) + bonus
            for key, pt, base, vel in candidates:
                hi = self._how_interesting(head, pt, base, vel)
                if hi > best:
                    best = hi
                    self.mode = key
                    self.time_looking = 0
            if best < tuning.LOOK_MIN_INTEREST and self.rng.random() < 0.5:
                self._look_at_nothing()

    def look_point(self, candidates):
        for key, pt, base, vel in candidates:
            if key == self.mode:
                return pt
        return None
