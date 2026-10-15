"""取这只猫的舌头、朝某点射舌。"""

from __future__ import annotations

import math

from ...core.units import clampf

OBJ_MIN_DIST = 60.0  # 舌尖离身体这么远之后才粘得住物体


def tongue_of(pet):
    """这只猫的舌头器官，没有舌头能力时为 None。"""
    return pet.organs.get("tongue")


def fire(pet, tx, ty):
    """朝 (tx, ty) 方向射舌，碰到屏幕边就粘住；舌头不空闲时收回。"""
    t = tongue_of(pet)
    if t is None:
        return
    if t.is_idle():
        hx, hy, hit = _ray_hit_edge(pet, t, pet.body.chunk0.x, pet.body.chunk0.y, tx, ty)
        mox, moy = pet.gfx.mouth_world()
        t.shoot(mox, moy, hx, hy, hit)
    else:
        t.retract()


def fire_at(pet, px, py, obj=None) -> bool:
    """直接朝世界点钉舌，obj 给定时粘住它；返回是否射出。"""
    t = tongue_of(pet)
    if t is None:
        return False
    mox, moy = pet.gfx.mouth_world()
    return t.shoot(mox, moy, px, py, hit=True, obj=obj)


def _ray_hit_edge(pet, tongue, mx, my, cx, cy):
    WL, H = pet.window._WL, pet.window._HL
    dx, dy = cx - mx, cy - my
    d0 = math.hypot(dx, dy)
    ux, uy = (0.0, -1.0) if d0 < 1e-6 else (dx / d0, dy / d0)
    eps = 1e-6
    best = None
    if uy < -eps:
        t = (0.0 - my) / uy
        if t > 0 and 0 <= mx + ux * t <= WL:
            best = t
    if ux < -eps:
        t = (0.0 - mx) / ux
        if t > 0 and 0 <= my + uy * t <= H and (best is None or t < best):
            best = t
    if ux > eps:
        t = (WL - mx) / ux
        if t > 0 and 0 <= my + uy * t <= H and (best is None or t < best):
            best = t
    if best is not None and best <= tongue.total:
        return mx + ux * best, my + uy * best, True
    ex = clampf(mx + ux * tongue.total, 0.0, WL)
    ey = clampf(my + uy * tongue.total, 0.0, H)
    return ex, ey, False


def ray_target(pet, ox, oy, ux, uy, length):
    """沿单位方向找舌头最先碰到的屏幕边、杆或物体：返回 (x, y, 物体或 None, 是否碰到)。"""
    from ...items.base import CLIMBABLE
    from ...items.state import ItemState

    win = pet.window
    best, obj = length, None
    for t in _edge_hits(ox, oy, ux, uy, win._WL, win._HL):
        if 0.0 < t < best:
            best = t
    hit = best < length
    for p in win.items_affording(CLIMBABLE):
        t = _seg_hit(ox, oy, ux, uy, p.ax, p.ay, p.bx, p.by)
        if t is not None and t < best:
            best, hit = t, True
    c0 = pet.body.chunk0
    for o in win._items():
        if getattr(o, "state", None) not in (ItemState.FREE, ItemState.HANGING) or not hasattr(o, "rad"):
            continue
        if getattr(o, "creature", False):  # 活物粘不住
            continue
        t = _circle_hit(ox, oy, ux, uy, o.x, o.y, o.rad)
        if t is None or t >= best:
            continue
        if math.hypot(ox + ux * t - c0.x, oy + uy * t - c0.y) < OBJ_MIN_DIST:
            continue
        best, obj, hit = t, o, True
    return ox + ux * best, oy + uy * best, obj, hit


def _edge_hits(ox, oy, ux, uy, W, H):
    if uy < 0.0:
        yield -oy / uy
    if uy > 0.0:
        yield (H - oy) / uy
    if ux < 0.0:
        yield -ox / ux
    if ux > 0.0:
        yield (W - ox) / ux


def _seg_hit(ox, oy, ux, uy, ax, ay, bx, by):
    sx, sy = bx - ax, by - ay
    den = ux * sy - uy * sx
    if abs(den) < 1e-9:
        return None
    qx, qy = ax - ox, ay - oy
    t = (qx * sy - qy * sx) / den
    s = (qx * uy - qy * ux) / den
    return t if t > 0.0 and 0.0 <= s <= 1.0 else None


def _circle_hit(ox, oy, ux, uy, cx, cy, r):
    qx, qy = cx - ox, cy - oy
    along = qx * ux + qy * uy
    if along <= 0.0:
        return None
    off2 = qx * qx + qy * qy - along * along
    if off2 > r * r:
        return None
    return max(0.0, along - math.sqrt(r * r - off2))
