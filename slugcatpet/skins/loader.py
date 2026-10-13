"""读取单个 DMS 皮肤目录为 SkinPack。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import t
from ..rendering.atlas import Atlas, load_json_lenient
from . import groups as G

META_FILE = "metadata.json"


@dataclass
class SkinPack:
    id: str
    name: str
    author: str
    path: Path
    source: str
    collection: str = ""  # 所属合集（mod 名 / 最外层文件夹），菜单分组用
    elements: dict = field(default_factory=dict)
    left: dict = field(default_factory=dict)
    right: dict = field(default_factory=dict)
    groups: set = field(default_factory=set)
    asym_groups: set = field(default_factory=set)
    missing: dict = field(default_factory=dict)  # 组 → 缺失帧（该组回退原版）
    rejected: set = field(default_factory=set)  # 图案越界被拒、回退原版的组
    colors: dict = field(default_factory=dict)  # 组 → (r,g,b)
    tail: dict = field(default_factory=dict)  # length/wideness/roundness/lift
    tail_asym: bool = False  # 尾巴贴图是三条横带（DMS 非对称尾巴）
    auto_white: set = field(default_factory=set)  # 画稿自带颜色、未指定颜色 → 按原图显示的组
    extent: float = 0.0  # 不透明像素离锚点最远距离
    warnings: list = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def parse_color(v) -> tuple[int, int, int] | None:
    """#RGB / #RRGGBB / #RRGGBBAA。"""
    if not isinstance(v, str):
        return None
    s = v.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) not in (6, 8):
        return None
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return None


def _str_field(meta: dict, key: str) -> str | None:
    for k, v in meta.items():
        if k.lower() == key and isinstance(v, str) and v.strip():
            return v.strip()
    return None


def load_pack(d: Path, source: str) -> SkinPack:
    pack = SkinPack(id="", name=d.name, author="", path=d, source=source)
    try:
        meta = load_json_lenient(d / META_FILE)
        if not isinstance(meta, dict):
            raise ValueError("not an object")
    except Exception as e:
        pack.error = t("skin_err_meta_parse", e=e)
        return pack
    pack.id = _str_field(meta, "id") or ""
    pack.name = _str_field(meta, "name") or d.name
    pack.author = _str_field(meta, "author") or ""
    missing = [k for k in ("id", "name", "author") if not _str_field(meta, k)]
    if missing:
        pack.error = t("skin_err_meta_fields", fields=", ".join(missing))
        return pack
    if len(pack.id) > G.MAX_ID_LEN or any(ord(c) < 32 for c in pack.id):
        pack.error = t("skin_err_id")
        return pack
    pack.name = pack.name[: G.MAX_NAME_LEN]
    _parse_defaults(pack, meta)

    pngs = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".png")
    total = sum(p.stat().st_size for p in pngs)
    if total > G.MAX_PACK_BYTES:
        pack.error = t("skin_err_pack_size", mb=total // (1024 * 1024), cap=G.MAX_PACK_BYTES // (1024 * 1024))
        return pack

    n_frames = 0
    for png in pngs:
        txt = png.with_suffix(".txt")
        if not txt.is_file():  # 没配 txt 的图不是图集，跳过
            continue
        try:
            atlas = Atlas("", d, image_path=png, data_path=txt)
        except Exception as e:
            pack.warnings.append(t("skin_warn_atlas_bad", file=png.name, e=e))
            continue
        w, h = atlas.image.width(), atlas.image.height()
        if w > G.MAX_ATLAS_SIDE or h > G.MAX_ATLAS_SIDE:
            pack.warnings.append(t("skin_warn_atlas_big", file=png.name, w=w, h=h, cap=G.MAX_ATLAS_SIDE))
            continue
        for key in atlas.frames:
            name = key[:-4] if key.endswith(".png") else key
            n_frames += 1
            if name.startswith(G.LEFT_PREFIX) and name[len(G.LEFT_PREFIX) :] in G.FRAME_GROUP:
                pack.left[name[len(G.LEFT_PREFIX) :]] = (atlas, name)
            elif name.startswith(G.RIGHT_PREFIX) and name[len(G.RIGHT_PREFIX) :] in G.FRAME_GROUP:
                pack.right[name[len(G.RIGHT_PREFIX) :]] = (atlas, name)
            else:
                pack.elements[name] = (atlas, name)
    if n_frames > G.MAX_FRAMES:
        pack.error = t("skin_err_frames", n=n_frames, cap=G.MAX_FRAMES)
        return pack

    _resolve_groups(pack)
    _check_tail(pack)
    _auto_colors(pack)
    if not pack.groups and not pack.colors and not pack.tail:
        pack.warnings.append(t("skin_warn_empty"))
    return pack


def _parse_defaults(pack: SkinPack, meta: dict) -> None:
    """metadata.defaults：{"BODY":{"color":"#fff"}, "TAIL":{"color":..,"length":..}}。"""
    defaults = next((v for k, v in meta.items() if k.lower() == "defaults"), None)
    if not isinstance(defaults, dict):
        return
    for grp, spec in defaults.items():
        if not isinstance(spec, dict):
            continue
        g = grp.upper()
        for k, v in spec.items():
            k = k.lower()
            if k == "color":
                c = parse_color(v)
                if c is None:
                    pack.warnings.append(t("skin_warn_color", group=g, v=v))
                else:
                    pack.colors[g] = c
            elif g == "TAIL" and k in ("length", "wideness", "roundness", "lift"):
                if isinstance(v, (int, float)) and math.isfinite(v):
                    pack.tail[k] = float(v)


def _resolve_groups(pack: SkinPack) -> None:
    images = {}
    for grp, frames in G.GROUPS.items():
        have = [f for f in frames if f in pack.elements]
        if not have:
            continue
        if len(have) < len(frames):
            pack.missing[grp] = [f for f in frames if f not in pack.elements]
            continue
        ext = max(_frame_extent(pack.elements[f][0], pack.elements[f][1], f, images) for f in frames)
        if ext > G.MAX_EXTENT:
            pack.warnings.append(t("skin_warn_extent", group=grp, ext=int(ext), cap=int(G.MAX_EXTENT)))
            pack.rejected.add(grp)
            continue
        pack.groups.add(grp)
        pack.extent = max(pack.extent, ext)
        if all(f in pack.left and f in pack.right for f in frames):
            ext_lr = max(
                _frame_extent(src[f][0], src[f][1], f, images)
                for src in (pack.left, pack.right)
                for f in frames
            )
            if ext_lr <= G.MAX_EXTENT:
                pack.asym_groups.add(grp)
                pack.extent = max(pack.extent, ext_lr)


# 尾巴设置的取值范围；超出则视为无效，不改形状
_TAIL_RANGE = {
    "length": (2.0, 15.0),
    "wideness": (0.1, 10.0),
    "roundness": (0.0, 1.5),
    "lift": (-100.0, 100.0),
}
# 整包彩色不透明像素占比超过此值 → 视为自带配色的画稿（原版贴图是白色靠染色）
_COLORED_FRAC = 0.05


def _check_tail(pack: SkinPack) -> None:
    if any(not (_TAIL_RANGE[k][0] <= v <= _TAIL_RANGE[k][1]) for k, v in pack.tail.items()):
        pack.tail = {}  # 同游戏：越界视为没设
    if "TAIL" in pack.groups:
        atlas, name = pack.elements["TailTexture"]
        e = atlas.frames[Atlas._key(name)]
        ss = e.get("sourceSize", e["frame"])
        pack.tail_asym = ss["h"] >= ss["w"]


def _auto_colors(pack: SkinPack) -> None:
    import numpy as np

    arrays = {}
    groups = pack.groups - G.UNUSED_GROUPS
    colored = total = 0
    for grp in groups:
        for f in G.GROUPS[grp]:
            atlas, name = pack.elements[f]
            arr = arrays.get(id(atlas))
            if arr is None:
                arr = arrays[id(atlas)] = np.asarray(_rgba_image(atlas))
            fr = atlas.frames[Atlas._key(name)]["frame"]
            px = arr[fr["y"] : fr["y"] + fr["h"], fr["x"] : fr["x"] + fr["w"]]
            px = px[px[..., 3] > 128][:, :3].astype(np.int16)
            hi, lo = px.max(axis=1), px.min(axis=1)
            total += len(px)
            colored += int(np.count_nonzero(((hi - lo) * 4 > hi) & (hi > 40)))
    if total and colored / total > _COLORED_FRAC:
        for grp in groups - set(pack.colors):
            pack.colors[grp] = (255, 255, 255)
            pack.auto_white.add(grp)


def _frame_extent(atlas: Atlas, name: str, generic: str, images: dict) -> float:
    e = atlas.frames[Atlas._key(name)]
    fr = e["frame"]
    ss = e.get("sourceSize", {"w": fr["w"], "h": fr["h"]})
    sw, sh = ss["w"], ss["h"]
    ax, ay = G.frame_anchor(generic)
    px, py = ax * sw, ay * sh
    if e.get("rotated"):
        bbox = (0, 0, sw, sh)  # 旋转帧取保守画布范围
    else:
        alpha = images.get(id(atlas))
        if alpha is None:
            alpha = _alpha_image(atlas)
            images[id(atlas)] = alpha
        bb = alpha.crop((fr["x"], fr["y"], fr["x"] + fr["w"], fr["y"] + fr["h"])).getbbox()
        if bb is None:
            return 0.0
        off = e.get("spriteSourceSize", {"x": 0, "y": 0}) if e.get("trimmed") else {"x": 0, "y": 0}
        bbox = (bb[0] + off["x"], bb[1] + off["y"], bb[2] + off["x"], bb[3] + off["y"])
    return max(math.hypot(x - px, y - py) for x in (bbox[0], bbox[2]) for y in (bbox[1], bbox[3]))


def _rgba_image(atlas: Atlas):
    from PIL import Image
    from PySide6.QtGui import QImage

    img = atlas.image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    buf = bytes(img.constBits())[: img.bytesPerLine() * h]
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "RGBA", img.bytesPerLine(), 1)


def _alpha_image(atlas: Atlas):
    return _rgba_image(atlas).getchannel("A")
