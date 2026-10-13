"""内置行为状态：取果 / 顺手捡个果子留着。"""

from __future__ import annotations

from ...brain.hands import EAT_LATER
from ...brain.state import T_ACTIVITY, T_NEED, State, LIGHT

T_FETCH_COOLDOWN = 200  # 取果失败后的冷却（tick）


class FetchFruit(State):
    name = "FetchFruit"
    tier = T_NEED
    energy = LIGHT
    fetcher = None  # 当前取果器
    cooldown = 0  # 放弃后的冷却
    keep = False  # 拿到后一律留着不吃
    carry_chance = 0.0  # 有点饿时拿到先揣着、过会儿再吃的概率（行为参数写入）
    _keep = False  # 本次拿到后留着不吃

    def saved_food(self):
        """手里留着、这只猫能吃的东西。"""
        fsm = self.fsm
        f = fsm.hands.held(EAT_LATER)
        return f if f is not None and fsm.traits.eats(f) else None

    def wants_saved(self):
        """该吃手里留着的了：真饿了，或者已经揣够久。"""
        hs = self.fsm.hands
        return self.saved_food() is not None and (hs.hungry_urgent() or hs.snack_due())

    def hands_needed(self):
        return "any" if not self.keep and self.wants_saved() else "one"

    def enter(self):
        fsm = self.fsm
        from .fetcher import FruitFetcher

        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        eat_saved = not self.keep and self.wants_saved()
        self._keep = self.keep or (
            not eat_saved and not fsm.hands.hungry_urgent() and fsm.rng.random() < self.carry_chance
        )
        self.fetcher = FruitFetcher(fsm.win, fsm.planner, fsm.traits, keep=self._keep, hands=fsm.hands)
        if eat_saved:
            self.fetcher.start_with(self.saved_food())

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if self.fetcher is None:
            fsm._transition("IdleStand")
            return
        done = self.fetcher.update()
        if self.fetcher.giveup:
            fsm.release_organs()
            self._fetch_release()
            self.cooldown = T_FETCH_COOLDOWN
            fsm._transition("IdleStand")
        elif done:
            fsm.release_organs()
            self._fetch_release()
            nxt = None
            if not self._keep and fsm.body.food >= fsm.body.food_max:
                nxt = fsm.ask("after_meal", None)
            fsm._transition(nxt or "IdleStand")

    def brk(self):
        fsm = self.fsm
        fsm.release_organs()
        self._fetch_release()

    def _fetch_release(self):
        """收尾：已经拿到手的留着待会儿吃；本来就要揣着的，等一阵再吃。"""
        fsm = self.fsm
        if self.fetcher is not None:
            self.fetcher.release()
            f = self.fetcher.held_target()
            if f is not None:
                if getattr(f, "stalk", None) is not None:
                    f.stalk = None
                fsm.hands.adopt(f, EAT_LATER)
                if self._keep:
                    fsm.hands.start_snack_wait()
        fsm.body.arm_aim["l"] = None
        fsm.body.arm_aim["r"] = None
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        self.fetcher = None


class Forage(FetchFruit):
    """吃饱时顺手再捡一个，留着饿了再吃。"""

    name = "Forage"
    tier = T_ACTIVITY
    keep = True
