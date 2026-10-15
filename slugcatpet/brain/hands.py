"""手部管家：记每样手持物为什么拿着，切状态时按需腾手，平时处理拿着东西本身该发生的事。"""

from __future__ import annotations

import math

from .. import tuning
from ..core.creature import Throw
from .skills import motor

EAT_LATER = "eat_later"  # 留着待会儿吃
WEAPON = "weapon"  # 拿着防身 / 生气时扔
DROP_ORDER = (EAT_LATER, WEAPON)  # 腾手时先放下谁

PUT_DOWN_FORBID = 240  # 放下后多久不再把它当目标
CALM_DROP_DELAY = (120, 360)  # 消气后过多久把石头放下
FIDGET_PROB = 1.0 / 400.0  # 站着发呆时每 tick 摆弄手里东西的概率
FIDGET_WALK = 0.4  # 摆弄时拿着东西挪个地方的比例
FIDGET_SWITCH = 0.3  # 换手的比例，其余是低头看看
FIDGET_LOOK = (30, 70)  # 低头看手里东西的时长
DRAG_THROW_WINDOW = 30  # 被抓后这么多帧内可能扔石头挣脱
DRAG_THROW_PROB = 0.06  # 窗口内每 tick 扔的概率
SMACK_SPEED = 20.0  # 砸光标时石头的出手速度
DRAG_SHAKE_SPEED = 2.2 * tuning.TEMPER_SWING_SPEED  # 被甩到这么快就脱手
SNATCH_TUG = 12  # 被抢时手追着光标拽的帧数


def can_wield(body, obj, hyst=0.0, hunting=False) -> bool:
    """这只猫眼下肯不肯把 obj 当武器：扎得进的对光标只在好感很低时用、打猎随时用，只能抛矛的猫不用。"""
    if not getattr(obj, "pierces", False):
        return True
    return not body.stats.spear_toss and (hunting or body.temper < tuning.SPEAR_TEMPER + hyst)


class HandKeeper:
    def __init__(self, fsm):
        self.fsm = fsm
        self.body = fsm.body
        self._purpose = {}  # id → (obj, 理由)
        self._forbid = {}  # id → 剩余帧
        self._calm_drop = 0
        self._look = 0
        self._look_obj = None
        self._drag_ticks = 0
        self._tug = 0
        self._tug_side = None
        self._snack_wait = 0  # 留着吃的东西还要等多久才吃

    # 查询

    def purpose_of(self, obj):
        e = self._purpose.get(id(obj))
        return None if e is None or e[0] is not obj else e[1]

    def held(self, purpose):
        """按主手顺序第一个以 purpose 拿着的东西。"""
        for obj in self.body.held_items():
            if self.purpose_of(obj) == purpose:
                return obj
        return None

    def forbidden(self, obj) -> bool:
        return id(obj) in self._forbid

    def hungry_urgent(self) -> bool:
        b = self.body
        return b.food < b.food_max * tuning.HUNGER_URGENT_FRAC

    def snack_due(self) -> bool:
        """留着吃的东西等够了没有。"""
        return self._snack_wait <= 0

    def start_snack_wait(self):
        self._snack_wait = self.fsm.rng.randint(tuning.SNACK_DELAY_MIN, tuning.SNACK_DELAY_MAX)

    # 拿起 / 放下

    def adopt(self, obj, purpose):
        """把手里的 obj 记为以 purpose 拿着；不在手里则忽略。"""
        if obj is not None and self.body.hand_of(obj) is not None:
            self._purpose[id(obj)] = (obj, purpose)

    def put_down(self, obj):
        """就地放下，一段时间内不再把它当目标。"""
        b = self.body
        if b.hand_of(obj) is None:
            return
        if getattr(obj, "stalk", None) is not None:
            obj.stalk = None
        b.release(obj, to_free=True)
        obj.vx, obj.vy = b.chunk0.vx * 0.5, b.chunk0.vy * 0.5
        self._purpose.pop(id(obj), None)
        self._forbid[id(obj)] = PUT_DOWN_FORBID

    def make_room(self, need):
        """腾出 need 要求的空手：one=至少一只，free=两只。"""
        want = {"one": 1, "free": 2}.get(need, 0)
        b = self.body
        held = b.held_items()
        order = sorted(held, key=lambda o: _drop_rank(self.purpose_of(o)))
        while 2 - len(held) < want and order:
            obj = order.pop(0)
            self.put_down(obj)
            held.remove(obj)

    def on_enter(self, state):
        need = state.hands_needed() if state is not None else "any"
        if need != "any":
            self.make_room(need)

    # 每 tick

    def tick(self, cursor):
        b = self.body
        for k, (o, _) in list(self._purpose.items()):
            if b.hand_of(o) is None:
                del self._purpose[k]
        for o in b.held_items():
            if id(o) not in self._purpose:
                self._purpose[id(o)] = (o, self._infer(o))
        for k in [k for k, v in self._forbid.items() if v <= 1]:
            del self._forbid[k]
        for k in self._forbid:
            self._forbid[k] -= 1
        if self.held(EAT_LATER) is None:
            self._snack_wait = 0
        elif self._snack_wait > 0:
            self._snack_wait -= 1
        st = self.fsm.state
        if st == "Dragged":
            self._drag_tick(cursor)
        else:
            self._drag_ticks = 0
        if st == "IdleStand" and not self.fsm._zerog():
            self._calm_tick()
            self._fidget_tick()
        else:
            self._look = 0
        self._tug_tick(cursor)

    def _infer(self, obj):
        """自己拿起的东西的理由：能吃的留着吃，能扔的当武器，其余没用。"""
        if self.fsm.win.can_eat(obj):
            return EAT_LATER
        if getattr(obj, "throwable", False):
            return WEAPON
        return None

    def _calm_tick(self):
        """放下没用的东西；不再记恨就把武器放下。"""
        junk = self.held(None)
        if junk is not None:
            self.put_down(junk)
        stone = self.held(WEAPON)
        b = self.body
        if stone is None or (
            b.temper < tuning.ARM_TEMPER + tuning.ARM_TEMPER_HYST
            and can_wield(b, stone, tuning.ARM_TEMPER_HYST)
        ):
            self._calm_drop = 0
            return
        if self._calm_drop == 0:
            self._calm_drop = self.fsm.rng.randint(*CALM_DROP_DELAY)
        self._calm_drop -= 1
        if self._calm_drop <= 0:
            self.put_down(stone)

    def _fidget_tick(self):
        """站着发呆时偶尔换手或低头看看手里的东西。"""
        fsm, b = self.fsm, self.body
        if self._look > 0 and b.hand_of(self._look_obj) is not None:
            self._look -= 1
            fsm.gfx.look_at = (self._look_obj.x, self._look_obj.y)
            return
        self._look = 0
        held = b.held_items()
        if not held or b.is_moving() or not b.on_floor() or fsm.rng.random() >= FIDGET_PROB:
            return
        r = fsm.rng.random()
        if r < FIDGET_WALK:
            motor.wander(fsm)  # 拿着东西挪个地方
        elif r < FIDGET_WALK + FIDGET_SWITCH and b.can_switch_hands():
            b.start_switch_hands()
        else:
            self._look_obj = fsm.rng.choice(held)
            self._look = fsm.rng.randint(*FIDGET_LOOK)

    def _drag_tick(self, cursor):
        """被拎着：甩太狠就脱手；刚被抓时好感低会把石头朝光标扔。"""
        fsm, b = self.fsm, self.body
        self._drag_ticks += 1
        ch = fsm.grab.chunk
        if ch is not None and math.hypot(ch.vx, ch.vy) > DRAG_SHAKE_SPEED:
            for obj in b.held_items():
                vx, vy = ch.vx, ch.vy
                self.put_down(obj)
                obj.vx, obj.vy = vx, vy
            return
        stone = self.held(WEAPON)
        if (
            stone is not None
            and cursor is not None
            and self._drag_ticks <= DRAG_THROW_WINDOW
            and b.temper < tuning.DRAG_THROW_TEMPER
            and fsm.rng.random() < DRAG_THROW_PROB
        ):
            self._smack(stone, cursor)

    def _smack(self, obj, cursor):
        """拿武器打抓着自己的光标：朝光标扔出去，顺势挣脱。按投掷态飞的武器取最近的四向之一。"""
        fsm, b, g = self.fsm, self.body, self.fsm.gfx
        side = b.hand_of(obj)
        h = g.hands[0 if side == "l" else 1]
        dx, dy = cursor[0] - h.x, cursor[1] - h.y
        self._purpose.pop(id(obj), None)
        if getattr(obj, "aims_line", False):
            if abs(dx) >= abs(dy):
                ix, iy = (1 if dx >= 0.0 else -1), 0
            else:
                ix, iy = 0, (1 if dy > 0.0 else -1)
            b.throw(obj, ix, 0.0, recoil=0.0, dir_y=iy)
        else:
            d = math.hypot(dx, dy)
            ux, uy = (dx / d, dy / d) if d > 1e-6 else (0.0, -1.0)
            b.release(obj, to_free=True)
            obj.x, obj.y = h.x, h.y
            obj.last_x, obj.last_y = h.x, h.y
            obj.vx, obj.vy = ux * SMACK_SPEED, uy * SMACK_SPEED
            obj.on_thrown(Throw(b, 1 if ux >= 0.0 else -1))
        g.throw_object(side, obj)
        g.blink = 15
        fsm.grab.force_release()

    # 被抢

    def snatched(self, obj):
        """光标从手里把 obj 抢走：手拽一下再松，按好感变脸色。"""
        fsm, b = self.fsm, self.body
        side = b.hand_of(obj)
        if side is None:
            return
        purpose = self.purpose_of(obj)
        b.release(obj)
        self._purpose.pop(id(obj), None)
        self._tug, self._tug_side = SNATCH_TUG, side
        hit = tuning.TEMPER_SNATCH * (2.0 if purpose == EAT_LATER and b.food < b.food_max else 1.0)
        b.temper_shift(hit)
        if b.temper < tuning.SNATCH_ANGER_TEMPER and fsm.state == "IdleStand":
            from .fsm import ANGER_TOTAL

            fsm.anger = ANGER_TOTAL
            fsm._transition("PostThrowWander")

    def _tug_tick(self, cursor):
        if self._tug <= 0:
            return
        self._tug -= 1
        if cursor is not None:
            self.fsm.gfx.hand_aim[self._tug_side] = cursor
            self.fsm.gfx.look_at = cursor
        if self._tug == 0:
            self.fsm.gfx.hand_aim[self._tug_side] = None


def _drop_rank(purpose):
    return DROP_ORDER.index(purpose) if purpose in DROP_ORDER else -1
