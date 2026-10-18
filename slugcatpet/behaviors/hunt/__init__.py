"""打猎：饿了又没现成能吃的，就拿武器打活物；骨针猫靠这个进食。"""

from __future__ import annotations

import math

from ... import tuning
from ...abilities.base import MOUTH
from ...brain.needs import bedtime_hunger, snack_appeal
from ...brain.hands import EAT_LATER, WEAPON
from ...brain.skills.throw import wieldable_items
from ...brain.state import HUNGER, T_NEED, VIGOROUS, State
from ...items.base import EDIBLE, creatures
from ..base import Behavior
from .hunter import Hunter, is_prey, needs_pierce

T_HUNT_CHECK = 8  # 每隔几 tick 判断一次要不要打猎
COOLDOWN_DONE = (120, 240)  # 打中后多久再打
COOLDOWN_GIVEUP = (600, 1200)  # 没打中后多久再打
COOLDOWN_NO_SHOT = (2400, 3600)  # 一下都没扔出去（够不着）后多久再打
HUNT_EFFORT = 0.8  # 顺手打猎的意愿比捡现成的打这个折


def prey_value(fsm, o):
    """打下 o 能吃到几个 1/4 格：骨针猫按吸食量，用嘴吃的猫按它本身或掉下来的东西。"""
    pet = fsm.win
    if MOUTH not in pet.tags:
        return getattr(o, "needle_quarters", 1)
    loot = getattr(o, "loot_quarters", None)
    if loot is not None:
        return loot(fsm.traits)
    return fsm.traits.nourishment(o) if pet.can_eat(o) else 0


def _armed_for(fsm, o, grows):
    """打 o 用得上的武器：大活物只有扎得进的才打得死。"""
    if grows or not needs_pierce(o):
        return True
    held = fsm.body.held_throwable()
    if held is not None and getattr(held, "pierces", False):
        return True
    return any(getattr(s, "pierces", False) for s in wieldable_items(fsm, hunting=True))


def _prey(fsm, grows=False):
    """场上能打、打下来有得吃、手边有合适武器的猎物。"""
    pet = fsm.win
    return [
        o
        for o in creatures(pet)
        if is_prey(o)
        and prey_value(fsm, o) > 0
        and not pet.rain.keeps_out(o.x, o.y)
        and _armed_for(fsm, o, grows)
    ]


class Hunt(State):
    name = "Hunt"
    tier = T_NEED
    energy = VIGOROUS
    hunter = None
    cooldown = 0
    grows = False  # 只用身上长出的武器

    def hands_needed(self):
        h = self._make()
        return "any" if h.held_weapon() is not None else "one"

    def _make(self):
        fsm = self.fsm
        return Hunter(fsm, self._pick, fsm.win.skill("grow_weapon"))

    def _pick(self):
        c0 = self.fsm.body.chunk0
        prey = _prey(self.fsm, self.grows)
        return min(prey, key=lambda o: math.hypot(o.x - c0.x, o.y - c0.y)) if prey else None

    def enter(self):
        fsm = self.fsm
        fsm.gfx.hand_aim["l"] = fsm.gfx.hand_aim["r"] = None
        self.hunter = self._make()

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if self.hunter is None:
            fsm.settle()
            return
        r = self.hunter.update()
        if r == "running":
            return
        if r == "done":
            span = COOLDOWN_DONE
        else:
            span = COOLDOWN_GIVEUP if self.hunter.throws else COOLDOWN_NO_SHOT
        self.cooldown = fsm.rng.randint(*span)
        self._release()
        fsm.settle()

    def brk(self):
        self._release()

    def kill_break(self):
        self._release()

    def _release(self):
        h = self.hunter
        if h is not None:
            h.release()
            w = h.held_weapon()
            if w is not None:
                self.fsm.hands.adopt(w, WEAPON)
        self.hunter = None


class HuntBehavior(Behavior):
    key = "hunt"
    title = {"zh": "打猎", "en": "Hunt"}
    doc = (
        "饿了又没现成吃的时拿武器打活物，最多扔三次：飞着的蝙蝠用石头或矛，蛋虫只用矛（石头只能砸晕）；"
        "骨针猫只用自己拔的骨针。蛋虫看见武器飞来会跳开，所以先冲上去逼它跳，等它落地还跳不动时再扔。"
        "投掷技能为 0 的猫（僧侣、圣徒）不打猎。"
    )
    requires = (EDIBLE,)

    def mount(self, fsm):
        pet, b = fsm.win, fsm.body
        if b.stats.throw_skill < 1 or b.stats.spear_toss:
            return
        grows = pet.skill("grow_weapon") is not None
        mouth = MOUTH in pet.tags
        if not (grows or mouth):
            return
        st = fsm.add_state(Hunt)
        st.grows = grows
        self.check = 0

        def armed():
            if grows:
                return not b.swimming
            return b.held_throwable() is not None or bool(wieldable_items(fsm, hunting=True))

        def rule(cursor):
            if st.cooldown > 0:
                st.cooldown -= 1
            self.check = (self.check + 1) % T_HUNT_CHECK
            if (
                self.check == 0
                and bedtime_hunger(b) >= tuning.EAT_URGENT
                and free()
                and not fsm.blocked(HUNGER)
            ):
                fsm._break_active_controllers()
                fsm._act_or_wake("Hunt")

        def free():
            return (
                st.cooldown <= 0
                and b.food < b.food_max
                and not fsm.grab.active
                and not fsm.ask("exhausted")
                and not b.swimming
                and not fsm.ask("cold_urgent")
                and not fsm._zerog()
                and not (mouth and (fsm.hands.held(EAT_LATER) is not None or fsm.ask("food_ready")))
                and bool(_prey(fsm, grows))
                and armed()
            )

        def want_hunt():
            if not free():
                return 0.0
            prey = _prey(fsm, grows)
            value = max(prey_value(fsm, o) for o in prey) / 4.0
            return max(bedtime_hunger(b), HUNT_EFFORT * snack_appeal(b, value) * fsm.traits.hunt_will)

        def start_hunt():
            fsm._transition("Hunt")
            return True

        def on_stun():
            if st.hunter is not None:
                st.hunter.release()
                st.hunter = None

        fsm.register_rule(rule, HUNGER)
        fsm.intents.add("hunt", want_hunt, start_hunt)
        fsm.on_stun(on_stun)
