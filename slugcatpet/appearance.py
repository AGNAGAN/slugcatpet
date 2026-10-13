"""一只猫的外观：皮肤、颜色、配件，以及取色优先级。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .skins.loader import parse_color

# 「自定颜色」接管的皮肤部位组（体色 / 脸色染的那些）
BODY_GROUPS = frozenset({"HEAD", "FACE", "BODY", "HIPS", "ARMS", "LEGS", "TAIL"})


def _hex(c) -> str:
    return "#%02X%02X%02X" % tuple(c)


@dataclass
class Look:
    skin: str | None = None  # 皮肤 id，None=原皮
    colors: dict | None = None  # {"body": rgb, "face": rgb}，None=默认颜色
    accessories: dict = field(default_factory=dict)  # key → {"on": bool, "color": rgb | None}

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
        return out or None

    def copy(self) -> Look:
        return Look(
            self.skin,
            dict(self.colors) if self.colors else None,
            {k: dict(v) for k, v in self.accessories.items()},
        )

    def wears(self, acc_cls, species: str) -> bool:
        e = self.accessories.get(acc_cls.key, {})
        return e["on"] if "on" in e else species in acc_cls.default_on

    def acc_color(self, key: str):
        return self.accessories.get(key, {}).get("color")


def base_colors(look: Look, cat, skin_colors: dict) -> tuple:
    """(体色, 脸色, 部位组色)：自定颜色 → 皮肤颜色 → 猫种默认；寒冷由绘制层最后叠加。"""
    if look is not None and look.colors:
        groups = {k: v for k, v in skin_colors.items() if k not in BODY_GROUPS}
        return tuple(look.colors["body"]), tuple(look.colors["face"]), groups
    return tuple(cat.body_color), tuple(cat.eye_color), dict(skin_colors)


def accessory_color(acc, groups: dict) -> tuple:
    if acc.color is not None:
        return acc.color
    if acc.color_group is not None and acc.color_group in groups:
        return groups[acc.color_group]
    return acc.default_color
