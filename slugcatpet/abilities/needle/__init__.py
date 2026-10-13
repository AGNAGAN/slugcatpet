"""骨针：靠尾巴上长出的骨针扎中食物进食，没有能吃东西的嘴。"""

from __future__ import annotations

from ..base import MOUTH, Ability


class NeedleAbility(Ability):
    key = "needle"
    title = {"zh": "骨针", "en": "Needles"}
    doc = "不能用嘴吃东西；进食靠骨针扎中食物。"
    removes = (MOUTH,)
