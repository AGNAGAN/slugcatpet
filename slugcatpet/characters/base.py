"""CatDef：猫种族的静态定义。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .personality import CatPersonality, DEFAULT_PERSONALITY
from .stats import SlugStats, DEFAULT_STATS

PUP_HEAD = ("msc", "HeadC")
PUP_FACE = ("msc", "PFaceA")
PUP_FACE_CLOSED = ("msc", "PFaceB")


@dataclass(frozen=True)
class CatDef:
    key: str
    body_color: tuple[int, int, int]
    eye_color: tuple[int, int, int]
    frames: dict[str, tuple[str, str]]
    layout_file: str
    atlas_keys: tuple[str, ...]
    tail_rad: tuple[float, ...] = ()  # 原皮尾巴每段半径，空则用游戏默认
    abilities: dict = field(default_factory=dict)
    behaviors: dict = field(default_factory=dict)
    stats: SlugStats = DEFAULT_STATS
    personality: CatPersonality = DEFAULT_PERSONALITY
    wip: bool = True
    pup: bool = False
    names: dict | None = None  # 显示名 {"zh": ..., "en": ...}，None 时用 i18n

    def frames_for(self, pup: bool) -> dict[str, tuple[str, str]]:
        """幼崽形态换成原版幼崽的头和脸，睁眼 / 闭眼按原来的脸对应。"""
        if not pup:
            return self.frames
        out = dict(self.frames)
        out["head"] = PUP_HEAD
        out.pop("face_mirror", None)
        for k in ("face", "face_blink", "face_open"):
            if k in out:
                out[k] = PUP_FACE_CLOSED if out[k][1][-1] in "BD" else PUP_FACE
        return out

    def is_pup(self, look) -> bool:
        """猫种本身是幼崽，或外观选了幼崽形态。"""
        return self.pup or bool(look and look.pup)
