"""竖杆、横杆的几何；攀爬在 brain/skills/pole_climb.py。"""

from __future__ import annotations

from ..state import ItemState

VERTICAL = "vertical"
HORIZONTAL = "horizontal"

POLE_RAD = 2.0
MIN_LENGTH = 40.0
TOP_MARGIN = 48.0


class Pole:
    """一根杆：ax/ay 是贴边或着地的一端，bx/by 是放置时光标那端。"""

    __slots__ = ("kind", "ax", "ay", "bx", "by", "state", "has_been_climbed", "_id")
    grounded = True  # 竖杆底端着地

    def __init__(self, kind, ax, ay, bx, by, seed=0):
        self.kind = kind
        self.ax = float(ax)
        self.ay = float(ay)
        self.bx = float(bx)
        self.by = float(by)
        self.state = ItemState.FREE
        self.has_been_climbed = False
        self._id = int(seed)

    @property
    def x(self) -> float:
        return self.bx

    @property
    def top_y(self) -> float:
        return self.by

    def step(self, WL: float, HL: float) -> None:
        return
