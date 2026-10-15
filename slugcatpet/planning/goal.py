"""规划目标。"""

from __future__ import annotations


class Goal:
    """目标：pos()、valid()、key()。radius 是到位容差，只有 can_stay 用；contact 是达成方式，只有补救层读。"""

    __slots__ = ("obj", "radius", "contact", "_pos_fn", "_valid_fn", "_key")

    def __init__(self, pos_fn, valid_fn, key, obj=None, radius=0.0, contact="body"):
        self._pos_fn = pos_fn
        self._valid_fn = valid_fn
        self._key = key
        self.obj = obj
        self.radius = float(radius)
        self.contact = contact

    def pos(self):
        return self._pos_fn()

    def valid(self):
        return bool(self._valid_fn())

    def key(self):
        return self._key


def point_goal(x, y, radius=0.0, contact="body"):
    x, y = float(x), float(y)
    return Goal(lambda: (x, y), lambda: True, ("pt", x, y), radius=radius, contact=contact)


def obj_goal(obj, valid=None, radius=0.0, contact="body"):
    """物体目标：valid 为接收 obj 的谓词，缺省恒真。"""
    vf = (lambda: valid(obj)) if valid is not None else (lambda: True)
    return Goal(lambda: (obj.x, obj.y), vf, ("obj", id(obj)), obj=obj, radius=radius, contact=contact)
