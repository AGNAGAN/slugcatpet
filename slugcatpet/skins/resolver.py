"""每只猫的图集查找链：各部位的来源皮肤（按组）→ 原版。"""

from __future__ import annotations

from . import groups as G

SKIN_KEY = "skin"
_SIDES = {"L": "left", "R": "right"}


class SkinAtlasSet:
    def __init__(self, base, sources: dict, species: str, colors=None, tail=None):
        """sources：部位组 → SkinPack / None（原皮）/ HIDDEN（隐藏）。"""
        self.base = base
        self.sources = sources
        self.species = species
        self._colors = dict(colors or {})
        self._tail = dict(tail or {})
        self._hit: dict[str, tuple | None] = {}

    @property
    def atlases(self):
        return self.base.atlases

    def get(self, key):
        return self.base.get(key)

    def find_atlas(self, frame: str):
        if self._lookup(frame) is not None:
            return SKIN_KEY
        name = frame.split("|", 1)[-1]
        if self.hidden(G.FRAME_GROUP.get(G.generic_frame(name, self.species), "")):
            return None
        return self.base.find_atlas(name)

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
        if side is None:
            return frame
        tok = f"{side}|{frame}"
        return tok if self._lookup(tok) is not None else frame

    def has_group(self, grp: str) -> bool:
        pack = self.sources.get(grp)
        return pack is not None and pack is not HIDDEN and grp in pack.groups

    def hidden(self, grp: str) -> bool:
        return self.sources.get(grp) is HIDDEN

    @property
    def colors(self) -> dict:
        return dict(self._colors)

    @property
    def tail(self) -> dict:
        return dict(self._tail)

    @property
    def tail_asym(self) -> bool:
        return self.has_group("TAIL") and self.sources["TAIL"].tail_asym

    def _lookup(self, frame: str):
        try:
            return self._hit[frame]
        except KeyError:
            pass
        hit = None
        side, _, name = frame.rpartition("|")
        generic = G.generic_frame(name, self.species)
        grp = G.FRAME_GROUP.get(generic)
        if grp is not None and grp not in G.UNUSED_GROUPS and self.has_group(grp):
            pack = self.sources[grp]
            if side:
                if grp in pack.asym_groups:
                    hit = getattr(pack, _SIDES[side]).get(generic)
            else:
                hit = pack.elements.get(generic)
        self._hit[frame] = hit
        return hit


class _Hidden:
    def __repr__(self):
        return "HIDDEN"


HIDDEN = _Hidden()
