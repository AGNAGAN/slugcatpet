"""DMS 兼容部件组、物种帧名映射、锚点与约束上限。"""

from __future__ import annotations

import re


def _seq(prefix: str, n: int) -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


# 部件组 → 必需帧；组内帧必须齐全该组才生效
GROUPS: dict[str, list[str]] = {
    "HEAD": _seq("HeadA", 18),
    "FACE": _seq("FaceA", 9) + _seq("FaceB", 9) + ["FaceDead", "FaceStunned"],
    "BODY": ["BodyA"],
    "ARMS": _seq("PlayerArm", 13) + ["OnTopOfTerrainHand", "OnTopOfTerrainHand2"],
    "HIPS": ["HipsA"],
    "LEGS": (
        _seq("LegsA", 7)
        + ["LegsAAir0", "LegsAAir1"]
        + _seq("LegsAClimbing", 7)
        + _seq("LegsACrawling", 6)
        + _seq("LegsAOnPole", 7)
        + ["LegsAPole", "LegsAVerticalPole", "LegsAWall"]
    ),
    "TAIL": ["TailTexture"],
    "FACESCAR": ["MushroomA"],
    "GILLS": ["LizardScaleA3", "LizardScaleB3"],
    "TAILSPECKLES": ["tinyStar"],
    "ASCENSION": ["guardEye", "WormEye"],
    "PIXEL": ["pixel"],
}

# 桌宠不画的组：加载但标注"未使用"
UNUSED_GROUPS = frozenset({"PIXEL"})

FRAME_GROUP: dict[str, str] = {f: g for g, frames in GROUPS.items() for f in frames}

# 物种专属帧 → 皮肤里的通用帧
SPECIES_ALIASES: dict[str, dict[str, str]] = {
    "saint": {"HeadB": "HeadA"},
    "artificer": {"FaceC": "FaceA", "FaceD": "FaceB"},
}

_DIGITS = re.compile(r"^(.*?)(\d+)$")


def generic_frame(frame: str, species: str | None) -> str:
    """物种专属帧名换成皮肤通用帧名；无映射原样返回。"""
    aliases = SPECIES_ALIASES.get(species or "")
    if not aliases:
        return frame
    m = _DIGITS.match(frame)
    if m and m.group(1) in aliases:
        return aliases[m.group(1)] + m.group(2)
    return frame


# 归一化锚点（y↓）
_GROUP_ANCHOR = {"ARMS": (0.9, 0.5), "LEGS": (0.5, 0.75), "BODY": (0.5, 0.2105263), "GILLS": (0.5, 0.9)}
_FRAME_ANCHOR = {"OnTopOfTerrainHand": (0.5, 0.5), "OnTopOfTerrainHand2": (0.5, 0.5)}


def frame_anchor(frame: str) -> tuple[float, float]:
    a = _FRAME_ANCHOR.get(frame)
    if a is not None:
        return a
    return _GROUP_ANCHOR.get(FRAME_GROUP.get(frame, ""), (0.5, 0.5))


# 不对称前缀（如 LeftHeadA0 / RightHeadA0）
LEFT_PREFIX = "Left"
RIGHT_PREFIX = "Right"

MAX_ATLAS_SIDE = 4096  # 单张图集宽/高 px
MAX_PACK_BYTES = 32 * 1024 * 1024  # 单个皮肤目录全部 png 总大小
MAX_FRAMES = 1024  # 单个皮肤总帧数
MAX_EXTENT = 256.0  # 不透明像素离锚点最远距离（逻辑 px），超出则该组拒绝
MAX_ID_LEN = 100
MAX_NAME_LEN = 60
