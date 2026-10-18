"""性格：每种猫的性格数据（CatPersonality）、每只猫的个体性格，以及它们对行为的作用（Traits）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import tuning

DIET_OMNIVORE = "omnivore"
DIET_CARNIVORE = "carnivore"
DIET_VEGETARIAN = "vegetarian"
DIET_SPECIAL = "special"

MEAT_PREF = 0.6  # 肉食者选肉时的预估耗时乘子（越小越优先）

AXES = ("energy", "sympathy")  # 每只猫各自一份、可在性格弹窗里调的轴


@dataclass(frozen=True)
class CatPersonality:
    energy: float = 0.5
    sympathy: float = 0.5
    vary: float = 0.0  # 新猫的个体性格在默认值附近随机的幅度，1 为全范围
    stamina: float = 1.0  # 体力消耗除以它，越低越容易累
    cold_gain_fac: float = 1.0
    swim_zeal: float = 0.5  # ≤0.5 视为中性
    diet: str = DIET_OMNIVORE
    meat: int = 0  # 啃尸体每口得几个 1/4 格，0 为不啃
    toy_pref: dict = field(default_factory=dict)
    kin: dict = field(default_factory=dict)  # 猫种 key → 和这种猫的初始关系


DEFAULT_PERSONALITY = CatPersonality()

# 性格轴 → 作用。加新轴：CatPersonality 加字段，Traits 里换算，这里登记
EFFECTS = (
    ("energy", "心情候选权重、玩耍体力门、东张西望和踱步频率；懒的发呆更久、常趴着、更容易困"),
    ("sympathy", "发呆走位靠近或远离其他猫；好感涨跌快慢、舔光标前等多久；高的吃饱后不想打猎"),
    ("vary", "新猫的个体性格（energy、sympathy）在默认值附近随机的幅度"),
    ("toy_pref", "按心情名单独调权重"),
    ("stamina", "体力消耗"),
    ("cold_gain_fac", "暴风雪里变冷的速度"),
    ("swim_zeal", "漂游最大深度、潜泳冲刺距离"),
    ("diet", "哪些可食物会去吃、肉的优先度、吃一样得多少饱食（肉食者 1/4 格）"),
    ("meat", "能不能啃尸体、每口得多少饱食"),
    ("kin", "和哪种猫一见面就关系好"),
)


def push_from_half(v: float, k: float) -> float:
    """把 0–1 的值往两端推（原版 Custom.PushFromHalf）。"""
    if v < 0.5:
        return 0.5 * (v / 0.5) ** k
    if v > 0.5:
        return 1.0 - 0.5 * ((1.0 - v) / 0.5) ** k
    return 0.5


def default_axes(p: CatPersonality) -> dict:
    return {a: getattr(p, a) for a in AXES}


def roll_axes(p: CatPersonality, rng) -> dict:
    """新猫的个体性格：vary 为 0 时就是猫种默认，否则朝随机值偏 vary。"""
    out = default_axes(p)
    if p.vary <= 0.0:
        return out
    for a in AXES:
        r = push_from_half(rng.random(), tuning.PERS_ROLL_PUSH)
        out[a] = round(out[a] + (r - out[a]) * min(1.0, p.vary), 3)
    return out


def clean_axes(raw, p: CatPersonality):
    """存档里的个体性格：缺的轴用猫种默认，不是对象返回 None。"""
    if not isinstance(raw, dict):
        return None
    out = default_axes(p)
    for a in AXES:
        v = raw.get(a)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[a] = max(0.0, min(1.0, float(v)))
    return out


def lean(v: float) -> float:
    """轴值离中性带多远：中性带内 0，到 0 / 1 时 -1 / 1。"""
    lo, hi = tuning.PERS_NEUTRAL_LO, tuning.PERS_NEUTRAL_HI
    if v > hi:
        return (v - hi) / (1.0 - hi)
    if v < lo:
        return (v - lo) / lo
    return 0.0


def is_meat(item) -> bool:
    return getattr(item, "is_meat", False)


def is_carcass(item) -> bool:
    return getattr(item, "carcass", False)


class Traits:
    """性格换算出的作用，每只猫一个，改性格时原地更新。"""

    def __init__(self, p: CatPersonality, axes: dict | None = None):
        self.diet = p.diet
        self.meat = p.meat
        self.drain = 1.0 / max(0.01, p.stamina)
        self.cold_gain = p.cold_gain_fac
        self.swim_zeal = max(0.0, min(1.0, (p.swim_zeal - 0.5) * 2.0))
        self._toy = p.toy_pref
        self.apply(axes or default_axes(p))

    def apply(self, axes: dict):
        e = axes["energy"]
        self.energy = e
        self.activity = max(0.0, 1.0 + tuning.PERS_ACT_SPREAD * (e - 0.5))
        self.play_gate = max(
            tuning.PERS_GATE_FLOOR, tuning.PLAY_ENERGY_GATE - tuning.PERS_GATE_SPREAD * (e - 0.5)
        )
        lazy, lively = max(0.0, -lean(e)), max(0.0, lean(e))
        self.idle_hold = 1.0 + (tuning.PERS_IDLE_SLOW - 1.0) * lazy - (1.0 - tuning.PERS_IDLE_FAST) * lively
        self.lounge = tuning.PERS_LOUNGE_PROB * lazy
        self.sleepy = 1.0 + tuning.PERS_SLEEPY_GAIN * lazy
        s = axes["sympathy"]
        self.sympathy = s
        k = lean(s)
        self.temper_fac = (1.0 + tuning.PERS_TEMPER_SPREAD * k, 1.0 - tuning.PERS_TEMPER_SPREAD * k)
        self.lick_wait = 1.0 - tuning.PERS_LICK_SPREAD * k
        self.hunt_will = 1.0 - tuning.PERS_HUNT_SHY * max(0.0, k)

    def mood_weight(self, name) -> float:
        return self.activity * self._toy.get(name, 1.0)

    def eats(self, item) -> bool:
        if is_carcass(item):
            return self.meat > 0
        return not (is_meat(item) and self.diet in (DIET_VEGETARIAN, DIET_SPECIAL))

    def nourishment(self, item) -> int:
        """吃完 item 得几个 1/4 格：肉食者只得 food_points 个（carnivore_full 的除外），其余 4 × food_points 个。"""
        if is_carcass(item):
            return self.meat
        n = getattr(item, "food_points", 1)
        if self.diet == DIET_CARNIVORE and not getattr(item, "carnivore_full", False):
            return n
        return 4 * n

    def food_time(self, item, t: float) -> float:
        return t * MEAT_PREF if is_meat(item) and self.diet == DIET_CARNIVORE else t


NEUTRAL = Traits(DEFAULT_PERSONALITY)
