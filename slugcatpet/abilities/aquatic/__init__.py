"""水生体质：潜泳冲刺、低水阻、浮泳拖臀。"""
from __future__ import annotations

from ..base import Ability


class AquaticAbility(Ability):
    key = "aquatic"
    title = {"zh": "水生", "en": "Aquatic"}
    doc = "水生体质（潜泳冲刺 / 低水阻 / 浮泳拖臀）。耗气倍率另见数值 lungs_fac。"

    def attach_body(self, pet, body):
        body.aquatic = True
