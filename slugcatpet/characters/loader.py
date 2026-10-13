"""读取内置角色定义（resources/characters/*.json），格式错误直接报错。"""

from __future__ import annotations

import json
import re
from dataclasses import fields, replace
from pathlib import Path

from .._paths import resource_dir
from .base import CatDef
from .personality import DEFAULT_PERSONALITY
from .stats import DEFAULT_STATS

FORMAT = 1
CHAR_DIR = resource_dir() / "characters"
_KEYS = {
    "format",
    "key",
    "order",
    "notes",
    "name",
    "body_color",
    "eye_color",
    "layout",
    "atlases",
    "frames",
    "tail_rad",
    "abilities",
    "behaviors",
    "stats",
    "personality",
    "wip",
}
_REQUIRED = ("key", "body_color", "eye_color", "layout", "atlases", "frames")
# 语义帧名：必填 / 可选
FRAMES_REQUIRED = ("head", "face", "face_blink", "legs_walk", "legs_crawl", "legs_air")
FRAMES_OPTIONAL = ("face_open", "face_mirror")
_HEX = re.compile(r"^#([0-9a-fA-F]{6})$")


def _color(v, where):
    m = _HEX.match(v) if isinstance(v, str) else None
    if m is None:
        raise ValueError(f"{where}: 颜色应写成 #RRGGBB，得到 {v!r}")
    n = int(m.group(1), 16)
    return (n >> 16 & 255, n >> 8 & 255, n & 255)


def _override(base, data, where):
    """按 dataclass 字段覆盖；未知字段 / 类型不符报错，int 可写给 float 字段。"""
    if not isinstance(data, dict):
        raise ValueError(f"{where}: 应为对象")
    known = {f.name: getattr(base, f.name) for f in fields(base)}
    kw = {}
    for k, v in data.items():
        if k not in known:
            raise ValueError(f"{where}: 未知字段 {k!r}")
        d = known[k]
        if isinstance(d, bool):
            ok = isinstance(v, bool)
        elif isinstance(d, float):
            ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            v = float(v) if ok else v
        elif isinstance(d, int) or d is None:
            ok = v is None or (isinstance(v, int) and not isinstance(v, bool))
        else:
            ok = isinstance(v, type(d))
        if not ok:
            raise ValueError(f"{where}: 字段 {k!r} 类型应同默认值 {d!r}，得到 {v!r}")
        kw[k] = v
    return replace(base, **kw)


def load_character(path: Path) -> tuple[int, CatDef]:
    where = path.name
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{where}: 根应为对象")
    unknown = set(data) - _KEYS
    if unknown:
        raise ValueError(f"{where}: 未知字段 {', '.join(sorted(unknown))}")
    missing = [k for k in _REQUIRED if k not in data]
    if missing:
        raise ValueError(f"{where}: 缺少字段 {', '.join(missing)}")
    if data.get("format", FORMAT) != FORMAT:
        raise ValueError(f"{where}: format 应为 {FORMAT}")
    frames = {}
    for name, ref in data["frames"].items():
        atlas, sep, frame = ref.partition("/") if isinstance(ref, str) else ("", "", "")
        if not (sep and atlas and frame):
            raise ValueError(f'{where}: frames.{name} 应写成 "图集/帧名"，得到 {ref!r}')
        frames[name] = (atlas, frame)
    bad = [n for n in frames if n not in FRAMES_REQUIRED + FRAMES_OPTIONAL]
    lack = [n for n in FRAMES_REQUIRED if n not in frames]
    if bad or lack:
        raise ValueError(f"{where}: frames 未知 {bad} / 缺少 {lack}")
    tail_rad = data.get("tail_rad", [])
    if not isinstance(tail_rad, list) or not (
        tail_rad == []
        or (
            2 <= len(tail_rad) <= 15
            and all(isinstance(r, (int, float)) and not isinstance(r, bool) and r > 0 for r in tail_rad)
        )
    ):
        raise ValueError(f"{where}: tail_rad 应为 2–15 个正数（尾巴每段半径），得到 {tail_rad!r}")
    abilities = data.get("abilities", {})
    behaviors = data.get("behaviors", {})
    if not isinstance(abilities, dict) or not all(isinstance(v, dict) for v in abilities.values()):
        raise ValueError(f"{where}: abilities 应为 {{能力: {{参数}}}}")
    if not isinstance(behaviors, dict) or not all(
        v is False or isinstance(v, dict) for v in behaviors.values()
    ):
        raise ValueError(f"{where}: behaviors 应为 {{行为: {{参数}} 或 false}}")
    names = data.get("name")
    if isinstance(names, str):
        names = {"zh": names, "en": names}
    if names is not None and not (
        isinstance(names, dict) and names and all(isinstance(v, str) for v in names.values())
    ):
        raise ValueError(f'{where}: name 应为字符串或 {{"zh": ..., "en": ...}}')
    cat = CatDef(
        key=data["key"],
        body_color=_color(data["body_color"], f"{where} body_color"),
        eye_color=_color(data["eye_color"], f"{where} eye_color"),
        frames=frames,
        layout_file=data["layout"],
        atlas_keys=tuple(data["atlases"]),
        tail_rad=tuple(float(r) for r in tail_rad),
        abilities=abilities,
        behaviors=behaviors,
        stats=_override(DEFAULT_STATS, data.get("stats", {}), f"{where} stats"),
        personality=_override(DEFAULT_PERSONALITY, data.get("personality", {}), f"{where} personality"),
        wip=bool(data.get("wip", False)),
        names=names,
    )
    return int(data.get("order", 1000)), cat


def load_builtin(char_dir: Path = CHAR_DIR) -> dict[str, CatDef]:
    loaded = [load_character(p) for p in sorted(char_dir.glob("*.json"))]
    loaded.sort(key=lambda oc: (oc[0], oc[1].key))
    out = {}
    for _, cat in loaded:
        if cat.key in out:
            raise ValueError(f"角色 key 重复：{cat.key!r}")
        out[cat.key] = cat
    return out
