"""角色注册表：variant key → CatDef。"""
from __future__ import annotations

from .base import CatDef
from .loader import load_builtin

DEFAULT_VARIANT = "saint"
FALLBACK_VARIANT = "survivor"

REGISTRY: dict[str, CatDef] = load_builtin()


def get(variant) -> CatDef:
    d = REGISTRY.get(variant)
    return d if d is not None else REGISTRY[DEFAULT_VARIANT]


def all_variants() -> list[str]:
    return list(REGISTRY)


def default_def() -> CatDef:
    return REGISTRY[DEFAULT_VARIANT]
