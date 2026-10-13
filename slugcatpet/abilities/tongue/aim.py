"""取这只猫的舌头、朝某点射舌。"""

from __future__ import annotations

import math

from ...core.units import clampf


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
