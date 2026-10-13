"""行为（Behavior）基类。"""
from __future__ import annotations

from types import SimpleNamespace

from ..abilities.base import Param
from ..brain.desire import Candidate
from ..items.base import USES


def mood_params(base, start, quit, init, decay, recover, **extra):
    out = {
        "mood_base": Param(base, 0.0, 10.0, "心情基础权重（再乘性格权重 Traits.mood_weight）"),
        "mood_start": Param(start, 0.0, 1.0, "新鲜度回升过此值才会被选中"),
        "mood_quit": Param(quit, 0.0, 1.0, "持续型心情：新鲜度降到此值就收工"),
        "mood_init": Param(init, 0.0, 1.0, "出生时的新鲜度"),
        "mood_decay": Param(decay, 0.0, 1.0, "做这件事时每 tick 新鲜度下降量"),
        "mood_recover": Param(recover, 0.0, 1.0, "不做时每 tick 新鲜度回升量"),
    }
    out.update(extra)
    return out


def _one(_):
    return 1.0


def mood_candidate(fsm, name, p, gate, one_shot=True, energy_factor=_one, before=None):
    fsm.mood.add(Candidate(
        name, base=p.mood_base * fsm.traits.mood_weight(name),
        start=p.mood_start, quit=p.mood_quit,
        decay=p.mood_decay, recover=p.mood_recover,
        gate=gate, energy_factor=energy_factor, temper_factor=_one,
        one_shot=one_shot, init=p.mood_init), before=before)


class Behavior:
    key = ""                 # 注册键，角色定义 behaviors 里用它
    title = {"zh": "", "en": ""}
    doc = ""
    requires = ()            # 依赖的能力 key 或物品用法；能力不齐不挂载，用法只标明会用到哪类物品
    essential = False        # 状态机离不开它，角色里不能关
    mood = None              # 心情候选名（性格按它调权重），无则 None
    params: dict = {}

    def __init__(self, p: SimpleNamespace):
        self.p = p

    def mount(self, fsm):
        raise NotImplementedError


def needed_abilities(cls) -> list[str]:
    return [r for r in cls.requires if r not in USES]
