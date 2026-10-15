"""跳跃弧线：按身体数值、按住档位和横向输入空跑物理，缓存 chunk0 相对起点的轨迹。"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
from dataclasses import dataclass

from .. import tuning
from .._paths import resource_dir
from ..core.creature import SlugcatBody

_SIM_W = 4000.0  # 模拟世界够宽，横向漂移不撞墙
_SIM_H = 1000.0
_SETTLE_TICKS = 120
_MAX_ARC_TICKS = 400

_DROP_H = 1600.0
_DROP_START_Y = 40.0
_MAX_DROP_TICKS = 400
_FREE_FALL = 1200.0  # 杆上起跳弧往下模拟的深度
_PJUMP_START_Y = 500.0  # 竖杆跳的模拟起跳高度，头顶留够上冲的空间

_BAKED = resource_dir() / "arcs.json.gz"

_cache: dict[tuple, object] = {}
_baked = None  # 随程序带的弧：{数值指纹: {弧名: 字段}}


@dataclass(frozen=True)
class JumpArc:
    """起跳弧：points 是每 tick chunk0 相对起跳点的位移（y↓），takeoff_h 是起跳时 chunk0 离地高度。"""

    hold_ticks: int
    move_dir: int
    takeoff_h: float
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class DropArc:
    """落体弧：points 同上，相对松手点。"""

    move_dir: int
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class PoleJumpArc:
    """竖杆跳弧：points 相对松杆点（y↓）。"""

    direction: int
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class BackflipArc:
    """站立后空翻弧：points 相对起跳点。"""

    direction: int
    points: tuple[tuple[float, float], ...]

    @property
    def apex(self) -> float:
        """最高点相对起跳点的上升高度 px（正值向上）。"""
        return max(-dy for _, dy in self.points)


@dataclass(frozen=True)
class PyroArc:
    """工匠爆跳弧：腾空第 PYRO_BOOST_AIR_TICKS tick 时调 pyro_boost。"""

    variant: str
    points: tuple[tuple[float, float], ...]


# 爆跳变体 → 输入方向 (ix, iy)，iy = 1 朝上。vert 直上，side± 横冲，diag± 斜上
PYRO_INPUTS = {"vert": (0, 0), "side+": (1, 0), "side-": (-1, 0), "diag+": (1, 1), "diag-": (-1, 1)}


BAKED_SPECS = (  # 离线算好、随程序带的弧
    tuple(("jump", (h, md)) for h in tuning.PLAN_JUMP_HOLD_GEARS for md in (0, 1, -1))
    + tuple(("freejump", (h, md)) for h in tuning.PLAN_JUMP_HOLD_GEARS for md in (0, 1, -1))
    + tuple(("drop", (md,)) for md in (0, 1, -1))
    + tuple(("polejump", (d,)) for d in (1, -1))
    + tuple(("backflip", (d, b)) for d in (1, -1) for b in (False, True))
    + tuple(("pyro", (v,)) for v in PYRO_INPUTS)
)

_KINDS = {
    "jump": JumpArc,
    "freejump": JumpArc,
    "drop": DropArc,
    "polejump": PoleJumpArc,
    "backflip": BackflipArc,
    "pyro": PyroArc,
}


def get_arc(stats, hold_ticks: int, move_dir: int = 0) -> JumpArc:
    """起跳弧；move_dir 取 -1、0、1，0 为不带横向输入。"""
    return _get(*_spec("jump", stats, hold_ticks, move_dir))


def get_drop_arc(stats, move_dir: int = 0) -> DropArc:
    return _get(*_spec("drop", stats, move_dir))


def get_pole_jump_arc(stats, direction: int) -> PoleJumpArc:
    return _get(*_spec("polejump", stats, direction))


def get_free_jump_arc(stats, hold_ticks: int, move_dir: int = 0) -> JumpArc:
    """站在杆上起跳的弧，一直落到 _FREE_FALL 深。"""
    return _get(*_spec("freejump", stats, hold_ticks, move_dir))


def get_backflip_arc(stats, direction: int, boosted: bool = False) -> BackflipArc:
    return _get(*_spec("backflip", stats, direction, boosted))


def get_pyro_arc(stats, variant: str) -> PyroArc:
    """工匠爆跳弧；variant 见 PYRO_INPUTS。"""
    return _get(*_spec("pyro", stats, variant))


def _spec(kind, stats, *args):
    """弧的缓存键和模拟函数。"""
    if kind == "jump":
        h, md = int(args[0]), int(args[1])
        return ("jump", stats, h, md), lambda: _simulate(stats, h, md)
    if kind == "freejump":
        h, md = int(args[0]), int(args[1])
        return ("freejump", stats, h, md), lambda: _simulate_free_jump(stats, h, md)
    if kind == "drop":
        md = int(args[0])
        return ("drop", stats, md), lambda: _simulate_drop(stats, md)
    if kind == "polejump":
        d = 1 if int(args[0]) >= 0 else -1
        return ("polejump", stats, d), lambda: _simulate_pole_jump(stats, d)
    if kind == "backflip":
        d = 1 if int(args[0]) >= 0 else -1
        b = bool(args[1]) if len(args) > 1 else False
        return ("backflip", stats, d, b), lambda: _simulate_backflip(stats, d, b)
    v = args[0]
    ix, iy = PYRO_INPUTS[v]
    return ("pyro", stats, v), lambda: _simulate_pyro(stats, v, ix, iy)


def stats_id(stats) -> str:
    """一组身体数值的指纹。"""
    return hashlib.sha1(repr(dataclasses.astuple(stats)).encode()).hexdigest()[:12]


def _name(key):
    return "|".join(str(v) for v in (key[0],) + key[2:])


def _from_baked(key):
    global _baked
    if _baked is None:
        try:
            _baked = json.loads(gzip.decompress(_BAKED.read_bytes()))
        except (OSError, ValueError):
            _baked = {}
    d = _baked.get(stats_id(key[1]), {}).get(_name(key))
    if d is None:
        return None
    try:
        d = dict(d, points=tuple(tuple(p) for p in d["points"]))
        return _KINDS[key[0]](**d)
    except (KeyError, TypeError):
        return None  # 字段对不上就现算


def _get(key, sim):
    arc = _cache.get(key)
    if arc is None:
        arc = _from_baked(key)
        if arc is None:
            arc = sim()  # 不在随程序带的弧里（数值改过）就现算
        _cache[key] = arc
    return arc


def bake(stats_list) -> dict:
    """现算这些数值的全部弧，得到随程序带的数据。"""
    out = {}
    for stats in stats_list:
        d = out.setdefault(stats_id(stats), {})
        for kind, args in BAKED_SPECS:
            key, sim = _spec(kind, stats, *args)
            d[_name(key)] = dataclasses.asdict(sim())
    return out


def sweep_hit(arc, dx: float, dy: float, radius: float):
    """(dx, dy) 离弧上某个采样点不超过 radius 时返回第一次命中的 tick（从 1 起），否则 None。"""
    r2 = radius * radius
    for i, (px, py) in enumerate(arc.points):
        ex, ey = dx - px, dy - py
        if ex * ex + ey * ey <= r2:
            return i + 1
    return None


def _simulate(stats, hold_ticks: int, move_dir: int) -> JumpArc:
    body = SlugcatBody((_SIM_W / 2.0, _SIM_H), _SIM_W, _SIM_H, stats=stats)
    for _ in range(_SETTLE_TICKS):
        body.step()
    ox, oy = body.chunk0.x, body.chunk0.y
    body.request_jump("stand", hold_ticks=hold_ticks)
    body.move_dir = int(move_dir)
    pts = []
    airborne = False
    for _ in range(_MAX_ARC_TICKS):
        body.step()
        pts.append((body.chunk0.x - ox, body.chunk0.y - oy))
        if body.on_floor():
            if airborne:
                break
        else:
            airborne = True
    return JumpArc(hold_ticks, int(move_dir), _SIM_H - oy, tuple(pts))


def _simulate_free_jump(stats, hold_ticks: int, move_dir: int) -> JumpArc:
    body = SlugcatBody((_SIM_W / 2.0, _SIM_H), _SIM_W, _SIM_H, stats=stats)
    for _ in range(_SETTLE_TICKS):
        body.step()
    ox, oy = body.chunk0.x, body.chunk0.y
    takeoff_h = _SIM_H - oy
    body.H = _SIM_H + _FREE_FALL
    body.chunk0.cy = body.chunk1.cy = 0
    body.tip_launch(hold_ticks=hold_ticks, move_dir=move_dir)
    pts = []
    for _ in range(_MAX_DROP_TICKS):
        body.step()
        pts.append((body.chunk0.x - ox, body.chunk0.y - oy))
        if body.on_floor():
            break
    return JumpArc(hold_ticks, int(move_dir), takeoff_h, tuple(pts))


def _simulate_drop(stats, move_dir: int) -> DropArc:
    body = SlugcatBody((_SIM_W / 2.0, _DROP_START_Y), _SIM_W, _DROP_H, stats=stats)
    body.move_dir = int(move_dir)
    ox, oy = body.chunk0.x, body.chunk0.y
    pts = []
    for _ in range(_MAX_DROP_TICKS):
        body.step()
        pts.append((body.chunk0.x - ox, body.chunk0.y - oy))
        if body.on_floor():
            break
    return DropArc(int(move_dir), tuple(pts))


def _simulate_backflip(stats, direction: int, boosted: bool = False) -> BackflipArc:
    body = SlugcatBody((_SIM_W / 2.0, _SIM_H), _SIM_W, _SIM_H, stats=stats)
    for _ in range(_SETTLE_TICKS):
        body.step()
    ox, oy = body.chunk0.x, body.chunk0.y
    body.backflip_launch(direction, boosted)
    pts = []
    airborne = False
    for _ in range(_MAX_ARC_TICKS):
        body.step()
        pts.append((body.chunk0.x - ox, body.chunk0.y - oy))
        if body.on_floor():
            if airborne:
                break
        else:
            airborne = True
    return BackflipArc(int(direction), tuple(pts))


def _simulate_pyro(stats, variant: str, ix: int, iy: int) -> PyroArc:
    body = SlugcatBody((_SIM_W / 2.0, _SIM_H), _SIM_W, _SIM_H, stats=stats)
    for _ in range(_SETTLE_TICKS):
        body.step()
    ox, oy = body.chunk0.x, body.chunk0.y
    body.request_jump("stand")
    pts = []
    air = 0
    fired = False
    for _ in range(_MAX_ARC_TICKS):
        if not fired and air >= tuning.PYRO_BOOST_AIR_TICKS:
            body.pyro_boost(ix, iy)
            fired = True
        body.step()
        pts.append((body.chunk0.x - ox, body.chunk0.y - oy))
        if body.on_floor():
            if fired:
                break
        else:
            air += 1
    return PyroArc(variant, tuple(pts))


def _simulate_pole_jump(stats, direction: int) -> PoleJumpArc:
    body = SlugcatBody((_SIM_W / 2.0, _PJUMP_START_Y), _SIM_W, _DROP_H, stats=stats)
    ox, oy = body.chunk0.x, body.chunk0.y
    body.pole_jump(direction)
    pts = []
    for _ in range(_MAX_DROP_TICKS):
        body.step()
        pts.append((body.chunk0.x - ox, body.chunk0.y - oy))
        if body.on_floor():
            break
    return PoleJumpArc(int(direction), tuple(pts))
