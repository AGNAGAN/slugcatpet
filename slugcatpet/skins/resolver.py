"""每只猫的图集查找链：皮肤（按组）→ 原版。"""
from __future__ import annotations

from . import groups as G

SKIN_KEY = "skin"
_SIDES = {"L": "left", "R": "right"}


class SkinAtlasSet:

    def __init__(self, base, pack, species: str):
        self.base = base
        self.pack = pack
        self.species = species
        self._hit: dict[str, tuple | None] = {}

    @property
    def atlases(self):
        return self.base.atlases

    def get(self, key):
        return self.base.get(key)

    def find_atlas(self, frame: str):
        if self._lookup(frame) is not None:
            return SKIN_KEY
        return self.base.find_atlas(frame.split("|", 1)[-1])

    def sprite(self, key, frame, tint=None, padded=True):
        if key == SKIN_KEY:
            atlas, name = self._lookup(frame)
            return atlas.sprite(name, tint, padded)
        return self.base.sprite(key, frame.split("|", 1)[-1], tint, padded)

    def source_size(self, key, frame):
        if key == SKIN_KEY:
            atlas, name = self._lookup(frame)
            return atlas.source_size(name)
        return self.base.source_size(key, frame.split("|", 1)[-1])

    def sided(self, frame: str, side: str | None) -> str:
        if side is None or self.pack is None:
            return frame
        tok = f"{side}|{frame}"
        return tok if self._lookup(tok) is not None else frame

    def has_group(self, grp: str) -> bool:
        return self.pack is not None and grp in self.pack.groups

    @property
    def colors(self) -> dict:
        return {} if self.pack is None else dict(self.pack.colors)

    @property
    def tail(self) -> dict:
        return {} if self.pack is None else dict(self.pack.tail)

    @property
    def tail_asym(self) -> bool:
        return self.pack is not None and self.pack.tail_asym

    def _lookup(self, frame: str):
        try:
            return self._hit[frame]
        except KeyError:
            pass
        hit = None
        pack = self.pack
        if pack is not None:
            side, _, name = frame.rpartition("|")
            generic = G.generic_frame(name, self.species)
            grp = G.FRAME_GROUP.get(generic)
            if grp is not None and grp not in G.UNUSED_GROUPS:
                if side:
                    if grp in pack.asym_groups:
                        hit = getattr(pack, _SIDES[side]).get(generic)
                elif grp in pack.groups:
                    hit = pack.elements.get(generic)
        self._hit[frame] = hit
        return hit
