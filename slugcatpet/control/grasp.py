"""手动控制时的手部操作：拾取、丢下、双击换手、投掷、站定长按吃、按住啃尸体，以及拉住、背上、骑上别的猫。"""

from __future__ import annotations

import math

from ..behaviors.fetch.chew import Chew
from ..brain.social.carry import BACK, HAND
from ..items.base import CARRYABLE

PICKUP_BUFFER = 5  # 拾取 / 投掷键的输入缓冲帧
SWITCH_WINDOW = 15  # 双击换手的间隔上限
NO_PICKUP_ON_RELEASE = 20
DROP_HOLD_DOWN = 5  # 丢下需先按住下的帧数
FORBID_TICKS = 40  # 丢下 / 扔出后多久不能再捡
DONT_GRAB_AFTER_THROW = 15
PICKUP_RANGE = 40.0  # 候选物离上身的最远距离（加物体半径）
FACING_BONUS = 10.0  # 面朝一侧的候选物优先
EAT_COUNTER_MAX = 40
EAT_BITE_INTERVAL = 15
EAT_POSE_FULL = 20  # 计数降到这里时手完全进入啃食姿态
EAT_STILL_SPEED = 3.6
TO_BACK_TICKS = 20  # 拉着猫时长按拾取这么久背到背上；背上有猫、手空着时长按拿回手里
MOUNT_DX = 18.0  # 空中臀离别的猫的上身横向这么近
MOUNT_DY = 30.0  # 且在它上身上方这么高以内，按拾取就骑上去


class GraspControl:
    def __init__(self, pet):
        self.pet = pet
        self.want_pickup = 0
        self.want_throw = 0
        self.switch_counter = 0
        self.no_pickup_on_release = 0
        self.dont_grab = 0
        self.eat_counter = EAT_COUNTER_MAX
        self.meat = Chew()
        self.candidate = None
        self.cat = None  # 附近能拉住的猫
        self.hold_pckp = 0
        self.forbidden = {}

    def update(self):
        b = self.pet.body
        inp = b._ctrl_input
        if inp is None or b.dead or b.stun > 0:
            return
        i0, i1 = inp[0], inp[1]
        carry = self.pet.window.social.carry
        if carry.link_of(self.pet) is not None:
            return  # 被带着时只能按跳下来
        press = i0.pckp and not i1.pckp
        self.hold_pckp = self.hold_pckp + 1 if i0.pckp else 0
        if self.hold_pckp == TO_BACK_TICKS:
            self._swap_cat(carry)
        still = i0.x == 0 and i0.y == 0 and not i0.jmp and not i0.thrw and b.submersion < 0.5

        if press and b.switch_hands == 0.0:
            if b.holding_any():
                if self.switch_counter == 0:
                    self.switch_counter = SWITCH_WINDOW
                else:
                    b.start_switch_hands()
                    self.want_pickup = 0
                    self.no_pickup_on_release = NO_PICKUP_ON_RELEASE

        meat = next(
            (
                o
                for o in b.held_items()
                if getattr(o, "carcass", False) and (self.pet.can_eat(o) or self.meat.counter)
            ),
            None,
        )
        if meat is not None:
            self.meat.hold_meat(self.pet, meat, i0.pckp)
            self._update_eat(False, None)
        else:
            food = next((o for o in b.held_items() if self.pet.can_eat(o)), None)
            self._eat_input(inp, food, press, still)

        self._tick_forbidden()
        self.candidate = self._pickup_candidate() if self.dont_grab < 1 else None
        self.cat = self._cat_candidate(carry) if self.dont_grab < 1 else None
        for k in ("switch_counter", "want_pickup", "want_throw", "no_pickup_on_release", "dont_grab"):
            v = getattr(self, k)
            if v > 0:
                setattr(self, k, v - 1)

        if i0.thrw and not i1.thrw:
            self.want_throw = PICKUP_BUFFER
        if self.want_throw > 0:
            if self._throw_cat(carry, i0):
                self.want_throw = 0
            else:
                for obj in b.held_items():
                    self._throw(obj, i0)
                    self.want_throw = 0
                    break

        if self.want_pickup > 0:
            self._do_pickup(inp)

    def _eat_input(self, inp, food, press, still):
        """站定长按拾取键吃手里的东西；轻点拾取键换成去捡别的。"""
        b = self.pet.body
        i0 = inp[0]
        eating = False
        if still:
            if food is not None and self.no_pickup_on_release < 1:
                if not i0.pckp:
                    j = 1
                    while j < 10 and inp[j].pckp:
                        j += 1
                    if 1 < j < 10:
                        self._pickup_pressed()
            elif press:
                self._pickup_pressed()
            c0 = b.chunk0
            if (
                food is not None
                and self.want_pickup < 1
                and (i0.pckp or self.eat_counter <= EAT_BITE_INTERVAL)
                and math.hypot(c0.vx, c0.vy) < EAT_STILL_SPEED
            ):
                eating = True
                self.pet.gfx.look_at = (food.x, food.y)
                if b.food < b.food_max and self.eat_counter < 1:
                    self.eat_counter = EAT_BITE_INTERVAL
                    self._bite(food)
        elif press:
            self._pickup_pressed()
        self._update_eat(eating, food if b.hand_of(food) else None)

    def _pickup_pressed(self):
        self.want_pickup = PICKUP_BUFFER

    def _update_eat(self, eating, food):
        """啃食计数：边吃边减，每到底咬一口；不吃时慢慢回满。手随计数抬到嘴边。"""
        b = self.pet.body
        if eating and self.eat_counter > 0:
            self.eat_counter -= 1
        elif not eating and self.eat_counter < EAT_COUNTER_MAX:
            self.eat_counter += 1
        if food is None:
            return
        c = self.eat_counter
        k = (
            0.0
            if c >= EAT_COUNTER_MAX
            else min(1.0, (EAT_COUNTER_MAX - c) / (EAT_COUNTER_MAX - EAT_POSE_FULL))
        )
        b.set_eat_raise(food, k)

    def _bite(self, food):
        b = self.pet.body
        self.pet.gfx.bite(b.hand_of(food))
        b.consume(food, self.pet.traits.nourishment(food))

    def _tick_forbidden(self):
        for k in [k for k, v in self.forbidden.items() if v <= 1]:
            del self.forbidden[k]
        for k in self.forbidden:
            self.forbidden[k] -= 1

    def _forbid(self, obj):
        self.forbidden[id(obj)] = FORBID_TICKS

    def _pickup_candidate(self):
        """上身附近可捡的物体，近者优先，面朝一侧再加分。"""
        b = self.pet.body
        c0 = b.chunk0
        best, best_score = None, math.inf
        for obj in self.pet.items_affording(CARRYABLE):
            if obj.state not in ("free", "hanging", "stuck") or id(obj) in self.forbidden:
                continue
            if not b.can_hold(obj):
                continue
            d = math.hypot(obj.x - c0.x, obj.y - c0.y)
            if d > obj.rad + PICKUP_RANGE:
                continue
            score = d
            if (obj.x < c0.x) == (b.facing < 0):
                score -= FACING_BONUS
            if score < best_score:
                best, best_score = obj, score
        return best

    def _cat_candidate(self, carry):
        """上身附近能拉住的猫：(猫, 距离)，没有为 None。"""
        b = self.pet.body
        c0 = b.chunk0
        best = None
        for o in self.pet.window.social.others(self.pet):
            if id(o) in self.forbidden or not carry.can_take(self.pet, o, carry.pick_mode(self.pet)):
                continue
            d = min(math.hypot(c.x - c0.x, c.y - c0.y) - c.rad for c in (o.body.chunk0, o.body.chunk1))
            if d <= PICKUP_RANGE and (best is None or d < best[1]):
                best = (o, d)
        return best

    def _mount_target(self, carry):
        """空中时脚下正对着上身的猫。"""
        b = self.pet.body
        c1 = b.chunk1
        for o in self.pet.window.social.others(self.pet):
            h = o.body.chunk0
            if (
                abs(h.x - c1.x) < MOUNT_DX
                and 0.0 < h.y - c1.y < MOUNT_DY
                and carry.can_take(o, self.pet, BACK)
            ):
                return o
        return None

    def _swap_cat(self, carry):
        """长按拾取：手里的猫背到背上，或背上的猫拿回空着的手里。"""
        lk = carry.carrying(self.pet, HAND) or carry.carrying(self.pet, BACK)
        if lk is not None and carry.move(lk, BACK if lk.mode == HAND else HAND):
            self.no_pickup_on_release = NO_PICKUP_ON_RELEASE

    def _throw_cat(self, carry, i0):
        """扔手里拉着的猫；手里没有能扔的时扔背上的。"""
        b = self.pet.body
        lk = carry.carrying(self.pet, HAND)
        if lk is None and b.held_throwable() is None:
            lk = carry.carrying(self.pet, BACK)
        if lk is None:
            return False
        carry.throw(lk.rider, b.throw_direction(i0.x), i0.x, i0.y)
        self._forbid(lk.rider)
        self.dont_grab = DONT_GRAB_AFTER_THROW
        return True

    def _do_pickup(self, inp):
        b = self.pet.body
        carry = self.pet.window.social.carry
        if all(inp[k].y == -1 for k in range(DROP_HOLD_DOWN)):
            lk = carry.carrying(self.pet, HAND)
            if lk is not None:
                self.want_pickup = 0
                carry.drop(lk.rider)
                self._forbid(lk.rider)
                return
            held = b.held_items()
            if held:
                self.want_pickup = 0
                obj = held[0]
                if getattr(obj, "stalk", None) is not None:
                    obj.stalk = None
                b.release(obj, to_free=True)
                self._forbid(obj)
                return
            lk = carry.carrying(self.pet, BACK)
            if lk is not None and b.on_floor():
                self.want_pickup = 0
                carry.drop(lk.rider)
                self._forbid(lk.rider)
            return
        if not b.on_floor() and not b.on_pole:
            o = self._mount_target(carry)
            if o is not None and carry.take(o, self.pet, BACK):
                self.want_pickup = 0
                return
        obj = self.candidate
        cat = self.cat
        if cat is not None and (
            obj is None or cat[1] < math.hypot(obj.x - b.chunk0.x, obj.y - b.chunk0.y) - obj.rad
        ):
            if carry.take(self.pet, cat[0], carry.pick_mode(self.pet)):
                self.want_pickup = 0
                self.no_pickup_on_release = NO_PICKUP_ON_RELEASE
                self.cat = None
            return
        if obj is None:
            return
        side = b.free_hand()
        if side is None:
            return
        if getattr(obj, "stuck_pos", None) is not None:
            obj.stuck_pos = None
        b.grab(obj, side)
        self.switch_counter = 0
        self.want_pickup = 0
        self.no_pickup_on_release = NO_PICKUP_ON_RELEASE
        self.candidate = None

    def _throw(self, obj, i0):
        b = self.pet.body
        side = b.hand_of(obj)
        d = b.throw_direction(i0.x)
        tossed = getattr(obj, "pierces", False) and b.stats.spear_toss
        if getattr(obj, "throwable", False) and not tossed:
            from ..brain.skills.throw import throw_speed

            b.throw(obj, d, throw_speed(self.pet), up=3.0, dir_y=_vertical_throw(b, i0))
            self.pet.gfx.blink = 15
        else:
            ang, power = 45.0, 4.0
            if i0.x != 0 and i0.y == 0:
                ang, power = 70.0, 12.5
            elif i0.x != 0 and i0.y == 1:
                ang, power = 25.0, 9.0
            elif i0.x == 0 and i0.y == 1:
                ang, power = 5.0, 8.0
            b.toss(obj, d, ang, power * 2.0)
        self.pet.gfx.throw_object(side, obj)
        self.dont_grab = DONT_GRAB_AFTER_THROW
        self._forbid(obj)


def _vertical_throw(b, i0):
    """后空翻中只按上下、或失重时按了上下，返回竖直出手方向（y↓），否则返回 0。"""
    if i0.y == 0:
        return 0
    if (b.animation == "Flip" and i0.x == 0) or b.bodyMode == "ZeroG":
        return -i0.y
    return 0
