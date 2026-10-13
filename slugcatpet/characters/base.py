"""CatDef：猫种族的静态定义。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .personality import CatPersonality, DEFAULT_PERSONALITY
from .stats import SlugStats, DEFAULT_STATS


@dataclass(frozen=True)
class CatDef:
    key: str
    body_color: tuple[int, int, int]
    eye_color: tuple[int, int, int]
    frames: dict[str, tuple[str, str]]
    layout_file: str
    atlas_keys: tuple[str, ...]
    abilities: dict = field(default_factory=dict)
    behaviors: dict = field(default_factory=dict)
    stats: SlugStats = DEFAULT_STATS
    personality: CatPersonality = DEFAULT_PERSONALITY
    wip: bool = True
    names: dict | None = None  # {"zh":..., "en":...} 显示名，None=用 i18n
