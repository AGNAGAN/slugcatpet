"""弧线模板：按 stats×档×横向输入离线空跑物理，缓存 chunk0 相对轨迹。"""

from __future__ import annotations

from dataclasses import dataclass

from .. import tuning
from ..core.creature import SlugcatBody

_SIM_W = 4000.0  # 宽 sim 世界：横向漂移不撞墙
_SIM_H = 1000.0
_SETTLE_TICKS = 120
_MAX_ARC_TICKS = 400

_DROP_H = 1600.0
_DROP_START_Y = 40.0
_MAX_DROP_TICKS = 400
_PJUMP_START_Y = 500.0  # 竖杆跳 sim 起跳高：留足头顶空间容上冲，不撞 sim 顶

_cache: dict[tuple, object] = {}


@dataclass(frozen=True)
class JumpArc:
    """起跳弧：points=逐 tick chunk0 相对起跳点位移（y↓），takeoff_h=起跳时 chunk0 距地高。"""

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
    """工匠爆跳弧：腾空第 PYRO_BOOST_AIR_TICKS tick 施 pyro_boost。"""

    variant: str
    points: tuple[tuple[float, float], ...]


# 爆跳变体 → 输入方向 (ix,iy)，iy=+1 表上：vert 直跳、side± 横向火箭、diag± 上斜
PYRO_INPUTS = {"vert": (0, 0), "side+": (1, 0), "side-": (-1, 0), "diag+": (1, 1), "diag-": (-1, 1)}


def get_arc(stats, hold_ticks: int, move_dir: int = 0) -> JumpArc:
    """起跳弧（缓存）；move_dir∈{-1,0,+1}，0=纯竖直。"""
    key = ("jump", stats, int(hold_ticks), int(move_dir))
    arc = _cache.get(key)
    if arc is None:
        arc = _simulate(stats, int(hold_ticks), int(move_dir))
        _cache[key] = arc
    return arc


def get_drop_arc(stats, move_dir: int = 0) -> DropArc:
    key = ("drop", stats, int(move_dir))
    arc = _cache.get(key)
    if arc is None:
        arc = _simulate_drop(stats, int(move_dir))
        _cache[key] = arc
    return arc


def get_pole_jump_arc(stats, direction: int) -> PoleJumpArc:
    d = 1 if int(direction) >= 0 else -1
    key = ("polejump", stats, d)
    arc = _cache.get(key)
    if arc is None:
        arc = _simulate_pole_jump(stats, d)
        _cache[key] = arc
    return arc


def get_backflip_arc(stats, direction: int, boosted: bool = False) -> BackflipArc:
    d = 1 if int(direction) >= 0 else -1
    key = ("backflip", stats, d, bool(boosted))
    arc = _cache.get(key)
    if arc is None:
        arc = _simulate_backflip(stats, d, bool(boosted))
        _cache[key] = arc
    return arc


def get_pyro_arc(stats, variant: str) -> PyroArc:
    """工匠爆跳弧（缓存）；variant∈vert/side±/diag±。"""
    key = ("pyro", stats, variant)
    arc = _cache.get(key)
    if arc is None:
        ix, iy = PYRO_INPUTS[variant]
        arc = _simulate_pyro(stats, variant, ix, iy)
        _cache[key] = arc
    return arc


def sweep_hit(arc, dx: float, dy: float, radius: float):
    """扫掠命中：(dx,dy) 落入任一采样点 radius 内 → 首个命中 tick（1 起），否则 None。"""
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
