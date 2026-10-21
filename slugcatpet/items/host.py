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
from .base import GHOST_OPACITY
from .state import ItemState

PLACE_BANNER_BG = (0, 0, 0, 150)
CLICK_CATCHER = (0, 0, 0, 1)  # 放置 / 移除模式的近乎透明底，接住点击
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
            grab=tuple(sorted((k for k in stores if k.grab_pad is not None), key=lambda k: -k.grab_rank)),
            by_use={},
        )
    return _groups


class ItemHost:
    def _init_items(self):
        for k in kinds():
            setattr(self, k.store, None if k.single else [])
        self._item_seeds = {}
        self._drag = None  # (kind, obj, 上一帧光标)
        self._item_dialog = None  # 物品开着的编辑弹窗
        self._confirm_dialog = None  # 单个移除前的确认弹窗
        self._place_mode = False
        self._place_kind = None  # 物品 key 或 "remove"
        self._place_preview = None
        self._ghosts = None  # 布局蓝图预览：[(类型, 物体)]
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
        if len(plan) == 1 and plan[0][1] and not plan[0][0].single and not plan[0][0].varies:
            return getattr(self, plan[0][0].store)  # 单一存放：直接给原列表，不复制
        out = []
        for k, whole in plan:
            if k.varies:
                out.extend(o for o in k.objects(self) if k.affords_now(o, use))
            elif whole:
                v = getattr(self, k.store)
                if k.single:
                    if v is not None:
                        out.append(v)
                else:
                    out.extend(v)
            else:
                out.extend(k.objects(self))
        return out

    def geometry_changed(self):
        """物体自己改变了路径前提（如矛扎进墙成了杆、被拔出）。"""
        self.geometry_version += 1
        self.world_version += 1

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

    def spawn(self, key, lx, ly):
        """程序生成一件物品（掉落物等），不走放置模式；腾不出位置返回 None。"""
        k = _kind(key)
        if not k.make_room(self):
            return None
        sk = k.seed_key or k.key
        seed = self._item_seeds.get(sk, 0)
        obj = k.make(self, lx, ly, seed)
        self._item_seeds[sk] = seed + 1
        if hasattr(obj, "_impact_cb"):
            obj._impact_cb = self._shake_impact
        k.add(self, obj)
        self.world_version += 1
        return obj

    def admit_item(self, k, obj):
        """把重建好的物体放进场上，种子计数跳过它的种子。"""
        sk = k.seed_key or k.key
        seed = int(getattr(obj, "_id", 0))
        self._item_seeds[sk] = max(self._item_seeds.get(sk, 0), seed + 1)
        if hasattr(obj, "_impact_cb"):
            obj._impact_cb = self._shake_impact
        k.add(self, obj)
        self.world_version += 1
        if k.geometry:
            self.geometry_version += 1
        self.update()

    def set_ghosts(self, ghosts):
        """显示或撤掉布局蓝图预览。"""
        self._ghosts = ghosts or None
        self._ops_key = None  # 定格时也重画
        self.update()

    def ghosting(self, k) -> bool:
        """正在预览，k 类场上的物品要画淡。"""
        return self._ghosts is not None and k.blueprint

    def _draw_ghosts(self, p):
        if self._ghosts is None:
            return
        p.save()
        p.setOpacity(GHOST_OPACITY)
        for k, o in self._ghosts:
            k.draw_ghost(self, p, o)
        p.restore()

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

    def grow_weapon(self, owner, x, y, style=0):
        """从 owner 身上长出一件武器（能长的物品类型提供）；长不出返回 None。"""
        for k in kinds():
            if getattr(k, "grows", False):
                obj = k.grow(self, x, y, owner, style)
                if obj is not None:
                    self.update()
                return obj
        return None

    def _forget(self, k, obj):
        k.drop(self, obj)
        if self._drag is not None and self._drag[1] is obj:
            self._drag = None

    def clear_kind(self, key, keep=False):
        """清掉一类物品；keep 时留下该类标记要留的（写过的珍珠）。"""
        k = _kind(key)
        objs = [o for o in k.objects(self) if not (keep and k.keeps(o))]
        for o in objs:
            self._forget(k, o)
            k.discard(self, o)
        k.cleared(self)
        if objs:
            self.world_version += 1
            if k.geometry:
                self.geometry_version += 1
        self._exit_place_mode()
        self.update()

    def clear_all_items(self):
        for k in kinds():
            self.clear_kind(k.key, keep=True)

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
        note = k.removal_note(obj)
        if note is None:
            self._remove_item(k, obj)
        else:
            self._confirm_remove(k, obj, note)
        return True

    def _remove_item(self, k, obj):
        if obj not in k.objects(self):
            return
        self._forget(k, obj)
        k.discard(self, obj)
        if k.geometry:
            self.geometry_version += 1
        self.world_version += 1
        self.update()

    def _confirm_remove(self, k, obj, note):
        """移除前弹窗展示内容，确认才移除；弹窗期间先退出移除模式，结束后接着进。"""
        if self._confirm_dialog is not None:
            return
        from PySide6.QtWidgets import QDialog

        from ..ui.widgets.dialogs import ConfirmDialog

        dlg = ConfirmDialog(
            t("dlg_confirm_title"),
            t(f"dlg_remove_{k.key}"),
            t("dlg_remove_yes"),
            t("dlg_kill_no"),
            parent=self,
            note=note or t("dlg_remove_empty"),
        )

        def done(result):
            self._confirm_dialog = None
            dlg.deleteLater()
            if result == QDialog.DialogCode.Accepted:
                self._remove_item(k, obj)
            self.enter_remove_mode()

        dlg.finished.connect(done)
        self._confirm_dialog = dlg
        self._exit_place_mode()
        dlg.place_center()
        dlg.show()
        dlg.activateWindow()

    def _secondary_target(self, pos):
        """右键点中的物体：有右键用法的物品类型里、光标够得着的那件。"""
        if pos is None:
            return None
        cx, cy = pos
        for k in _g().grab:
            if not k.secondary:
                continue
            best, bestd = None, 1e9
            for o in k.objects(self):
                if not k.grabbable(o):
                    continue
                d = k.grab_dist(o, cx, cy)
                if d <= o.rad + k.grab_pad and d < bestd:
                    best, bestd = o, d
            if best is not None:
                return k, best
        return None

    def _grab_target(self, pos):
        if pos is None:
            return None
        cx, cy = pos
        for k in _g().grab:
            best, bestd = None, 1e9
            for o in k.objects(self):
                if not k.grabbable(o):
                    continue
                d = k.grab_dist(o, cx, cy)
                if d <= o.rad + k.grab_pad and d < bestd:
                    best, bestd = o, d
            if best is not None:
                return k, best
        return None

    def held_item_at(self, pos) -> bool:
        """pos 处有没有猫手里拿着、能抢过来的东西。"""
        hit = self._grab_target(pos)
        return hit is not None and hit[1].state == ItemState.CARRIED

    def _begin_item_drag(self, pos) -> bool:
        hit = self._grab_target(pos)
        if hit is None:
            return False
        k, o = hit
        if o.state == ItemState.CARRIED:
            for pet in self.pets:
                if pet.body.hand_of(o) is None:
                    continue
                if pet.behavior is not None and not getattr(pet, "controlled", False):
                    pet.behavior.hands.snatched(o)
                else:
                    pet.body.release(o)
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
        for k in _g().late if late else _g().early:
            if d is not None and d[0] is k:
                self._step_item_drag(k)
            if k.always_tick or getattr(self, k.store):
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

    def _draw_item_overlays(self, p):
        for k in _g().stores:
            if self._present(k):
                k.draw_overlay(self, p)

    def _draw_items_under(self, p):
        self._draw_kinds(p, lambda k: k.draw_under(self, p))

    def _draw_items_behind(self, p):
        self._draw_kinds(p, lambda k: k.draw_behind(self, p))

    def _draw_items(self, p, layer):
        self._draw_kinds(p, lambda k: k.draw(self, p) if k.layer == layer else None)

    def _draw_kinds(self, p, fn):
        """逐类绘制，只画到地面线为止：窗口下延盖住任务栏时，地面以下的部分不露出来。"""
        p.save()
        p.setClipRect(QRectF(-1e4, -1e4, 2e4, self._HL + 1e4), Qt.ClipOperation.IntersectClip)
        for k in _g().stores:
            if self._present(k):
                fn(k)
        p.restore()

    def _draw_place_hint(self, p):
        s = self._scale
        p.fillRect(QRectF(0.0, 0.0, self.width() / s, self.height() / s), QColor(*CLICK_CATCHER))
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
