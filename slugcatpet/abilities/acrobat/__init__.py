"""高后空翻：给规划器加一种加强后空翻够取方式。"""

from __future__ import annotations

from ...planning.backflip_reach import BackflipReach
from ..base import Ability


class AcrobatAbility(Ability):
    key = "acrobat"
    title = {"zh": "高后空翻", "en": "Acrobat"}
    doc = "规划器可用加强后空翻够取高处目标；行为后空翻上横杆 / 后空翻劫持光标随之挂载。"

    def reaches(self, pet):
        return [BackflipReach(pet)]
