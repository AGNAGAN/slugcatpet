"""超度：业力满时悬浮升空并放出幽灵触手全屏特效。"""

from __future__ import annotations

from ..base import Ability


class AscensionAbility(Ability):
    key = "ascension"
    title = {"zh": "超度", "en": "Ascension"}
    doc = "业力满时可超度：悬浮升空 + 全屏幽灵触手特效（何时触发见行为 ascend）。"
