"""一只猫的外观：皮肤、颜色、配件，以及取色优先级。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .skins.loader import parse_color

# 「自定颜色」接管的皮肤部位组（体色 / 脸色染的那些）
BODY_GROUPS = frozenset({"HEAD", "FACE", "BODY", "HIPS", "ARMS", "LEGS", "TAIL"})
# 外观面板里可单独换包的身体部位，按显示顺序
PART_GROUPS = ("HEAD", "FACE", "BODY", "ARMS", "HIPS", "LEGS", "TAIL")
EMPTY = "__empty__"  # 部位来源：隐藏该部位
TAIL_KEYS = ("length", "wideness", "roundness")


def _hex(c) -> str:
    return "#%02X%02X%02X" % tuple(c)


@dataclass
class Look:
    skin: str | None = None  # 皮肤 id，None=原皮
    colors: dict | None = None  # {"body": rgb, "face": rgb}，None=默认颜色
    accessories: dict = field(default_factory=dict)  # key → {"on": bool, "color": rgb | None}
    parts: dict = field(default_factory=dict)  # 部位组 → 皮肤 id（""=原皮，EMPTY=隐藏），覆盖整套
    part_colors: dict = field(default_factory=dict)  # 部位组 → rgb
    tail: dict | None = None  # 自定尾巴形状 {length, wideness, roundness}，None=跟随皮肤

    @classmethod
    def from_state(cls, state: dict) -> Look:
        """读存档里的一只猫；兼容只有 skin 字段的旧存档。"""
        raw = state.get("look")
        if not isinstance(raw, dict):
            raw = {"skin": state.get("skin")}
        skin = raw.get("skin")
        look = cls(skin=skin if isinstance(skin, str) and skin else None)
        cols = raw.get("colors")
        if isinstance(cols, dict):
            parsed = {k: parse_color(cols.get(k)) for k in ("body", "face")}
            if all(parsed.values()):
                look.colors = parsed
        accs = raw.get("accessories")
        if isinstance(accs, dict):
            for key, v in accs.items():
                if not isinstance(v, dict):
                    continue
                entry = {}
                if isinstance(v.get("on"), bool):
                    entry["on"] = v["on"]
                c = parse_color(v.get("color"))
                if c is not None:
                    entry["color"] = c
                if entry:
                    look.accessories[str(key)] = entry
        parts = raw.get("parts")
        if isinstance(parts, dict):
            look.parts = {str(g): v for g, v in parts.items() if isinstance(v, str)}
        pcols = raw.get("part_colors")
        if isinstance(pcols, dict):
            for g, v in pcols.items():
                c = parse_color(v)
                if c is not None:
                    look.part_colors[str(g)] = c
        tail = raw.get("tail")
        if isinstance(tail, dict) and all(isinstance(tail.get(k), (int, float)) for k in TAIL_KEYS):
            look.tail = {k: float(tail[k]) for k in TAIL_KEYS}
        return look

    def to_state(self) -> dict | None:
        """写存档；全是默认值时返回 None。"""
        out = {}
        if self.skin:
            out["skin"] = self.skin
        if self.colors:
            out["colors"] = {k: _hex(v) for k, v in self.colors.items()}
        accs = {}
        for key, e in self.accessories.items():
            d = {}
            if "on" in e:
                d["on"] = e["on"]
            if e.get("color") is not None:
                d["color"] = _hex(e["color"])
            if d:
                accs[key] = d
        if accs:
            out["accessories"] = accs
        if self.parts:
            out["parts"] = dict(self.parts)
        if self.part_colors:
            out["part_colors"] = {g: _hex(c) for g, c in self.part_colors.items()}
        if self.tail:
            out["tail"] = dict(self.tail)
        return out or None

    def copy(self) -> Look:
        return Look(
            self.skin,
            dict(self.colors) if self.colors else None,
            {k: dict(v) for k, v in self.accessories.items()},
            dict(self.parts),
            dict(self.part_colors),
            dict(self.tail) if self.tail else None,
        )

    def wears(self, acc_cls, species: str) -> bool:
        e = self.accessories.get(acc_cls.key, {})
        return e["on"] if "on" in e else species in acc_cls.default_on

    def acc_color(self, key: str):
        return self.accessories.get(key, {}).get("color")

    def source(self, grp: str) -> str:
        """该部位取图的皮肤 id：部位覆盖 → 整套；""=原皮。"""
        return self.parts.get(grp, self.skin or "")

    def set_skin(self, skin_id: str | None, groups) -> None:
        """换整套：这些部位回到整套，部位颜色和自定尾巴交给皮肤默认。"""
        self.skin = skin_id or None
        for g in groups:
            self.parts.pop(g, None)
            self.part_colors.pop(g, None)
        self.tail = None


def shown_source(skin_id: str, grp: str, get_pack) -> str:
    """实际画出来的来源：皮肤缺这个部位或找不到时按原皮算。"""
    if not skin_id or skin_id == EMPTY:
        return skin_id
    pack = get_pack(skin_id)
    return skin_id if pack is not None and grp in pack.groups else ""


def whole_set(look: Look, groups, get_pack) -> str | None:
    """各部位实际效果等同于哪个整套（""=原皮）；不是任何一套则 None（混搭）。"""
    cands = [look.skin or ""] + [v for v in look.parts.values() if v != EMPTY]
    for cand in dict.fromkeys(cands):
        if all(shown_source(look.source(g), g, get_pack) == shown_source(cand, g, get_pack) for g in groups):
            return cand
    return None


def base_colors(look: Look, cat, skin_colors: dict) -> tuple:
    """(体色, 脸色, 部位组色)：部位颜色 → 自定颜色 → 皮肤颜色 → 猫种默认；寒冷由绘制层最后叠加。"""
    if look is not None and look.colors:
        groups = {k: v for k, v in skin_colors.items() if k not in BODY_GROUPS}
        body, face = tuple(look.colors["body"]), tuple(look.colors["face"])
    else:
        groups = dict(skin_colors)
        body, face = tuple(cat.body_color), tuple(cat.eye_color)
    if look is not None:
        groups.update({g: tuple(c) for g, c in look.part_colors.items()})
    return body, face, groups


def accessory_color(acc, groups: dict) -> tuple:
    if acc.color is not None:
        return acc.color
    if acc.color_group is not None and acc.color_group in groups:
        return groups[acc.color_group]
    return acc.default_color
