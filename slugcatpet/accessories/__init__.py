"""配件注册表：配件 key → Accessory 子类。"""

from __future__ import annotations

from .base import Accessory
from .gills import GillsAccessory
from .scar import ScarAccessory

# 顺序即挂载与绘制顺序
BUILTIN = (GillsAccessory, ScarAccessory)

REGISTRY: dict[str, type[Accessory]] = {cls.key: cls for cls in BUILTIN}

__all__ = ["Accessory", "BUILTIN", "REGISTRY"]
