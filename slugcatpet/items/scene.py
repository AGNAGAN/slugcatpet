"""场景存取：把场上物品存成字典（重启保留、布局蓝图），再按当前屏幕摆回去。"""

from __future__ import annotations

from ..core.units import clampf
from . import get as _kind, kinds

BLUEPRINT_CAP = 12  # 布局蓝图最多存几个


class Fit:
    """存档时屏幕坐标 → 当前屏幕：不放大，屏幕变小时等比缩小；纵向从地面量，横向从中线量，贴边的从那条边量。"""

    def __init__(self, size, WL, HL):
        try:
            w0, h0 = float(size[0]), float(size[1])
        except (TypeError, ValueError, IndexError):
            w0, h0 = WL, HL
        w0, h0 = (w0 if w0 > 0.0 else WL), (h0 if h0 > 0.0 else HL)
        self.same = abs(w0 - WL) < 0.5 and abs(h0 - HL) < 0.5
        self.k = min(1.0, WL / w0, HL / h0) if w0 and h0 else 1.0
        self.w0, self.h0 = w0, h0
        self.WL, self.HL = WL, HL

    def x(self, x, edge=None):
        """edge 为 l / r 时从那条边量；不给时在边上或边外的自动贴边。"""
        if self.same:
            return x
        if edge is None:
            edge = "l" if x <= 0.0 else ("r" if x >= self.w0 else None)
        if edge == "l":
            return x * self.k
        if edge == "r":
            return self.WL - (self.w0 - x) * self.k
        return self.WL * 0.5 + (x - self.w0 * 0.5) * self.k

    def y(self, y, edge=None):
        """edge 为 t 时从顶边量；不给时在顶边或之上的自动贴顶。"""
        if self.same:
            return y
        if edge == "t" or (edge is None and y <= 0.0):
            return y * self.k
        return self.HL - (self.h0 - y) * self.k

    def inside(self, x, y, xedge=None, yedge=None):
        """换算后夹进屏幕。"""
        return clampf(self.x(x, xedge), 0.0, self.WL), clampf(self.y(y, yedge), 0.0, self.HL)


def capture(win, blueprint=False):
    """场上物品；blueprint 时只要归蓝图管的。"""
    items = []
    for k in kinds():
        if blueprint and not k.blueprint:
            continue
        for o in k.objects(win):
            d = k.dump(o)
            if d is not None:
                items.append({"kind": k.key, **d})
    return {"size": [win._WL, win._HL], "items": items}


def _entries(data, blueprint):
    items = data.get("items")
    if not isinstance(items, list):
        return []
    out = []
    for d in items:
        try:
            k = _kind(d.get("kind"))
        except (AttributeError, KeyError):
            continue
        if not blueprint or k.blueprint:
            out.append((k, d))
    return out


def build(win, data, blueprint=False):
    """按存档重建 (类型, 物体)，不放进场上；坏条目跳过。"""
    if not isinstance(data, dict):
        return []
    fit = Fit(data.get("size"), win._WL, win._HL)
    out = []
    for k, d in _entries(data, blueprint):
        try:
            obj = k.load(win, d, fit)
        except (KeyError, TypeError, ValueError):
            obj = None
        if obj is not None:
            out.append((k, obj))
    return out


def restore(win, data, blueprint=False):
    """摆回存档里的物品；blueprint 时先清掉场上归蓝图管的。"""
    if blueprint:
        for k in kinds():
            if k.blueprint:
                win.clear_kind(k.key)
    for k, obj in build(win, data, blueprint):
        if k.can_place(win):
            win.admit_item(k, obj)


def counts(data):
    """蓝图里各类物品的件数 {key: n}。"""
    out = {}
    if isinstance(data, dict):
        for k, _ in _entries(data, True):
            out[k.key] = out.get(k.key, 0) + 1
    return out
