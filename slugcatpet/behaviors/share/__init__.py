"""分享：吃够了、手里留着吃的，附近有想亲近的猫饿着，就拿过去放在它身边。"""

from __future__ import annotations

import math

from ... import tuning
from ...abilities.base import MOUTH, Param
from ...brain.hands import EAT_LATER
from ...brain.state import LIGHT, T_ACTIVITY, State
from ...items.base import EDIBLE
from ..base import Behavior

T_SHARE_CHECK = 30  # 每隔几 tick 看一次要不要分享
OFFER_TICKS = 24  # 走到后伸手递的时长
TIMEOUT = 900
SIDE_DX = 30.0  # 走到离对方这么远
NEAR_DX = 80.0  # 停下时离对方臀部这么近以内才递，否则对方挪开了，重新走


def pick_recipient(fsm, food, p):
    """想亲近、饿着、能吃 food、在同一层地面上走得到的猫；挑最想亲近的。"""
    b = fsm.body
    rain = fsm.win.rain
    best = None
    for o in fsm.social.others(fsm.win):
        ob = o.body
        w = fsm.social.pull(fsm.win, o)
        if (
            w < p.min_pull
            or not ob.on_floor()
            or not b.same_floor(ob)
            or abs(ob.chunk1.x - b.chunk1.x) > p.reach
            or fsm.social.state_of(o) not in ("IdleStand", "LieDown", "Sleep")
            or (rain.dangerous() and rain.keeps_out(ob.chunk1.x, ob.chunk1.y))
            or not fsm.social.wants_food(o, food)
            or fsm.social.held(o, "gift") is not None
        ):
            continue
        if best is None or w > best[0]:
            best = (w, o)
    return None if best is None else best[1]


class Share(State):
    name = "Share"
    tier = T_ACTIVITY
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self.to = None
        self.food = None
        self.offer = 0

    def enter(self):
        self.offer = 0
        self.fsm.social.claim(self.to, "gift", self.food, ttl=tuning.SHARE_HOLD)
        self.fsm.body.set_posture(True)
        self._go()

    def _go(self):
        """走到对方靠我这一侧的身边。"""
        b = self.fsm.body
        ob = self.to.body
        side = 1.0 if b.chunk1.x >= ob.chunk1.x else -1.0
        b.walk_to(ob.chunk1.x + side * SIDE_DX)

    def _valid(self):
        fsm = self.fsm
        return (
            fsm.body.hand_of(self.food) is not None
            and self.to in fsm.social.others(fsm.win)
            and self.to.body.on_floor()
            and fsm.body.same_floor(self.to.body)
            and fsm.social.wants_food(self.to, self.food)
        )

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        if not self._valid() or fsm.timer >= TIMEOUT:
            self._end()
            return
        ob = self.to.body
        head = (ob.chunk0.x, ob.chunk0.y)
        if self.offer == 0:
            if b.is_moving():
                return
            if abs(b.chunk1.x - ob.chunk1.x) > NEAR_DX:  # 走到了，对方却挪开了
                self._go()
                return
        b.stop_walk()
        b.facing = 1 if ob.chunk1.x > b.chunk1.x else -1
        fsm.gfx.look_at = head
        side = b.hand_of(self.food)
        fsm.gfx.hand_aim[side] = head
        self.offer += 1
        if self.offer < OFFER_TICKS:
            return
        fsm.hands.put_down(self.food)
        self.food.vx = math.copysign(tuning.SHARE_TOSS_VX, ob.chunk1.x - b.chunk1.x)
        fsm.social.claim(self.to, "gift", self.food, ttl=tuning.SHARE_HOLD)  # 从放下起重新计时
        fsm.social.bonds.nudge(fsm.win, self.to, tuning.BOND_SHARE)
        self._end()

    def _end(self):
        self.brk()
        self.fsm.settle()

    def brk(self):
        fsm = self.fsm
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        if self.to is not None and fsm.body.hand_of(self.food) is not None:
            fsm.social.release(self.to, "gift")  # 没送出去：放掉留给对方的预约
        self.to = None
        self.food = None


class ShareBehavior(Behavior):
    key = "share"
    title = {"zh": "分享", "en": "Share food"}
    doc = (
        "自己吃够了（够冬眠）、手里留着吃的，附近有想亲近的猫（看亲和和关系）饿着、也能吃这个，"
        "就拿过去放在它身边，留给它一阵子。两只猫关系变好。"
    )
    requires = (MOUTH, EDIBLE)
    params = {
        "min_pull": Param(0.4, -1.0, 1.0, "想靠近对方至少这么多才分享（亲和与关系换算，见 social.pull）"),
        "chance": Param(0.3, 0.0, 1.0, "每次检查到能分享时真去分享的概率"),
        "reach": Param(700.0, 0.0, 5000.0, "只找这么远以内的"),
        "cooldown": Param(1200, 0, 100000, "分享过一次后多久再考虑"),
    }

    def mount(self, fsm):
        st = fsm.add_state(Share)
        b = fsm.body
        p = self.p
        self.check = 0
        self.cooldown = 0

        def rule(cursor):
            if self.cooldown > 0:
                self.cooldown -= 1
                return
            self.check = (self.check + 1) % T_SHARE_CHECK
            if self.check or fsm.state != "IdleStand" or fsm.grab.active or fsm._zerog() or b.swimming:
                return
            food = fsm.hands.held(EAT_LATER)
            if food is None or b.food < b.food_hibernate or not b.on_floor():
                return
            to = pick_recipient(fsm, food, p)
            if to is None or fsm.rng.random() >= p.chance:
                return
            st.to, st.food = to, food
            self.cooldown = int(p.cooldown)
            fsm._transition("Share")

        fsm.register_rule(rule)
