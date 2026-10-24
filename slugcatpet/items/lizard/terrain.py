"""蜥蜴的房间格子：实心判定、AItile 可达性分类、竖 / 横杆格。

房间坐标 y↑、地面线 y=0，格 20px。格中心落在 [0,WL]x[0,HL] 之外的格是实心。
内部另存一圈实心外环（原版房间边缘就是实心格，AImapper 的循环边界依赖它），
对外的格坐标 (tx, ty) 不含外环。
"""

from __future__ import annotations

import math

from ..state import ItemState
from .breeds import (
    ACC_INDEX,
    ACC_NAMES,
    AIR,
    CEILING,
    CLIMB,
    CORRIDOR,
    CURVED_FLOOR,
    FLOOR,
    OFFSCREEN,
    SAND,
    SOLID,
    WALL,
    LizardBreedParams,
)
from .rw import V2

__all__ = [
    "TILE",
    "SOLID",
    "AIR",
    "FLOOR",
    "CORRIDOR",
    "CLIMB",
    "WALL",
    "CEILING",
    "OFFSCREEN",
    "CURVED_FLOOR",
    "SAND",
    "Terrain",
    "terrain_for",
    "to_room",
    "to_win",
]

TILE = 20.0
_EDGE = 8.0

_I_SOLID = ACC_INDEX[SOLID]
_I_AIR = ACC_INDEX[AIR]
_I_FLOOR = ACC_INDEX[FLOOR]
_I_CORRIDOR = ACC_INDEX[CORRIDOR]
_I_CLIMB = ACC_INDEX[CLIMB]
_I_WALL = ACC_INDEX[WALL]
_I_CEILING = ACC_INDEX[CEILING]

_VERTICAL = "vertical"
_HORIZONTAL = "horizontal"

_version_counter = 0


def to_room(x: float, y_win: float, HL: float) -> V2:
    return V2(x, HL - y_win)


def to_win(v: V2, HL: float) -> tuple[float, float]:
    return (v.x, HL - v.y)


class Terrain:
    """一个窗口大小下的格子世界。poles 是窗口坐标的 Pole 列表。"""

    def __init__(self, WL: float, HL: float, poles=()):
        global _version_counter
        _version_counter += 1
        self.version = _version_counter
        self.key = None
        self.WL = float(WL)
        self.HL = float(HL)
        self.cols = max(1, int((self.WL - TILE / 2) // TILE) + 1)
        self.rows = max(1, int((self.HL - TILE / 2) // TILE) + 1)
        self.W = self.cols + 2  # 含外环
        self.H = self.rows + 2
        self._vx: dict[tuple[int, int], float] = {}  # 竖杆格 -> 杆的真实 x
        self._hy: dict[tuple[int, int], float] = {}  # 横杆格 -> 杆的真实 y
        self._place_poles(poles)
        self._classify()
        self._find_passage_info()

    # 杆

    def _place_poles(self, poles) -> None:
        for p in poles:
            if getattr(p, "state", ItemState.FREE) != ItemState.FREE:
                continue
            if p.kind == _VERTICAL:
                x = p.bx
                top = self.HL - p.by
                tx = min(max(int(math.floor(x / TILE)), 0), self.cols - 1)
                ty = 0
                while ty < self.rows and ty * TILE + TILE / 2 <= top:
                    for c in self._near(x, tx, self.cols):
                        self._vx[(c, ty)] = x
                    ty += 1
            elif p.kind == _HORIZONTAL:
                y = self.HL - p.ay
                ty = min(max(int(math.floor(y / TILE)), 0), self.rows - 1)
                lo, hi = min(p.ax, p.bx), max(p.ax, p.bx)
                for tx in range(self.cols):
                    c = tx * TILE + TILE / 2
                    if lo <= c <= hi:
                        for r in self._near(y, ty, self.rows):
                            self._hy[(tx, r)] = y

    @staticmethod
    def _near(v: float, t: int, n: int) -> list[int]:
        """杆离所在格边界不足 8px 时,把相邻那一列/行也算上,避免贴杆的身体在两格间来回出杆。"""
        f = v - t * TILE
        out = [t]
        if f < _EDGE and t > 0:
            out.append(t - 1)
        elif TILE - f < _EDGE and t < n - 1:
            out.append(t + 1)
        return out

    # AImapper.FindAccessibilityOfCurrentTile

    def _solid_i(self, ix: int, iy: int) -> bool:
        """内部格坐标（含外环）的 Terrain==Solid；环外按实心。"""
        if ix < 0 or iy < 0 or ix >= self.W or iy >= self.H:
            return True
        return ix == 0 or iy == 0 or ix == self.W - 1 or iy == self.H - 1

    def _classify(self) -> None:
        """世界只有一圈实心外环加杆：距外环 2 格以上的格(上下左右邻格都不是外环)只可能是 Air / Climb，
        其余靠外环的格按原版条件逐格判。"""
        W, H = self.W, self.H
        solid = self._solid_i
        acc = [_I_SOLID] * (W * H)
        inner = [_I_AIR] * max(0, W - 4)
        for iy in range(1, H - 1):
            if 2 <= iy <= H - 3:
                acc[iy * W + 2 : iy * W + W - 2] = inner
                slow = (1, W - 2)
            else:
                slow = range(1, W - 1)
            for ix in slow:
                key = (ix - 1, iy - 1)
                a = _I_AIR
                if (
                    solid(ix, iy - 1)
                    or (solid(ix - 1, iy - 1) and not solid(ix - 1, iy))
                    or (solid(ix + 1, iy - 1) and not solid(ix + 1, iy))
                ):
                    a = _I_FLOOR
                elif solid(ix - 1, iy) and solid(ix + 1, iy):
                    a = _I_CORRIDOR
                elif key in self._vx or key in self._hy:
                    a = _I_CLIMB
                elif (
                    solid(ix - 1, iy)
                    or solid(ix + 1, iy)
                    or (solid(ix - 1, iy + 1) and not solid(ix, iy + 1))
                    or (solid(ix + 1, iy + 1) and not solid(ix, iy + 1))
                ):
                    a = _I_WALL
                elif solid(ix, iy + 1):
                    a = _I_CEILING
                acc[ix + iy * W] = a
        for key in (*self._vx, *self._hy):
            ix, iy = key[0] + 1, key[1] + 1
            if 2 <= ix <= W - 3 and 2 <= iy <= H - 3:
                acc[ix + iy * W] = _I_CLIMB
        self.acc_i = acc  # 含外环的 acc 序号

    # AImapper.FindPassagesOfCurrentTile / FindFallRiskOfCurrentTile 里与连接无关的部分

    def _find_passage_info(self) -> None:
        W, H = self.W, self.H
        solid = self._solid_i
        n = W * H
        self.narrow_i = [False] * n
        # 只有底部外环之上的格有地面支撑：altitude 是离地行数；fallRisk 落在最底一行
        self.floor_altitude_i = [100000] * n
        for ix in range(1, W - 1):
            for iy in range(1, H - 1):
                self.floor_altitude_i[ix + iy * W] = iy
        self.fall_y_i = [iy for iy in range(H) for _ in range(W)]
        for iy in range(1, H - 1):
            self.fall_y_i[iy * W + 1 : iy * W + W - 1] = [1] * (W - 2)
        # narrowSpace 只可能出现在靠外环的格
        eight = ((-1, 0), (-1, -1), (0, -1), (1, -1))
        for iy in range(H):
            near_y = iy <= 2 or iy >= H - 3
            for ix in range(W) if near_y else [*range(0, min(3, W)), *range(max(3, W - 3), W)]:
                for dx, dy in eight:
                    if solid(ix + dx, iy + dy) and solid(ix - dx, iy - dy):
                        self.narrow_i[ix + iy * W] = True

    # 对外查询

    def _idx(self, t) -> int:
        """公开格 -> 含外环的下标；环外返回 -1。"""
        ix, iy = t[0] + 1, t[1] + 1
        if ix < 0 or iy < 0 or ix >= self.W or iy >= self.H:
            return -1
        return ix + iy * self.W

    def tile_of(self, p: V2) -> tuple[int, int]:
        return (int(math.floor(p.x / TILE)), int(math.floor(p.y / TILE)))

    def middle_of(self, t) -> V2:
        x = self._vx.get((t[0], t[1]), t[0] * TILE + TILE / 2)
        y = self._hy.get((t[0], t[1]), t[1] * TILE + TILE / 2)
        return V2(x, y)

    def solid(self, t) -> bool:
        i = self._idx(t)
        return i < 0 or self.acc_i[i] == _I_SOLID

    def vertical_beam(self, t) -> bool:
        return (t[0], t[1]) in self._vx

    def horizontal_beam(self, t) -> bool:
        return (t[0], t[1]) in self._hy

    def acc_index(self, t) -> int:
        i = self._idx(t)
        return _I_SOLID if i < 0 else self.acc_i[i]

    def acc(self, t) -> str:
        return ACC_NAMES[self.acc_index(t)]

    def accessible(self, t, breed: LizardBreedParams) -> bool:
        """AImap.TileAccessibleToCreature：该格的 acc 对模板合法。"""
        return breed.tile_resistances[self.acc_index(t)][0] <= 1

    def terrain_proximity(self, t) -> int:
        """AImap.getTerrainProximity：到最近实心格的 4 邻域步数(实心格 0，贴实心的空格 1)；房间(含外环)之外 -1。
        实心只有外环，所以就是到外环的轴向最小距离。"""
        ix, iy = t[0] + 1, t[1] + 1
        if ix < 0 or iy < 0 or ix >= self.W or iy >= self.H:
            return -1
        return min(ix, iy, self.W - 1 - ix, self.H - 1 - iy)

    def narrow_space(self, t) -> bool:
        i = self._idx(t)
        return i >= 0 and self.narrow_i[i]

    def floor_altitude(self, t) -> int:
        i = self._idx(t)
        return 100000 if i < 0 else self.floor_altitude_i[i]

    def fall_risk_y(self, t) -> int:
        """AItile.fallRiskTile.y（公开格坐标）。"""
        i = self._idx(t)
        return t[1] if i < 0 else self.fall_y_i[i] - 1


def terrain_for(win) -> Terrain:
    """按 win.geometry_version / 宽高缓存在 win 上，变了才重建。"""
    key = (getattr(win, "geometry_version", 0), win._WL, win._HL)
    t = getattr(win, "_lizard_terrain", None)
    if t is not None and t.key == key:
        return t
    t = Terrain(win._WL, win._HL, list(getattr(win, "poles", ())))
    t.key = key
    win._lizard_terrain = t
    return t
