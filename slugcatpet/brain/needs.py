"""饿的效用：睡前要吃够和顺手吃。"""

from __future__ import annotations

from .. import tuning
from .intent import smooth


def bedtime_hunger(body):
    """食物不够冬眠时越困越想吃。"""
    if body.food >= body.food_hibernate:
        return 0.0
    return tuning.EAT_BED_UTIL * smooth(tuning.EAT_BED_LO, tuning.EAT_BED_HI, body.sleepiness)


def snack_appeal(body, value):
    """顺手吃一个；value 为这东西值几格（0–1）。"""
    if body.food >= body.food_max:
        return 0.0
    return tuning.EAT_OPP_UTIL * (1.0 - body.food / body.food_max) * (0.4 + 0.6 * min(1.0, value))


def hunger(body, value):
    return max(bedtime_hunger(body), snack_appeal(body, value))
