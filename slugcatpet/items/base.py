"""物品类型 ItemKind：一种可放进世界的东西的放置、移除、拖拽、推进、绘制与用法。"""
from __future__ import annotations

import math

from .state import ItemState

EDIBLE = "edible"
THROWABLE = "throwable"
CLIMBABLE = "climbable"
WARM = "warm"
CARRYABLE = "carryable"
USES = frozenset((EDIBLE, THROWABLE, CLIMBABLE, WARM, CARRYABLE))


class ItemKind:

    key = ""
    store = ""
    single = False
    cap = 12                   # 上限；None 不限
    affords = frozenset()
    seed_key = None
    layer = "front"            # 绘制层：mid（猫身后、手前）/ front / top（水之上）
    mobile = True              # 会动：运动检测、出界夹回、重力、水位
    collides = False
    late_tick = False
    geometry = False           # 增删会改变路径前提
    grab_pad = None
    grab_states = (ItemState.FREE,)
    grab_rank = 0              # 重叠时大者先被拖
    fling_cap = 14.0
    splash_states = (ItemState.FREE,)
    dead_state = ItemState.EATEN

    def objects(self, win):
        v = getattr(win, self.store)
        if self.single:
            return [] if v is None else [v]
        return v

    def add(self, win, obj):
        if self.single:
            setattr(win, self.store, obj)
        else:
            getattr(win, self.store).append(obj)

    def discard(self, win, obj):
        if self.single:
            setattr(win, self.store, None)
        else:
            getattr(win, self.store).remove(obj)

    def can_place(self, win) -> bool:
        return self.cap is None or len(self.objects(win)) < self.cap

    def make(self, win, lx, ly, seed):
        raise NotImplementedError

    def on_enter_place(self, win):
        """进入放置模式时（预览用的随机量等）。"""

    def draw_guide(self, win, p):
        """放置模式下常驻的提示线等。"""

    def draw_hint(self, win, p, cx, cy):
        """放置预览，光标在世界内时调用。"""

    def drop(self, win, obj):
        obj.state = self.dead_state

    def hit(self, obj, cx, cy):
        """移除模式下光标到物体的距离（负数=在里面）；None 不可移除。"""
        if obj.state not in self.grab_states:
            return None
        return math.hypot(cx - obj.x, cy - obj.y) - obj.rad

    def draw_mark(self, p, obj, rad):
        p.drawEllipse(_pt(obj.x, obj.y), rad, rad)

    def grabbable(self, obj) -> bool:
        return obj.state in self.grab_states

    def on_grab(self, obj):
        """开始拖：清掉挂载 / 叼持等。"""

    def on_release(self, win, obj):
        if obj.state == ItemState.MOUSE:
            obj.state = ItemState.FREE

    def tick(self, win):
        objs = self.objects(win)
        if not objs:
            return
        for o in objs:
            o.step(win._WL, win._HL)
        self.after_step(win)
        setattr(win, self.store, [o for o in objs if o.state != self.dead_state])

    def after_step(self, win):
        """推进完本类全部物体之后（命中判定等）。"""

    def floor_shift(self, win, old, new):
        """地面高度变了。"""

    def on_zerog(self, win):
        """无重力打开。"""

    def draw_under(self, win, p):
        """猫身之下。"""

    def draw(self, win, p):
        raise NotImplementedError

    def paint_icon(self, p, r, atlas):
        """侧边栏按钮图标，画在矩形 r 内。"""


def _pt(x, y):
    from PySide6.QtCore import QPointF
    return QPointF(x, y)
