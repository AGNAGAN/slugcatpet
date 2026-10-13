"""石头：猫生气时捡起来扔；被扔中的猫会晕，光标会被弹开。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPolygonF

from ...core.units import clampf, lerp
from ...rendering.primitives import draw_stone, draw_stone_trail
from ..base import CARRYABLE, THROWABLE, ItemKind
from ..state import ItemState
from .model import Stone

STONE_COLOR = (74, 76, 82)
STONE_DRAW_SCALE = 0.7
STONE_STUN_SPEED = 8.0
STONE_STUN_TICKS = 80
STONE_KNOCKBACK = 0.5
STONE_TRAIL_MIN_SPEED = 6.0
STONE_TRAIL_LEN_K = 1.6
STONE_TRAIL_LEN_MAX = 42.0
STONE_TRAIL_HALFW = 3.0
STONE_TRAIL_ALPHA = 90
CURSOR_STUN_PAD = 8.0
CURSOR_STUN_LOCK = 80
CURSOR_KNOCK_SPEED = 26.0  # 光标被石头砸中后的弹开初速（逻辑 px/tick）

_ICON_FACET = QColor(70, 76, 66, 160)


class StoneKind(ItemKind):
    key = "stone"
    store = "stones"
    affords = frozenset({THROWABLE, CARRYABLE})
    collides = True
    grab_pad = 7.0
    grab_rank = 1
    dead_state = ItemState.GONE

    def make(self, win, lx, ly, seed):
        return Stone(lx, ly, seed=seed)

    def drop(self, win, s):
        for pet in win.pets:
            if s is getattr(pet.body, "carried_stone", None):
                rs = getattr(pet.body, "release_stone", None)
                if rs is not None:
                    rs()
        s.state = ItemState.GONE

    def on_grab(self, s):
        s.unfetchable = False
        s.fetch_fails = 0
        s.fling = False

    def on_release(self, win, s):
        if s.state == ItemState.MOUSE:
            s.state = ItemState.FREE
            s.fling = True
            s.spin = clampf(s.vx * 2.0, -40.0, 40.0) * lerp(0.05, 1.0, s.room_gravity)

    def after_step(self, win):
        _hit_pets(win)
        _hit_cursor(win)

    def draw(self, win, p):
        ts = win._ts
        for s in win.stones:
            x = s.last_x + (s.x - s.last_x) * ts
            y = s.last_y + (s.y - s.last_y) * ts
            rot = s.last_rotation + (s.rotation_deg - s.last_rotation) * ts
            if (s.fling or s.thrown_by_cat) and s.state == ItemState.FREE:
                sp = math.hypot(s.vx, s.vy)
                if sp > STONE_TRAIL_MIN_SPEED:
                    length = min(sp * STONE_TRAIL_LEN_K, STONE_TRAIL_LEN_MAX)
                    draw_stone_trail(
                        p,
                        x,
                        y,
                        s.vx / sp,
                        s.vy / sp,
                        length,
                        STONE_TRAIL_HALFW,
                        STONE_COLOR,
                        STONE_TRAIL_ALPHA,
                    )
            if s.vibrate > 0:
                x += (s.vibrate % 3) - 1.0
                y += ((s.vibrate // 2) % 3) - 1.0
            draw_stone(p, win.atlas, x, y, rot, s.frame, color=STONE_COLOR, scale=STONE_DRAW_SCALE)

    def draw_hint(self, win, p, cx, cy):
        p.save()
        p.setOpacity(0.5)
        draw_stone(
            p,
            win.atlas,
            cx,
            cy,
            0.0,
            "Pebble" + str(1 + win.item_seed(self) % 14),
            color=STONE_COLOR,
            scale=STONE_DRAW_SCALE,
        )
        p.restore()

    def paint_icon(self, p, r, atlas):
        from ...ui.widgets.iconkit import ICON_GREY, pen

        cx, cy = r.center().x(), r.center().y()
        w, h = r.width(), r.height()
        ox, oy = cx, cy + h * 0.04
        pts = [(-0.54, 0.12), (-0.30, -0.40), (0.10, -0.46), (0.54, -0.12), (0.46, 0.34), (-0.12, 0.46)]
        poly = [QPointF(ox + dx * w * 0.56, oy + dy * h * 0.50) for dx, dy in pts]
        p.setPen(pen(ICON_GREY, max(1.8, w * 0.13), cap=False))
        p.setBrush(ICON_GREY)
        p.drawPolygon(QPolygonF(poly))
        p.setPen(pen(_ICON_FACET, max(1.2, w * 0.07)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(ox - w * 0.20, oy - h * 0.16), QPointF(ox + w * 0.08, oy - h * 0.24))


def _hit_pets(win):
    for pet in win.pets:
        if pet.behavior is None:
            continue
        b = pet.body
        for s in win.stones:
            if not s.fling or s.state != ItemState.FREE:
                continue
            sp = math.hypot(s.vx, s.vy)
            if sp < STONE_STUN_SPEED:
                continue
            for c in (b.chunk0, b.chunk1):
                if math.hypot(s.x - c.x, s.y - c.y) < s.rad + c.rad:
                    if pet.behavior.apply_stun(STONE_STUN_TICKS):
                        c.vx += s.vx * STONE_KNOCKBACK
                        c.vy += s.vy * STONE_KNOCKBACK
                        s.deflect(win._stun_rng)
                        s.fling = False
                    break


def _hit_cursor(win):
    if win.cursor_hijack is not None or win.behavior is None:
        return
    cur = win.cursor_logical()
    if cur is None:
        return
    cx, cy = cur
    for s in win.stones:
        if not s.thrown_by_cat or s.state != ItemState.FREE:
            continue
        # 按本 tick 的位移线段判命中，高速石头不会一帧穿过光标
        ax, ay = s.last_x, s.last_y
        dx, dy = s.x - ax, s.y - ay
        l2 = dx * dx + dy * dy
        u = clampf(((cx - ax) * dx + (cy - ay) * dy) / l2, 0.0, 1.0) if l2 > 1e-9 else 1.0
        if math.hypot(cx - (ax + dx * u), cy - (ay + dy * u)) < s.rad + CURSOR_STUN_PAD:
            k = CURSOR_KNOCK_SPEED / (math.hypot(s.vx, s.vy) or 1.0)
            knock = (s.vx * k, s.vy * k - 6.0)
            win.start_cursor_hijack(cx, cy, lock_ticks=CURSOR_STUN_LOCK, knock_v=knock)
            s.deflect(win._stun_rng)
            s.thrown_by_cat = False
            break


KIND = StoneKind()
