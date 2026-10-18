"""玩珍珠的状态：走过去拿起 → 拿着晃一会儿 → 放下或抛开。"""

from __future__ import annotations

from ...brain.skills import motor
from ...brain.skills.throw import WeaponPickup
from ...brain.state import LIGHT, T_ACTIVITY, State
from ...core.creature import Throw
from ...items.base import TOY

TOSS_UP = 0.8  # 抛出时竖直初速占 toss_speed 的比例（向上）
LOOK_PROB = 0.01  # 拿着时每 tick 低头看一眼的概率
LOOK_TICKS = 40


class PearlPlay(State):
    name = "PearlPlay"
    mood = "pearl_play"
    tier = T_ACTIVITY
    energy = LIGHT
    hands = "one"
    p = None

    def enter(self):
        fsm = self.fsm
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        self.pearl = None
        self.timer = 0
        self.hold_for = 0
        self.look = 0
        self.pick = WeaponPickup(fsm, lambda s, d: d, self.name, use=TOY, slot="pearl")
        self.found = self.pick.select()

    def tick(self, cursor, disturbed):
        if not self.found:
            self._finish()
        elif self.pearl is None:
            self._approach()
        else:
            self._carry()

    def _approach(self):
        fsm = self.fsm
        if not self.pick.available():
            self._finish()
            return
        r = self.pick.update()
        if r == "got":
            self.pearl = self.pick.target
            self.timer = 0
            self.hold_for = fsm.rng.randint(int(self.p.hold_min), int(self.p.hold_max))
        elif r in ("failed", "lost"):
            self._finish()

    def _carry(self):
        fsm, b = self.fsm, self.fsm.body
        if b.hand_of(self.pearl) is None:
            self._finish()
            return
        self.timer += 1
        if self.look > 0:
            self.look -= 1
            fsm.gfx.look_at = (self.pearl.x, self.pearl.y)
        elif fsm.rng.random() < LOOK_PROB:
            self.look = LOOK_TICKS
        if not b.is_moving() and fsm.rng.random() < self.p.stroll_prob:
            motor.wander(fsm)
        if self.timer >= self.hold_for:
            self._let_go()
            self._finish()

    def _let_go(self):
        """放下，或朝面向的一侧随手抛开。"""
        fsm, b, g = self.fsm, self.fsm.body, self.fsm.gfx
        obj = self.pearl
        side = b.hand_of(obj)
        h = g.hands[0 if side == "l" else 1]
        fsm.hands.put_down(obj)
        if fsm.rng.random() >= self.p.toss_prob or not b.on_floor():
            return
        ux = 1 if b.facing >= 0 else -1
        sp = self.p.toss_speed
        obj.x, obj.y = h.x, h.y
        obj.last_x, obj.last_y = h.x, h.y
        obj.vx = ux * sp * fsm.rng.uniform(0.5, 1.0)
        obj.vy = -sp * TOSS_UP * fsm.rng.uniform(0.6, 1.0)
        obj.on_thrown(Throw(b, ux))
        g.throw_object(side, obj)

    def _finish(self):
        self._stop()
        self.fsm._transition("IdleStand")

    def _stop(self):
        b = self.fsm.body
        b.stop_walk()
        b.arm_aim["l"] = None
        b.arm_aim["r"] = None

    def brk(self):
        self._stop()

    def kill_break(self):
        self._stop()
