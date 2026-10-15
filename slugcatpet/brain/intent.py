"""意图选择：待机到点时按各行为的效用 softmax 随机挑一件事做。"""

from __future__ import annotations

import math

from .. import tuning


def smooth(a, b, x):
    """x 从 a 到 b 平滑地由 0 升到 1。"""
    if a == b:
        return 1.0 if x >= a else 0.0
    t = (x - a) / (b - a)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)


class _Intent:
    __slots__ = ("name", "utility", "start")

    def __init__(self, name, utility, start):
        self.name = name
        self.utility = utility  # 效用，≤0 不参加
        self.start = start  # 开始做，返回是否进入了别的状态


class IntentPicker:
    def __init__(self, rng):
        self.rng = rng
        self._intents = []
        self.last = None  # 上次挑中的意图名

    def add(self, name, utility, start):
        self._intents.append(_Intent(name, utility, start))

    def utilities(self):
        return {it.name: it.utility() for it in self._intents}

    def start(self, name):
        """直接开始名为 name 的意图，返回是否进入了别的状态。"""
        it = next((it for it in self._intents if it.name == name), None)
        if it is None:
            return False
        self.last = name
        return bool(it.start())

    def pick(self):
        """挑一个意图并开始，返回是否进入了别的状态。"""
        cands = [(it, it.utility()) for it in self._intents]
        cands = [(it, u) for it, u in cands if u > 0.0]
        if not cands:
            self.last = None
            return False
        top = max(u for _, u in cands)
        w = [math.exp((u - top) / tuning.INTENT_TEMP) for _, u in cands]
        r = self.rng.random() * sum(w)
        chosen = cands[-1][0]
        for (it, _), wi in zip(cands, w):
            r -= wi
            if r <= 0.0:
                chosen = it
                break
        self.last = chosen.name
        return bool(chosen.start())
