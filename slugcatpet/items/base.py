"""物品类型 ItemKind：一种可放进世界的东西的放置、移除、拖拽、推进、绘制与用法。"""

from __future__ import annotations

import math

from .state import ItemState

EDIBLE = "edible"
THROWABLE = "throwable"
CLIMBABLE = "climbable"
WARM = "warm"
CARRYABLE = "carryable"
TOY = "toy"
USES = frozenset((EDIBLE, THROWABLE, CLIMBABLE, WARM, CARRYABLE, TOY))

# 活物被什么打中，传给模型的 struck()
HIT_STONE = "stone"
HIT_SPEAR = "spear"
HIT_SLAM = "slam"

GHOST_RGB = (110, 170, 255)  # 布局蓝图预览
GHOST_OPACITY = 0.6
DIMMED_OPACITY = 0.35  # 预览时场上会被换掉的物品


def creatures(win):
    """场上的活物（不论死活），按物品注册表和放置顺序。"""
    return [o for o in win._items() if getattr(o, "creature", False)]


def alive_creature(o) -> bool:
    return getattr(o, "creature", False) and not o.dead


def dump_loose(obj, **extra):
    """散落物的存档：还在场上（没吃掉、没消解）就存位置和种子。"""
    if obj.state in (ItemState.EATEN, ItemState.GONE) or getattr(obj, "dissolve", -1) >= 0:
        return None
    return {"x": obj.x, "y": obj.y, "seed": obj._id, **extra}


class ItemKind:
    key = ""
    store = ""
    single = False
    placeable = True  # 侧边栏有放置按钮
    cap = 12  # 上限；None 不限
    affords = frozenset()
    seed_key = None
    layer = "front"  # 绘制层：mid（盖住猫身，抓杆的手在它上面）/ front / top（水之上）
    mobile = True  # 会动：运动检测、出界夹回、重力、水位
    collides = False
    late_tick = False
    geometry = False  # 增删会改变路径前提
    grab_pad = None
    grab_states = (ItemState.FREE,)
    grab_rank = 0  # 重叠时大者先被拖
    fling_cap = 14.0
    splash_states = (ItemState.FREE,)
    dead_state = ItemState.EATEN
    varies = False  # 每件物体提供的用法随状态变（见 affords_now）
    dissolve_ticks = 40  # 消解（淡出）用的帧数
    blueprint = False  # 归布局蓝图管
    secondary = False  # 右键点中会调 on_secondary

    def dump(self, obj):
        """存档用的字典（坐标为当时的逻辑坐标）；None 不存。"""
        return None

    def load(self, win, d, fit):
        """按 dump 的字典重建物体，坐标经 fit 换到当前屏幕；不入场，None 为放弃。"""
        return None

    def keeps(self, obj) -> bool:
        """清空时留下。"""
        return False

    def removal_note(self, obj) -> str | None:
        """单个移除前要确认时，给出弹窗里展示的内容；None 直接移除。"""
        return None

    def on_secondary(self, win, obj, global_pos):
        """右键点中 obj（secondary 为真时）。"""

    def draw_overlay(self, win, p):
        """盖在所有层之上、不受地面线裁剪的提示。"""

    def draw_ghost(self, win, p, obj):
        """布局蓝图预览里的虚影。"""

    def affords_now(self, obj, use) -> bool:
        """varies 时：这件物体眼下提不提供 use。"""
        return True

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

    def make_room(self, win) -> bool:
        """程序生成前腾位置：默认只看上限。"""
        return self.can_place(win)

    def dissolve(self, win, obj):
        """开始消解：松手，之后不能拿、不提供用法，淡出完就移除。物体要有 dissolve 字段（-1 为没在消解）。"""
        if obj.dissolve >= 0:
            return
        obj.dissolve = 0
        for pet in win.pets:
            pet.body.release(obj)
        if getattr(obj, "held_by_hand", None) is not None:
            obj.held_by_hand = None
        if obj.state in (ItemState.CARRIED, ItemState.MOUSE):
            obj.state = ItemState.FREE

    def dissolve_alpha(self, obj, ts=1.0) -> float:
        d = getattr(obj, "dissolve", -1)
        if d < 0:
            return 1.0
        return max(0.0, 1.0 - (d + ts) / self.dissolve_ticks)

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
        """能被光标拖：在 grab_states 里，或是猫手里拿着的可拿物（抢过来）；消解中的不行。"""
        if getattr(obj, "dissolve", -1) >= 0:
            return False
        return obj.state in self.grab_states or (obj.state == ItemState.CARRIED and CARRYABLE in self.affords)

    def grab_dist(self, obj, cx, cy) -> float:
        """光标到物体抓取点的距离，和 rad + grab_pad 比。"""
        return math.hypot(cx - obj.x, cy - obj.y)

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
            d = getattr(o, "dissolve", -1)
            if d >= 0:
                o.dissolve = d + 1
                if o.dissolve >= self.dissolve_ticks:
                    o.state = self.dead_state
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

    def static_sig(self, win):
        """静态内容的签名，变了才重画；没有返回 ()。"""
        return ()

    def draw_behind(self, win, p):
        """画在猫身后的部分（如走路时远侧手里的武器）。"""

    def paint_icon(self, p, r, atlas):
        """侧边栏按钮图标，画在矩形 r 内。"""


def _pt(x, y):
    from PySide6.QtCore import QPointF

    return QPointF(x, y)
