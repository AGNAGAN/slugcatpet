"""心情抽签：freshness 带滞回地控制冷却，在合格的候选里按权重随机抽。"""

from __future__ import annotations

from .. import tuning


def _lerp(x, lo, hi, flo, fhi):
    if hi == lo:
        return flo
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return flo + (fhi - flo) * t


class MoodContext:
    __slots__ = ("energy", "temper", "cold", "submerged")

    def __init__(self, energy, temper, cold=0.0, submerged=False):
        self.energy = energy
        self.temper = temper
        self.cold = cold
        self.submerged = submerged


def _one(_):
    return 1.0


class Candidate:
    __slots__ = (
        "name",
        "base",
        "start",
        "quit",
        "decay",
        "recover",
        "gate",
        "energy_factor",
        "temper_factor",
        "cold_factor",
        "scale",
        "one_shot",
        "freshness",
    )

    def __init__(
        self,
        name,
        base,
        start,
        quit,
        decay,
        recover,
        gate,
        energy_factor,
        temper_factor,
        one_shot,
        init=1.0,
        cold_factor=None,
        scale=None,
    ):
        self.name = name
        self.base = base
        self.start = start
        self.quit = quit
        self.decay = decay
        self.recover = recover
        self.gate = gate
        self.energy_factor = energy_factor
        self.temper_factor = temper_factor
        self.cold_factor = cold_factor if cold_factor is not None else _one
        self.scale = scale  # 每次抽签时再乘的权重 fn()，跟着性格变
        self.one_shot = one_shot  # True 由状态自己结束，False 在 freshness 降到 quit 时退出
        self.freshness = init

    def weight(self, ctx, noise):
        base = self.base if self.scale is None else self.base * self.scale()
        return max(
            0.0,
            base
            * self.energy_factor(ctx.energy)
            * self.temper_factor(ctx.temper)
            * self.cold_factor(ctx.cold)
            + noise,
        )


class MoodArbiter:
    def __init__(self, rng, noise_amp):
        self.rng = rng
        self.noise_amp = noise_amp
        self.candidates = {}
        self.order = []

    def add(self, cand, before=None):
        """加入候选，插到 before 之前，没有就排最后。"""
        self.candidates[cand.name] = cand
        i = next((i for i, c in enumerate(self.order) if c.name == before), None)
        if i is None:
            self.order.append(cand)
        else:
            self.order.insert(i, cand)

    def tick_freshness(self, active_name):
        for c in self.order:
            if c.name == active_name:
                c.freshness = max(0.0, c.freshness - c.decay)
            else:
                c.freshness = min(1.0, c.freshness + c.recover)

    def should_quit(self, active_name):
        c = self.candidates.get(active_name)
        if c is None or c.one_shot:
            return False
        return c.freshness <= c.quit

    def eligible(self, ctx):
        return [c for c in self.order if c.gate(ctx) and c.freshness >= c.start]

    def select(self, ctx):
        elig = self.eligible(ctx)
        if not elig:
            return None
        weights = [c.weight(ctx, self.rng.uniform(0.0, self.noise_amp)) for c in elig]
        total = sum(weights)
        if total <= 0.0:
            return None
        r = self.rng.random() * total
        acc = 0.0
        for c, w in zip(elig, weights):
            acc += w
            if r <= acc:
                return c.name
        return elig[-1].name


def build_arbiter(rng):
    return MoodArbiter(rng, tuning.MOOD_NOISE_AMP)
