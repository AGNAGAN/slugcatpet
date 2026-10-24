"""蜥蜴寻路：AImapper 的连接生成 + PathFinder / LizardPather 的路径选择。

连接按原版 FindPassagesOfCurrentTile 的顺序生成（顺序影响同价时的选择）。
搜索是从目的地反向、朝蜥蜴所在格的 A*（原版启发），每 tick 推进固定步数；
follow_path 只遍历当前格的连接，O(邻居数)。
"""

from __future__ import annotations

from typing import NamedTuple

from .breeds import (
    ACC_INDEX,
    ALLOWED,
    CLIMB,
    CURVED_FLOOR,
    DOUBLE_REACH_UP,
    DROP_TO_CLIMB,
    DROP_TO_FLOOR,
    FLOOR,
    ILLEGAL_CONNECTION,
    ILLEGAL_TILE,
    LIZARD_TURN,
    OPEN_DIAGONAL,
    REACH_DOWN,
    REACH_OVER_GAP,
    REACH_UP,
    SEMI_DIAGONAL_REACH,
    STANDARD,
    UNALLOWED,
    UNWANTED,
    LizardBreedParams,
)
from .rw import FOUR_DIRECTIONS, int_clamp_at_one
from .terrain import Terrain

__all__ = [
    "STANDARD",
    "REACH_OVER_GAP",
    "REACH_UP",
    "DOUBLE_REACH_UP",
    "REACH_DOWN",
    "SEMI_DIAGONAL_REACH",
    "DROP_TO_FLOOR",
    "DROP_TO_CLIMB",
    "LIZARD_TURN",
    "OPEN_DIAGONAL",
    "MovementConnection",
    "LizardPather",
]

_SOLID = ACC_INDEX["Solid"]
_AIR = ACC_INDEX["Air"]
_FLOOR = ACC_INDEX[FLOOR]
_CURVED = ACC_INDEX[CURVED_FLOOR]
_CLIMB = ACC_INDEX[CLIMB]
_FAR = 1e9


class MovementConnection(NamedTuple):
    type: str
    start_coord: tuple[int, int]
    destination_coord: tuple[int, int]
    distance: int


class _Graph:
    """地形的全部连接（与品种无关）。out/inc 以含外环的格下标索引，连接坐标用公开格坐标。"""

    def __init__(self, terrain: Terrain):
        self.W, self.H = terrain.W, terrain.H
        n = self.W * self.H
        self.out: list[list[MovementConnection]] = [[] for _ in range(n)]
        self.inc: list[list[MovementConnection]] = [[] for _ in range(n)]
        self._build(terrain)

    def _build(self, terrain: Terrain) -> None:
        W, H = self.W, self.H
        acc = terrain.acc_i
        out, inc = self.out, self.inc

        # 四周各垫 4 格实心，查询免边界判断（最远偏移 3 格）
        Wp = W + 8
        pad = [_SOLID] * (Wp * 4)
        for r in range(H):
            pad += [_SOLID] * 4 + acc[r * W : (r + 1) * W] + [_SOLID] * 4
        pad += [_SOLID] * (Wp * 4)

        def A(x, y):
            return pad[x + 4 + (y + 4) * Wp]

        def walk(x, y):
            a = A(x, y)
            return a != _AIR and a != _SOLID

        def mc(typ, sx, sy, dx, dy, dist):
            return MovementConnection(typ, (sx - 1, sy - 1), (dx - 1, dy - 1), dist)

        def straight_drop(ax, ay, bx, by):
            """IsThereAStraightDropBetweenTiles"""
            if A(ax, ay - 1) != _SOLID and A(ax, ay - 1) > A(ax, ay):
                for y in range(ay - 1, 0, -1):
                    if A(ax, y) == _FLOOR and A(ax, y - 1) == _SOLID:
                        return (ax, y) == (bx, by)
                    if A(ax, y) == _CLIMB and A(ax, y + 1) > A(ax, y) and (ax, y) == (bx, by):
                        return True
            return False

        cols, rows = terrain.cols, terrain.rows
        uniform = _uniform_cells(acc, W, H)
        new = tuple.__new__
        for y in range(1, rows + 1):
            urow = uniform[y]
            for x in range(1, cols + 1):
                here = out[x + y * W]
                if urow[x]:
                    # 5x6 窗口内 acc 全相同：只会有 Standard 连接（原版各条件都要求窗口内 acc 有大小差）
                    for dx, dy in FOUR_DIRECTIONS:
                        nx, ny = x + dx, y + dy
                        if 1 <= nx <= cols and 1 <= ny <= rows:
                            here.append(
                                new(MovementConnection, (STANDARD, (x - 1, y - 1), (nx - 1, ny - 1), 1))
                            )
                    for c in here:
                        inc[c.destination_coord[0] + 1 + (c.destination_coord[1] + 1) * W].append(c)
                    continue
                # 外环格上的连接不对外，且外环起点只会产生指向外环 / 环内的 Standard，所以不遍历外环
                for dx, dy in FOUR_DIRECTIONS:
                    if 1 <= x + dx <= cols and 1 <= y + dy <= rows:
                        here.append(mc(STANDARD, x, y, x + dx, y + dy, 1))
                a0 = A(x, y)
                # 竖直：ReachUp / DoubleReachUp / ReachDown
                if (
                    A(x, y + 1) != _SOLID
                    and walk(x, y + 2)
                    and A(x, y + 1) > a0
                    and A(x, y + 2) < A(x, y + 1)
                ):
                    here.append(mc(REACH_UP, x, y, x, y + 2, 2))
                if (
                    walk(x, y + 3)
                    and A(x, y + 1) != _SOLID
                    and A(x, y + 2) != _SOLID
                    and A(x, y + 1) > a0
                    and A(x, y + 1) > A(x, y + 3)
                    and A(x, y + 2) > a0
                    and A(x, y + 2) > A(x, y + 3)
                ):
                    here.append(mc(DOUBLE_REACH_UP, x, y, x, y + 3, 3))
                if (
                    A(x, y - 1) != _SOLID
                    and walk(x, y - 2)
                    and A(x, y - 1) > a0
                    and A(x, y - 2) < A(x, y + 1)
                ):
                    here.append(mc(REACH_DOWN, x, y, x, y - 2, 2))
                # 下落
                if A(x, y - 1) != _SOLID and A(x, y - 1) > a0:
                    num = 0
                    seen: list[int] = []
                    for y2 in range(y - 1, 0, -1):
                        if A(x, y2) in (_FLOOR, _CURVED) and A(x, y2 - 1) == _SOLID:
                            here.append(mc(DROP_TO_FLOOR, x, y, x, y2, y - y2))
                            seen += [y2, y2 - 1, y2 + 1]
                            break
                        if A(x, y2) == _CLIMB and A(x, y2 + 1) > A(x, y2):
                            here.append(mc(DROP_TO_CLIMB, x, y, x, y2, y - y2))
                            seen.append(y2)
                        num += 1
                    if num >= 4:
                        for sx in (1, -1):
                            y4 = y - 4
                            while y4 > 0 and A(x + sx, y4) != _SOLID and A(x, y4) != _SOLID:
                                if (
                                    A(x + sx, y4) in (_FLOOR, _CURVED)
                                    and A(x + sx, y4 + 1) != _SOLID
                                    and A(x + sx, y4 + 2) != _SOLID
                                    and A(x + sx, y4 - 1) == _SOLID
                                    and not straight_drop(x - 1, y, x + sx, y4)
                                    and not straight_drop(x + 1, y, x + sx, y4)
                                ):
                                    if y4 not in seen:
                                        here.append(mc(DROP_TO_FLOOR, x, y, x + sx, y4, y - y4))
                                    break
                                if (
                                    A(x + sx, y4) == _CLIMB
                                    and A(x + sx, y4 + 1) != _SOLID
                                    and A(x + sx, y4 + 2) != _SOLID
                                    and A(x + sx, y4 + 1) > A(x + sx, y4)
                                    and not straight_drop(x - 1, y, x + sx, y4)
                                    and not straight_drop(x + 1, y, x + sx, y4)
                                    and y4 not in seen
                                ):
                                    here.append(mc(DROP_TO_CLIMB, x, y, x + sx, y4, y - y4))
                                y4 -= 1
                # 水平
                for dx in (-1, 1):
                    if (
                        A(x + dx, y) != _SOLID
                        and walk(x + 2 * dx, y)
                        and A(x + dx, y) > a0
                        and A(x + 2 * dx, y) < A(x + dx, y)
                    ):
                        here.append(mc(REACH_OVER_GAP, x, y, x + 2 * dx, y, 2))
                    if (
                        a0 == _FLOOR
                        and A(x + dx, y) == _FLOOR
                        and A(x, y + 1) != _SOLID
                        and A(x + dx, y + 1) != _SOLID
                    ):
                        here.append(mc(LIZARD_TURN, x, y, x + dx, y, 1))
                    if A(x + dx, y) != _SOLID and A(x, y + 1) != _SOLID:
                        n5 = max(a0, A(x + dx, y + 1))
                        if A(x + dx, y) > n5 and A(x, y + 1) > n5:
                            here.append(mc(OPEN_DIAGONAL, x, y, x + dx, y + 1, 1))
                            out[x + dx + (y + 1) * W].append(mc(OPEN_DIAGONAL, x + dx, y + 1, x, y, 1))
                    if (
                        walk(x + dx, y - 2)
                        and A(x, y - 1) != _SOLID
                        and A(x + dx, y - 1) != _SOLID
                        and (A(x + dx, y) != _SOLID or A(x, y - 2) != _SOLID)
                        and A(x + dx, y) > a0
                        and A(x + dx, y) > A(x + dx, y - 2)
                        and A(x, y - 2) > a0
                        and A(x, y - 2) > A(x + dx, y - 2)
                        and A(x, y - 1) > a0
                        and A(x, y - 1) > A(x + dx, y - 2)
                        and A(x + dx, y - 1) > a0
                        and A(x + dx, y - 1) > A(x + dx, y - 2)
                    ):
                        here.append(mc(SEMI_DIAGONAL_REACH, x, y, x + dx, y - 2, 3))
                        back = mc(SEMI_DIAGONAL_REACH, x + dx, y - 2, x, y, 3)
                        out[x + dx + (y - 2) * W].append(back)
                        here.append(back)
                    if (
                        walk(x - 2, y + dx)
                        and A(x - 1, y) != _SOLID
                        and A(x - 1, y + dx) != _SOLID
                        and (A(x, y + dx) != _SOLID or A(x - 2, y) != _SOLID)
                        and A(x, y + dx) > a0
                        and A(x, y + dx) > A(x - 2, y + dx)
                        and A(x - 2, y) > a0
                        and A(x - 2, y) > A(x - 2, y + dx)
                        and A(x - 1, y) > a0
                        and A(x - 1, y) > A(x - 2, y + dx)
                        and A(x - 1, y + dx) > a0
                        and A(x - 1, y + dx) > A(x - 2, y + dx)
                    ):
                        here.append(mc(SEMI_DIAGONAL_REACH, x, y, x - 2, y + dx, 3))
                        back = mc(SEMI_DIAGONAL_REACH, x - 2, y + dx, x, y, 3)
                        out[x - 2 + (y + dx) * W].append(back)
                        here.append(back)
                for c in here:
                    inc[c.destination_coord[0] + 1 + (c.destination_coord[1] + 1) * W].append(c)


def _uniform_cells(acc, W, H):
    """uniform[y][x]：以 (x,y) 为中心 x±2、y-2..y+3 的窗口内 acc 全相同且不是 Floor（含外环）。"""
    nonuni = []
    for y in range(H):
        r = acc[y * W : (y + 1) * W]
        bad = bytearray(W)
        for p in range(1, W):
            if r[p] != r[p - 1]:
                for x in range(max(0, p - 2), min(W, p + 2)):
                    bad[x] = 1
        nonuni.append(bad)
    out = [bytearray(W) for _ in range(H)]
    for y in range(2, H - 3):
        rows = [acc[(y + k) * W : (y + k + 1) * W] for k in range(-2, 4)]
        bads = [nonuni[y + k] for k in range(-2, 4)]
        o = out[y]
        r0 = rows[0]
        for x in range(2, W - 2):
            v = r0[x]
            if v == _FLOOR:
                continue
            if bads[0][x] or bads[1][x] or bads[2][x] or bads[3][x] or bads[4][x] or bads[5][x]:
                continue
            if (
                rows[1][x] == v
                and rows[2][x] == v
                and rows[3][x] == v
                and rows[4][x] == v
                and rows[5][x] == v
            ):
                o[x] = 1
    return out


class _LazyRows:
    """按下标首次访问时才构造的行表。"""

    def __init__(self, n, build):
        self._rows = [None] * n
        self._build = build

    def __getitem__(self, i):
        r = self._rows[i]
        if r is None:
            r = self._rows[i] = self._build(i)
        return r

    def __len__(self):
        return len(self._rows)


class _Compiled:
    """某品种在某地形上的连接合法性与代价。"""

    def __init__(self, terrain: Terrain, breed: LizardBreedParams):
        g = terrain_graph(terrain)
        W = terrain.W
        self.W, self.H = W, terrain.H
        self.terrain = terrain
        self.breed = breed
        acc_ok = [breed.tile_resistances[a][0] <= UNWANTED for a in range(len(breed.tile_resistances))]
        # 覆盖范围：品种可达格的包围盒（含端点）
        acc_i, cols = terrain.acc_i, terrain.cols
        xs, ys = [], []
        for ty in range(terrain.rows):
            b = (ty + 1) * W + 1
            row = acc_i[b : b + cols]
            if any(acc_ok[a] for a in set(row)):
                ys.append(ty)
                xs += [tx for tx, a in enumerate(row) if acc_ok[a]]
        if xs:
            self.covered = (min(xs), min(ys), max(xs), max(ys))
        else:
            self.covered = (0, 0, 1, 1)
        self._g = g
        self._acc_ok = acc_ok
        n = W * terrain.H
        self._cache: dict[MovementConnection, tuple] = {}
        # 每格的出 / 入连接编译按需做（寻路只会碰到可达的那一小片）
        self.out_c = _LazyRows(n, self._build_out)
        self.rev = _LazyRows(n, self._build_rev)

    def _comp(self, c: MovementConnection):
        r = self._cache.get(c)
        if r is None:
            r = self._cache[c] = self._cost(c)
        return r

    def _build_out(self, i: int) -> list:
        terrain = self.terrain
        rows = []
        for c in self._g.out[i]:
            el, er = self._comp(c)
            sx, sy = c.start_coord
            dxx, dyy = c.destination_coord
            ax, ay = int_clamp_at_one(dxx - sx, dyy - sy)
            std_floor = c.type == STANDARD and terrain.acc_index((sx, sy)) == _FLOOR
            rows.append(
                (
                    c,
                    el,
                    er,
                    self.idx(c.destination_coord),
                    dxx,
                    dyy,
                    std_floor,
                    ax,
                    ay,
                    terrain.narrow_space((sx, sy)),
                )
            )
        return rows

    def _build_rev(self, i: int) -> list:
        rows = []
        for c in self._g.inc[i]:
            if self.in_covered(c.start_coord):
                el, er = self._comp(c)
                rows.append((self.idx(c.start_coord), el, er))
        return rows

    def idx(self, t) -> int:
        return t[0] + 1 + (t[1] + 1) * self.W

    def in_covered(self, t) -> bool:
        lo, b, r, tp = self.covered
        return lo <= t[0] <= r and b <= t[1] <= tp

    def acc_ok(self, t) -> bool:
        return self.terrain.accessible(t, self.breed)

    def tile_cost(self, t) -> tuple[int, float]:
        """AImap.TileCostForCreature"""
        if not self.acc_ok(t):
            return (ILLEGAL_TILE, 0.0)
        return self.breed.tile_resistances[self.terrain.acc_index(t)]

    def connection_allowed(self, c: MovementConnection) -> bool:
        """AImap.IsConnectionAllowedForCreature"""
        b, T = self.breed, self.terrain
        s, d = c.start_coord, c.destination_coord
        if not self.acc_ok(s) or not self.acc_ok(d) or b.connection_resistances[c.type][0] > UNWANTED:
            return False
        t = c.type
        if t in (DROP_TO_CLIMB, DROP_TO_FLOOR, REACH_DOWN, REACH_OVER_GAP, REACH_UP):
            if t == REACH_UP and T.acc_index(s) == _FLOOR and T.acc_index(d) == _FLOOR:
                if not self.acc_ok((s[0], s[1] + 1)):
                    if not self.acc_ok((s[0], s[1] - 1)):
                        return T.acc_index((s[0], s[1] - 1)) == _SOLID
                    return True
                return False
            ax, ay = int_clamp_at_one(d[0] - s[0], d[1] - s[1])
            return not self.acc_ok((s[0] + ax, s[1] + ay))
        if t == SEMI_DIAGONAL_REACH:
            ax, ay = int_clamp_at_one(d[0] - s[0], d[1] - s[1])
            if abs(d[0] - s[0]) > abs(d[1] - s[1]):
                ay = 0
            else:
                ax = 0
            return not self.acc_ok((s[0] + ax, s[1] + ay))
        if t == DOUBLE_REACH_UP:
            p = b.double_reach_up_params
            if (
                T.acc_index(s) > p[0]
                or T.acc_index((s[0], s[1] + 1)) > p[1]
                or T.acc_index((s[0], s[1] + 2)) > p[1]
                or T.acc_index((s[0], s[1] + 3)) > p[2]
            ):
                return False
            if not self.acc_ok((s[0], s[1] + 1)):
                return not self.acc_ok((s[0], s[1] + 2))
            return False
        if t == OPEN_DIAGONAL:
            if not self.acc_ok((s[0], d[1])):
                return not self.acc_ok((d[0], s[1]))
            return False
        return True

    def _cost(self, c: MovementConnection) -> tuple[int, float]:
        """PathFinder.CheckConnectionCost + LizardAI.TravelPreference 里这个世界用得到的部分。"""
        b = self.breed
        pl, pr = ILLEGAL_CONNECTION, 100.0 * c.distance
        if not self.connection_allowed(c):
            pass  # IllegalConnection + IllegalConnection：合法性不变
        else:
            rl, rr = b.connection_resistances[c.type]
            gl, gr = self.tile_cost(c.destination_coord)
            sl = self.tile_cost(c.start_coord)[0]
            pl = max(rl, gl, sl)
            pr = rr * c.distance + gr
        d = c.destination_coord
        if b.key == "green":
            if self.terrain.narrow_space(d):
                pr += 10.0
        elif b.key == "blue":
            pr += min(max(30.0 - self.terrain.floor_altitude(d) * 3.0, 0.0), 10.0)
        elif b.key == "pink":
            pr += self.terrain.floor_altitude(d) * 2.0
        return (pl, pr)


def terrain_graph(terrain: Terrain) -> _Graph:
    g = getattr(terrain, "_lizard_graph", None)
    if g is None:
        g = terrain._lizard_graph = _Graph(terrain)
    return g


def _compiled(terrain: Terrain, breed: LizardBreedParams) -> _Compiled:
    cache = getattr(terrain, "_lizard_compiled", None)
    if cache is None:
        cache = terrain._lizard_compiled = {}
    c = cache.get(breed.key)
    if c is None:
        c = cache[breed.key] = _Compiled(terrain, breed)
    return c


FALLBACK_RESISTANCE = 61728.0  # 原版 fallbackPathingCell 的 costToGoal 是随机值，这里取其期望


class PathingCell:
    """PathFinder.PathingCell 的实时视图（读的是 pather 当前数组）。

    tile 是格 (tx, ty)，fallbackPathingCell 的 tile 为 None。
    cost_to_goal = (legality, resistance)；generation 从未访问过是 -1。
    """

    __slots__ = ("pather", "tile")

    def __init__(self, pather, tile):
        self.pather = pather
        self.tile = tile

    @property
    def world_coordinate(self):
        return self.tile

    def _i(self) -> int:
        return self.pather._comp.idx(self.tile)

    @property
    def generation(self) -> int:
        return -1 if self.tile is None else self.pather._cgen[self._i()]

    @property
    def legality(self) -> int:
        return 0 if self.tile is None else self.pather._cl[self._i()]

    @property
    def resistance(self) -> float:
        return FALLBACK_RESISTANCE if self.tile is None else self.pather._cr[self._i()]

    @property
    def cost_to_goal(self) -> tuple[int, float]:
        return (self.legality, self.resistance)

    @property
    def reachable(self) -> bool:
        return self.tile is not None and self.pather.coordinate_reachable(self.tile)

    @property
    def possible_to_get_back_from(self) -> bool:
        return self.tile is not None and self.pather.coordinate_possible_to_get_back_from(self.tile)

    def __eq__(self, o):
        return isinstance(o, PathingCell) and self.tile == o.tile

    def __hash__(self):
        return hash(self.tile)


FALLBACK_CELL = PathingCell(None, None)


class LizardPather:
    """每只蜥蜴一个。destination / 坐标都是公开格 (tx, ty)。

    搜索照原版 PathFinder：从目的地反向的 A*，启发值朝向蜥蜴当前格；
    每次 update 推进 steps_per_frame 格，蜥蜴一旦选了本轮 generation 的格就停止；
    没被本轮访问的格保持旧 generation 与旧代价。
    """

    def __init__(self, lizard_params: LizardBreedParams):
        self.breed = lizard_params
        self.terrain: Terrain | None = None
        self.destination: tuple[int, int] | None = None  # GetDestination（含待切换的）
        self.walk_past_point_of_no_return = False
        self.looking_for_impossible_path = False
        self.steps_per_frame = 10
        self._comp: _Compiled | None = None
        self._requested: tuple[int, int] | None = None
        self._reach: list[bool] | None = None
        self._back: list[bool] | None = None
        self._center: tuple[int, int] | None = None
        self._dest: tuple[int, int] | None = None  # 正在搜索的目的地
        self._next_dest: tuple[int, int] | None = None
        self._creature: tuple[int, int] | None = None
        self._gen = 1
        self._follow_gen = -2
        self._open: list[int] = []
        self._stepped = False
        self._cl: list[int] = []
        self._cr: list[float] = []
        self._cgen: list[int] = []
        self._h: list[tuple[int, float]] = []
        self._inopen: list[bool] = []

    # 更新与设置

    def update(self, terrain: Terrain, creature_tile=None) -> None:
        """每 tick 调一次：地形变了就重置，并推进搜索。creature_tile 是蜥蜴当前格。"""
        if creature_tile is not None:
            self._creature = (int(creature_tile[0]), int(creature_tile[1]))
        if terrain is not self.terrain:
            old_center = self._center
            self.terrain = terrain
            self._comp = _compiled(terrain, self.breed)
            n = self._comp.W * self._comp.H
            self._cl = [ALLOWED] * n
            self._cr = [_FAR] * n
            self._cgen = [-1] * n
            self._h = [(ALLOWED, _FAR)] * n
            self._inopen = [False] * n
            self._open = []
            self._reach = self._back = None
            self._center = None
            self._dest = self._next_dest = None
            if self._requested is not None:
                self.destination = self._resolve(self._requested)
            center = self._creature if self._creature is not None else old_center
            if center is not None and self._comp.acc_ok(center):
                self._map(center)
            elif self.destination is not None:
                self._assign(self.destination)
        elif self._reach is None and self._creature is not None and self._comp.acc_ok(self._creature):
            self._map(self._creature)
        self._step(self.steps_per_frame)
        self._stepped = True

    def set_destination(self, tile) -> None:
        tile = (int(tile[0]), int(tile[1]))
        self._requested = tile
        if self._comp is None:
            self.destination = tile
            return
        new = self._resolve(tile)
        self.destination = new
        if new == self._dest or new == self._next_dest:
            return
        c = self._comp
        reach = self._reach
        if self._dest is None or reach is None:
            self._assign(new)
        elif reach[c.idx(new)] and reach[c.idx(self._dest)]:
            self._next_dest = new  # 旧搜索收尾后再切换
        else:
            self._assign(new)

    def _resolve(self, tile):
        """夹进覆盖范围，再找一个可达的邻格（FindReachableNeighbourIfPossible）。"""
        c = self._comp
        lo, b, r, t = c.covered
        x = min(max(tile[0], lo), r)
        y = min(max(tile[1], b), t)
        if self._reach is not None:
            for dx, dy in ((0, 0), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1)):
                n = (x + dx, y + dy)
                if c.in_covered(n) and self._reach[c.idx(n)]:
                    return n
        return (x, y)

    # 可达性映射（AccessibilityMapper）：从 center 正向可达、反向可回

    def _map(self, center) -> None:
        c = self._comp
        n = c.W * c.H
        reach = [False] * n
        back = [False] * n
        ci = c.idx(center)
        reach[ci] = back[ci] = True
        queue = [ci]
        k = 0
        while k < len(queue):
            i = queue[k]
            k += 1
            for _conn, el, _er, d, *_ in c.out_c[i]:
                if not reach[d] and el <= UNWANTED:
                    reach[d] = True
                    queue.append(d)
        queue = [ci]
        k = 0
        while k < len(queue):
            i = queue[k]
            k += 1
            for s, el, _er in c.rev[i]:
                if not back[s] and el <= UNWANTED:
                    back[s] = True
                    queue.append(s)
        first = self._reach is None
        self._reach, self._back = reach, back
        self._center = center
        if first and self._requested is not None:
            self.destination = self._resolve(self._requested)
        if self.destination is not None:
            self._assign(self.destination)  # AccessibilityMappingDone

    # PathFinder 搜索：AssignNewDestination / Update / CheckNeighbours

    def _assign(self, dest) -> None:
        c = self._comp
        self._dest = dest
        self._next_dest = None
        self._gen += 1
        for i in self._open:
            self._inopen[i] = False
        self._open = []
        d = c.idx(dest)
        reach = self._reach
        self.looking_for_impossible_path = not (reach is not None and reach[d])
        leg = c.tile_cost(dest)[0]
        self._h[d] = (leg, 0.0)
        self._cl[d] = leg
        self._cr[d] = 0.0
        self._add_open(d)

    def _add_open(self, i: int) -> None:
        h = self._h[i]
        o, hs = self._open, self._h
        for k in range(len(o)):
            if h <= hs[o[k]]:
                o.insert(k, i)
                return
        o.append(i)

    def _heuristic(self, s: int, pl: int, pr: float) -> tuple[int, float]:
        """LizardPather.HeuristicForCell"""
        if self.looking_for_impossible_path and not (self._reach and self._reach[s]):
            return (pl, pr * 5.5)
        c = self._comp
        cx, cy = self._creature if self._creature is not None else self._dest
        sx, sy = s % c.W - 1, s // c.W - 1
        return (pl, pr * 0.5 + abs(sx - cx) + abs(sy - cy))

    def _step(self, n: int) -> None:
        c = self._comp
        if c is None or self._dest is None:
            return
        d = c.idx(self._dest)
        self._cr[d] = 0.0
        reach = self._reach or [False] * (c.W * c.H)
        cl, cr, cgen, hs, inopen = self._cl, self._cr, self._cgen, self._h, self._inopen
        for _ in range(n):
            if self._open:
                i = self._open.pop(0)
                inopen[i] = False
                gl, gr = cl[i], cr[i]
                gen = self._gen
                impossible = self.looking_for_impossible_path
                for s, el, er in c.rev[i]:
                    if (el > UNWANTED or not reach[s]) and (not impossible or el == UNALLOWED):
                        continue
                    pl = gl if gl > el else el
                    pr = gr + er
                    h = self._heuristic(s, pl, pr)
                    if cgen[s] == gen:
                        if inopen[s]:
                            if hs[s] > h:
                                self._open.remove(s)
                                hs[s] = h
                                self._add_open(s)
                            if (cl[s], cr[s]) > (pl, pr):
                                cl[s], cr[s] = pl, pr
                    elif cgen[s] < gen:
                        cl[s], cr[s] = pl, pr
                        hs[s] = h
                        inopen[s] = True
                        cgen[s] = gen
                        self._add_open(s)
                if self._follow_gen == self._gen and cgen[c.idx(self._dest)] == gen:
                    for k in self._open:
                        inopen[k] = False
                    self._open = []
            elif self._next_dest is not None:
                self._assign(self._next_dest)
            elif self._follow_gen < self._gen - 1:
                self._assign(self._dest)
            else:
                break

    # 查询

    def cell(self, tile) -> PathingCell:
        """PathFinder.PathingCellAtWorldCoordinate：该格的实时视图；覆盖范围外是 fallbackPathingCell。只读，不推进搜索。"""
        c = self._comp
        t = (int(tile[0]), int(tile[1]))
        if c is None or not c.in_covered(t):
            return FALLBACK_CELL
        return PathingCell(self, t)

    def _cell(self, tile):
        """(idx, reachable, possibleToGetBackFrom)；覆盖范围外是 fallbackPathingCell。"""
        c = self._comp
        if c is None or self._reach is None or not c.in_covered(tile):
            return None
        i = c.idx(tile)
        return i, self._reach[i], self._back[i]

    def coordinate_reachable(self, tile) -> bool:
        cell = self._cell(tile)
        return cell is not None and cell[1]

    def coordinate_possible_to_get_back_from(self, tile) -> bool:
        cell = self._cell(tile)
        return cell is not None and cell[2]

    def coordinate_reachable_and_getbackable(self, tile) -> bool:
        cell = self._cell(tile)
        return cell is not None and cell[1] and cell[2]

    def connection_at_coordinate(self, out_going: bool, tile, i: int) -> MovementConnection | None:
        if self.terrain is None:
            return None
        g = terrain_graph(self.terrain)
        W = self.terrain.W
        x, y = tile[0] + 1, tile[1] + 1
        if x < 0 or y < 0 or x >= W or y >= self.terrain.H:
            return None
        lst = (g.out if out_going else g.inc)[x + y * W]
        return lst[i] if 0 <= i < len(lst) else None

    def cost_to_goal(self, tile) -> tuple[int, float] | None:
        """调试用：该格最近一次被访问时的代价；从未访问返回 None。"""
        c = self._comp
        if c is None or not self._cl or not c.in_covered(tile):
            return None
        i = c.idx(tile)
        return None if self._cgen[i] < 0 else (self._cl[i], self._cr[i])

    # LizardPather.FollowPath

    def follow_path(
        self, tile, body_direction=None, actually_following: bool = True
    ) -> MovementConnection | None:
        c = self._comp
        if c is None or self._dest is None:
            return None
        tile = (int(tile[0]), int(tile[1]))
        if actually_following:
            self._creature = tile
        if actually_following:
            if not self._stepped:
                self._step(self.steps_per_frame)  # 外部没调 update 时也推进搜索
            self._stepped = False
        if self._reach is None and c.acc_ok(tile):
            self._map(tile)
        if self._reach is None:
            return None
        cell = self._cell(tile)
        if actually_following and c.acc_ok(tile) and (cell is None or not cell[1] or not cell[2]):
            self._map(tile)  # OutOfElement
        T = self.terrain
        flag = (not T.narrow_space(tile)) and T.fall_risk_y(tile) < tile[1] - 5
        fx, fy = FOUR_DIRECTIONS[body_direction] if body_direction is not None else (0, 0)
        back = self._back
        cl, cr, cgen = self._cl, self._cr, self._cgen
        walk_past = self.walk_past_point_of_no_return
        best = None
        best_leg = UNALLOWED
        best_cost = (UNALLOWED, 0.0)
        best_gen = -5
        i0 = c.idx(tile)
        if i0 < 0 or i0 >= len(c.out_c):
            return None
        in_cov = c.in_covered
        for conn, el, er, d, dx, dy, std_floor, ax, ay, narrow_start in c.out_c[i0]:
            if not in_cov((dx, dy)):
                continue
            leg = el
            if (
                not flag
                and body_direction is not None
                and std_floor
                and (ax != 0 or narrow_start)
                and ax == -fx
                and ay == -fy
                and leg < UNWANTED
            ):
                leg = UNWANTED
            if not back[d] and not walk_past:
                leg = UNALLOWED
            gen = cgen[d]
            tl = cl[d]
            total = (tl if tl > leg else leg, cr[d] + er)
            if leg < best_leg:
                best, best_leg, best_gen, best_cost = conn, leg, gen, total
            elif leg == best_leg:
                if gen > best_gen:
                    best, best_gen, best_cost = conn, gen, total
                elif gen == best_gen and total <= best_cost:
                    best, best_cost = conn, total
        if actually_following:
            self._follow_gen = best_gen
        return best
