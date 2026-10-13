"""机会主义舌头补救层：空中掠果时抢射舌粘住收绳，消费方每 tick 驱动。"""
from __future__ import annotations
import math

from . import consts
from .reach import FETCH_IDEAL, FETCH_REEL, mouth_pos


class TongueSnatch:

    def __init__(self, pet):
        self.pet = pet
        self._prev_dist = None
        self._rescues = 0
        self._active = False
        self._timer = 0

    def update(self, goal):
        tg = self.pet.tongue
        if tg is None:
            return
        if self._active:
            self._maintain(tg, goal)
            return
        body = self.pet.body
        gx, gy = goal.pos()
        mox, moy = mouth_pos(self.pet)
        dist = math.hypot(gx - mox, gy - moy)
        prev = self._prev_dist
        self._prev_dist = dist
        if not self._should_fire(goal, body, tg, dist, prev):
            return
        if not tg.is_idle():
            return
        if not tg.try_acquire(self):
            return
        if not tg.shoot(mox, moy, gx, gy, hit=True, obj=goal.obj, owner=self):
            tg.release(self)
            return
        tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)
        self._active = True
        self._timer = 0
        self._rescues += 1

    def holding(self):
        """是否正持有补救舌头，需实查 owner 非仅看布尔。"""
        tg = self.pet.tongue
        return self._active and tg is not None and tg.owner is self

    def reset(self):
        self._rescues = 0
        self._clear()

    def _should_fire(self, goal, body, tg, dist, prev):
        if goal.contact != "grasp" or goal.obj is None or not goal.valid():
            return False
        if body.on_floor():
            return False
        if self._rescues >= consts.PLAN_SNATCH_MAX_TRIES:
            return False
        if prev is None or dist <= prev:
            return False
        if dist > tg.total:
            return False
        return True

    def _maintain(self, tg, goal):
        self._timer += 1
        if tg.owner is not self:
            self._clear()
            return
        if not goal.valid() or self._timer > consts.PLAN_SNATCH_TIMEOUT:
            self._handback(tg)
            return
        if tg.attached:
            tg.set_targets(ideal=FETCH_IDEAL, reel_rate=FETCH_REEL)

    def abort(self):
        tg = self.pet.tongue
        if tg is not None and tg.owner is self:
            self._handback(tg)
        else:
            self._clear()

    def _handback(self, tg):
        if tg.owner is self:
            tg.retract()
            tg.release(self)
        self.pet.body.suspended = False
        self._clear()

    def _clear(self):
        self._active = False
        self._timer = 0
        self._prev_dist = None
