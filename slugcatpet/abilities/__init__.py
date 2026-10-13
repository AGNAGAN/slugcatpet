"""能力注册表：能力 key → Ability 子类。"""

from __future__ import annotations

from .acrobat import AcrobatAbility
from .aquatic import AquaticAbility
from .ascension import AscensionAbility
from .base import Ability, Param, resolve_params
from .pyro import PyroAbility
from .tongue import TongueAbility

# 顺序即挂载顺序
BUILTIN = (TongueAbility, AscensionAbility, PyroAbility, AcrobatAbility, AquaticAbility)

REGISTRY: dict[str, type[Ability]] = {cls.key: cls for cls in BUILTIN}


def validate(abilities: dict, where: str) -> None:
    for key, over in abilities.items():
        cls = REGISTRY.get(key)
        if cls is None:
            raise ValueError(f"{where}: 未知能力 {key!r}（可用：{', '.join(REGISTRY)}）")
        missing = [r for r in cls.requires if r not in abilities]
        if missing:
            raise ValueError(f"{where}: 能力 {key!r} 依赖 {', '.join(missing)}")
        resolve_params(cls.params, over, f"{where} 能力 {key}")


def instantiate(cat) -> dict[str, Ability]:
    """按注册顺序（非角色定义书写顺序）建能力实例。"""
    abilities = cat.abilities
    validate(abilities, f"角色 {cat.key!r}")
    return {
        cls.key: cls(resolve_params(cls.params, abilities[cls.key], f"{cat.key} 能力 {cls.key}"))
        for cls in BUILTIN
        if cls.key in abilities
    }


__all__ = ["Ability", "Param", "REGISTRY", "instantiate", "validate", "resolve_params"]
