"""物品注册表：顺序决定侧边栏按钮、推进与同层绘制的先后。"""

from __future__ import annotations

from .base import ItemKind
from .batfly import KIND as BATFLY
from .fruit import KIND as FRUIT
from .lamp import KIND as LAMP
from .pole import HPOLE, VPOLE
from .slimemold import KIND as SLIMEMOLD
from .spear import KIND as SPEAR
from .stone import KIND as STONE

# 新物品加在末尾，原有场景的推进和绘制顺序就不变
BUILTIN: tuple[ItemKind, ...] = (VPOLE, HPOLE, FRUIT, STONE, LAMP, SLIMEMOLD, BATFLY, SPEAR)

_BY_KEY = {k.key: k for k in BUILTIN}


def kinds() -> tuple[ItemKind, ...]:
    return BUILTIN


def get(key: str) -> ItemKind:
    return _BY_KEY[key]
