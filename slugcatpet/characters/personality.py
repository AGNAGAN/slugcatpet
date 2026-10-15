"""性格：每种猫的性格数据（CatPersonality），以及它对行为的作用（Traits）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import tuning

DIET_OMNIVORE = "omnivore"
DIET_CARNIVORE = "carnivore"
DIET_VEGETARIAN = "vegetarian"
DIET_SPECIAL = "special"

MEAT_PREF = 0.6  # 肉食者选肉时的预估耗时乘子（越小越优先）


@dataclass(frozen=True)
class CatPersonality:
    activity: float = 0.5
    stamina: float = 1.0  # 体力消耗除以它，越低越容易累
    cold_gain_fac: float = 1.0
    sociability: float = 0.5
    swim_zeal: float = 0.5  # ≤0.5 视为中性
    diet: str = DIET_OMNIVORE
    meat: int = 0  # 啃尸体每口得几个 1/4 格，0 为不啃
    toy_pref: dict = field(default_factory=dict)


DEFAULT_PERSONALITY = CatPersonality()

# 性格轴 → 作用。加新轴：CatPersonality 加字段，Traits 里换算，这里登记
EFFECTS = (
    ("activity", "心情候选权重、玩耍体力门、东张西望和踱步频率"),
    ("toy_pref", "按心情名单独调权重"),
    ("stamina", "体力消耗"),
    ("cold_gain_fac", "暴风雪里变冷的速度"),
    ("sociability", "发呆走位：靠近或远离其他猫"),
    ("swim_zeal", "漂游最大深度、潜泳冲刺距离"),
    ("diet", "哪些可食物会去吃、肉的优先度、吃一样得多少饱食（肉食者 1/4 格）"),
    ("meat", "能不能啃尸体、每口得多少饱食"),
)


def is_meat(item) -> bool:
    return getattr(item, "is_meat", False)


def is_carcass(item) -> bool:
    return getattr(item, "carcass", False)


class Traits:
    def __init__(self, p: CatPersonality):
        act = p.activity
        self.activity = max(0.0, 1.0 + tuning.PERS_ACT_SPREAD * (act - 0.5))
        self.play_gate = max(
            tuning.PERS_GATE_FLOOR, tuning.PLAY_ENERGY_GATE - tuning.PERS_GATE_SPREAD * (act - 0.5)
        )
        self.drain = 1.0 / max(0.01, p.stamina)
        self.cold_gain = p.cold_gain_fac
        self.sociability = p.sociability
        self.swim_zeal = max(0.0, min(1.0, (p.swim_zeal - 0.5) * 2.0))
        self.diet = p.diet
        self.meat = p.meat
        self._toy = p.toy_pref

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
