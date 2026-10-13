"""窗口上的物品管理：放置 / 移除 / 清空、鼠标拖拽、逐 tick 推进与分层绘制，全部按注册表通用处理。"""
from __future__ import annotations

import math
import random
from types import SimpleNamespace

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from ..control.hotkey import HK_PLACE_ESC, VK_ESCAPE
from ..i18n import t
from . import get as _kind, kinds
from .state import ItemState

PLACE_BANNER_BG = (0, 0, 0, 150)
PLACE_BANNER_TEXT = (255, 255, 255, 220)
REMOVE_MARK = (235, 70, 60)
REMOVE_PAD = 7.0
REMOVE_MARK_RAD = 11.0


_groups = None


def _g():
    """按用途分好的物品类型表；竖杆横杆共用 poles。"""
    global _groups
    if _groups is None:
        seen, stores = set(), []
        for k in kinds():
            if k.store not in seen:
                seen.add(k.store)
                stores.append(k)
        _groups = SimpleNamespace(
            stores=tuple(stores),
            early=tuple(k for k in stores if not k.late_tick),
            late=tuple(k for k in stores if k.late_tick),
            mobile=tuple(k for k in kinds() if k.mobile),
            collide=tuple(k for k in kinds() if k.collides),
            grab=tuple(sorted((k for k in stores if k.grab_pad is not None),
                              key=lambda k: -k.grab_rank)),
            by_use={})
    return _groups


class ItemHost:

    def _init_items(self):
        for k in kinds():
            setattr(self, k.store, None if k.single else [])
        self._item_seeds = {}
        self._drag = None              # (kind, obj, 上一帧光标)
        self._place_mode = False
        self._place_kind = None        # 物品 key 或 "remove"
        self._place_preview = None
        self._stun_rng = random.Random(98765)

    def _items(self):
        for k in _g().mobile:
            yield from k.objects(self)

    def items_affording(self, use):
        """提供某种用法的物品；共用存放属性且都提供该用法的几种（竖杆横杆）按放置顺序一起给。"""
        by_use = _g().by_use
        plan = by_use.get(use)
        if plan is None:
            plan, seen = [], set()
            for k in kinds():
                if use not in k.affords or k.store in seen:
                    continue
                seen.add(k.store)
                mates = [m for m in kinds() if m.store == k.store]
                if all(use in m.affords for m in mates):
                    plan.append((k, True))
                else:
                    plan.extend((m, False) for m in mates if use in m.affords)
            plan = by_use[use] = tuple(plan)
        if len(plan) == 1 and plan[0][1] and not plan[0][0].single:
            return getattr(self, plan[0][0].store)    # 单一存放：直接给原列表，不复制
        out = []
        for k, whole in plan:
            if whole:
                v = getattr(self, k.store)
                if k.single:
                    if v is not None:
                        out.append(v)
                else:
                    out.extend(v)
            else:
                out.extend(k.objects(self))
        return out

    def has_items(self):
        return any(self._present(k) for k in _g().stores)

    def _present(self, k):
        v = getattr(self, k.store)
        return v is not None and v != []

    def item_seed(self, kind):
        return self._item_seeds.get(kind.seed_key or kind.key, 0)

    def can_place(self, key):
        return _kind(key).can_place(self)

    def place(self, key, lx, ly):
        k = _kind(key)
        if not k.can_place(self):
            return None
        sk = k.seed_key or k.key
        seed = self._item_seeds.get(sk, 0)
        obj = k.make(self, lx, ly, seed)
        self._item_seeds[sk] = seed + 1
        if k.single:
            old = k.objects(self)
            if old:
                old[0].state = k.dead_state
        if hasattr(obj, "_impact_cb"):
            obj._impact_cb = self._shake_impact
        k.add(self, obj)
        self.world_version += 1
        if k.geometry:
            self.geometry_version += 1
        if k.single or not k.can_place(self):
            self._exit_place_mode()
        self.update()
        return obj

    def enter_place_mode(self, key):
        k = _kind(key)
        if not k.can_place(self):
            return False
        self._place_mode = True
        self._place_kind = key
        k.on_enter_place(self)
        self._begin_place_capture()
        return True

    def enter_remove_mode(self):
        self._place_mode = True
        self._place_kind = "remove"
        self._begin_place_capture()
        return True

    def _begin_place_capture(self):
        """进入放置模式，grabMouse 防点击被覆盖窗截走。"""
        hk = getattr(self, "_hotkey_filter", None)
        if hk is not None:
            hk.register(HK_PLACE_ESC, 0, VK_ESCAPE)
        if not self._hwnd:
            self._hwnd = int(self.winId())
        from ..control.mouse import set_passthrough
        set_passthrough(self._hwnd, False)
        self._passthrough = False
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.grabMouse()

    def _exit_place_mode(self):
        if not self._place_mode:
            return
        self._place_mode = False
        self._place_kind = None
        self._place_preview = None
        hk = getattr(self, "_hotkey_filter", None)
        if hk is not None:
            hk.unregister(HK_PLACE_ESC)
        self.releaseMouse()
        self.unsetCursor()
        self._passthrough = None

    def _place_click(self, lx, ly):
        if self._place_kind == "remove":
            self._remove_at((lx, ly))
        else:
            self.place(self._place_kind, lx, ly)

    def _forget(self, k, obj):
        k.drop(self, obj)
        if self._drag is not None and self._drag[1] is obj:
            self._drag = None

    def clear_kind(self, key):
        k = _kind(key)
        objs = list(k.objects(self))
        for o in objs:
            self._forget(k, o)
            k.discard(self, o)
        if objs:
            self.world_version += 1
            if k.geometry:
                self.geometry_version += 1
        self._exit_place_mode()
        self.update()

    def clear_all_items(self):
        for k in kinds():
            self.clear_kind(k.key)

    def _remove_target(self, pos):
        """光标下最近的可移除物体；杆身上算 0，光标落在小物体内部时小物体优先。"""
        cx, cy = pos
        best, bestd = None, REMOVE_PAD
        for k in kinds():
            for o in k.objects(self):
                d = k.hit(o, cx, cy)
                if d is not None and d <= bestd:
                    best, bestd = (k, o), d
        return best

    def _remove_at(self, pos):
        hit = self._remove_target(pos)
        if hit is None:
            return False
        k, obj = hit
        self._forget(k, obj)
        k.discard(self, obj)
        if k.geometry:
            self.geometry_version += 1
        self.world_version += 1
        self.update()
        return True

    def _grab_target(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        for k in _g().grab:
            best, bestd = None, 1e9
            for o in k.objects(self):
                if not k.grabbable(o):
                    continue
                d = math.hypot(cx - o.x, cy - o.y)
                if d <= o.rad + k.grab_pad and d < bestd:
                    best, bestd = o, d
            if best is not None:
                return k, best
        return None

    def _begin_item_drag(self, pos) -> bool:
        hit = self._grab_target(pos)
        if hit is None:
            return False
        k, o = hit
        k.on_grab(o)
        o.state = ItemState.MOUSE
        o.vx = o.vy = 0.0
        o.last_x, o.last_y = pos
        o.x, o.y = pos
        self._drag = (k, o, tuple(pos))
        return True

    def _step_item_drag(self, k):
        if self._drag is None or self._drag[0] is not k:
            return
        _, o, last = self._drag
        if o.state != ItemState.MOUSE:
            self._drag = None
            return
        cur = self.cursor_logical()
        if cur is None:
            return
        o.last_x, o.last_y = o.x, o.y
        o.vx = cur[0] - last[0]
        o.vy = cur[1] - last[1]
        o.x, o.y = cur
        self._drag = (k, o, tuple(cur))

    def _end_item_drag(self):
        if self._drag is None:
            return False
        k, o, _ = self._drag
        sp = math.hypot(o.vx, o.vy)
        if sp > k.fling_cap:
            o.vx *= k.fling_cap / sp
            o.vy *= k.fling_cap / sp
        k.on_release(self, o)
        self._drag = None
        return True

    def _tick_items(self, late=False):
        d = self._drag
        for k in (_g().late if late else _g().early):
            if d is not None and d[0] is k:
                self._step_item_drag(k)
            if getattr(self, k.store):
                k.tick(self)

    def _colliding_items(self):
        out = []
        for k in _g().collide:
            out.extend(k.objects(self))
        return out

    def _splash_items(self):
        out = []
        for k in _g().mobile:
            out.extend(o for o in k.objects(self) if o.state in k.splash_states)
        return out

    def _items_floor_shift(self, old, new):
        for k in kinds():
            k.floor_shift(self, old, new)

    def _items_zerog(self):
        for k in kinds():
            k.on_zerog(self)

    def _draw_items_under(self, p):
        for k in _g().stores:
            if self._present(k):
                k.draw_under(self, p)

    def _draw_items(self, p, layer):
        for k in _g().stores:
            if k.layer == layer and self._present(k):
                k.draw(self, p)

    def _draw_place_hint(self, p):
        self._draw_place_banner(p)
        if self._place_kind == "remove":
            self._draw_remove_hint(p)
            return
        k = _kind(self._place_kind)
        k.draw_guide(self, p)
        cur = self.cursor_logical()
        if cur is not None and 0.0 <= cur[0] <= self._WL and 0.0 <= cur[1] <= self._HL:
            k.draw_hint(self, p, cur[0], cur[1])

    def _draw_place_banner(self, p):
        label = t("place_hint_remove" if self._place_kind == "remove" else "place_hint")
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont()
        f.setPointSizeF(9.0)
        p.setFont(f)
        fm = p.fontMetrics()
        tw, th = fm.horizontalAdvance(label), fm.height()
        x, y, pad = (self._WL - tw) * 0.5, 8.0, 8.0
        bg = QPainterPath()
        bg.addRoundedRect(x - pad, y, tw + pad * 2.0, th + 4.0, 6.0, 6.0)
        p.fillPath(bg, QColor(*PLACE_BANNER_BG))
        p.setPen(QColor(*PLACE_BANNER_TEXT))
        p.drawText(QRectF(x, y + 2.0, tw, th), Qt.AlignmentFlag.AlignCenter, label)
        p.restore()

    def _draw_remove_hint(self, p):
        cur = self.cursor_logical()
        if cur is None:
            return
        cx, cy = cur
        if not (0.0 <= cx <= self._WL and 0.0 <= cy <= self._HL):
            return
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(*REMOVE_MARK, 200), 1.4, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(cx - 12.0, cy), QPointF(cx + 12.0, cy))
        p.drawLine(QPointF(cx, cy - 12.0), QPointF(cx, cy + 12.0))
        hit = self._remove_target(cur)
        if hit is not None:
            p.setPen(QPen(QColor(*REMOVE_MARK), 2.0))
            hit[0].draw_mark(p, hit[1], REMOVE_MARK_RAD)
        p.restore()
