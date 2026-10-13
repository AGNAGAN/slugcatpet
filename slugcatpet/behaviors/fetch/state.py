"""内置行为状态：取果。"""
from __future__ import annotations

from ...brain.state import T_NEED, State, LIGHT

T_FETCH_COOLDOWN = 200           # 取果失败后的冷却（tick）


class FetchFruit(State):
    name = "FetchFruit"
    tier = T_NEED
    energy = LIGHT
    fetcher = None               # 当前取果器
    cooldown = 0                 # 放弃后的冷却

    def enter(self):
        fsm = self.fsm
        from .fetcher import FruitFetcher
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        self.fetcher = FruitFetcher(fsm.win, fsm.planner, fsm.traits)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if self.fetcher is None:
            fsm._transition("IdleStand")
            return
        done = self.fetcher.update()
        if self.fetcher.giveup:
            fsm._break_tongue()
            self._fetch_release()
            self.cooldown = T_FETCH_COOLDOWN
            fsm._transition("IdleStand")
        elif done:
            fsm._break_tongue()
            self._fetch_release()
            fsm._transition("IdleStand")

    def brk(self):
        fsm = self.fsm
        fsm._break_tongue()
        self._fetch_release()

    def _fetch_release(self):
        fsm = self.fsm
        if self.fetcher is not None:
            self.fetcher.release()
        if fsm.body.carried_fruit is not None:
            fsm.body.carried_fruit.stalk = None
            fsm.body.carried_fruit.state = "free"
            fsm.body.carried_fruit.held_by_hand = None
            fsm.body.release_fruit()
        fsm.body.arm_aim["l"] = None
        fsm.body.arm_aim["r"] = None
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        self.fetcher = None
