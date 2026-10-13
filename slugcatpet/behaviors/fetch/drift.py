"""水里和失重时就近吃：游到 / 飘到附近能吃的东西旁抓住，就地啃。"""

from __future__ import annotations

import math

from ... import tuning
from ...items.base import EDIBLE
from .chew import Chew

CHASE_KICK_FAR = 60.0  # 失重追食物时离它这么远才蹬墙


class DriftForage:
    """挂在游泳、失重待机两个扩展点上；cooling() 为真时不去追新的。"""

    def __init__(self, fsm, cooling):
        self.fsm = fsm
        self.cooling = cooling
        self.chew = Chew()

    def swim(self) -> bool:
        b = self.fsm.body
        f = self._held_food()
        if f is not None:
            if self._chew(f):
                b.swim_target = (b.chunk0.x, b.chunk0.y - 4.0)
            return True
        e = self._nearest(tuning.SWIM_FETCH_SEEK_R, ready_only=False)
        if e is None:
            return False
        b.swim_target = (e.x, e.y)
        if math.hypot(e.x - b.chunk0.x, e.y - b.chunk0.y) < tuning.SWIM_FETCH_REACH:
            self._grab(e)
        return True

    def zerog(self) -> bool:
        fsm, b = self.fsm, self.fsm.body
        f = self._held_food()
        if f is not None:
            self._chew(f)
            return True
        e = self._nearest(math.inf, ready_only=True)
        if e is None:
            return False
        fsm.gfx.look_at = (e.x, e.y)
        dx, dy = e.x - b.chunk0.x, e.y - b.chunk0.y
        dist = math.hypot(dx, dy)
        if dist < tuning.SWIM_FETCH_REACH and self._grab(e):
            return True
        ux, uy = dx / dist, dy / dist
        b.zerog_swim(ux, uy, b.canJump > 0)
        if b.canJump > 0 and dist > CHASE_KICK_FAR:
            b.request_zerog_kick(ux, uy)
        fsm.run_tasks("zerog_aim", e.x, e.y)
        return True

    def _held_food(self):
        """没吃饱时手里第一个能吃的。"""
        fsm, b = self.fsm, self.fsm.body
        if b.food >= b.food_max:
            return None
        return next((o for o in b.held_items() if fsm.win.can_eat(o)), None)

    def _chew(self, f) -> bool:
        """啃一 tick；东西已不在手上的状态就松手，返回 False。"""
        b = self.fsm.body
        if f.state != "carried":
            b.release(f)
            return False
        self.chew.step(self.fsm.win, f)
        return True

    def _nearest(self, max_d, ready_only):
        """没吃饱、不在冷却时 max_d 内最近的能吃的；ready_only 时跳过眼下够不到的（飞着的蝙蝠）。"""
        fsm, b = self.fsm, self.fsm.body
        if b.food >= b.food_max or self.cooling():
            return None
        best, bd = None, max_d
        for f in fsm.items(EDIBLE):
            if f.state not in ("free", "hanging") or not fsm.win.can_eat(f):
                continue
            if ready_only and not getattr(f, "fetch_ready", True):
                continue
            d = math.hypot(f.x - b.chunk0.x, f.y - b.chunk0.y)
            if d < bd:
                bd, best = d, f
        return best

    def _grab(self, e) -> bool:
        b = self.fsm.body
        side = b.free_hand("r" if e.x >= b.chunk0.x else "l")
        if side is None:
            return False
        if getattr(e, "stuck_pos", None) is not None:
            e.stuck_pos = None  # 抓取瞬间剥离黏菌
        b.grab(e, side)
        self.chew.reset()
        return True
