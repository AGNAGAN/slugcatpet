"""行为状态机 BehaviorFSM。"""
from __future__ import annotations
import math
import os
import random

from .. import tuning
from ..items.base import CLIMBABLE, EDIBLE, THROWABLE
from ..planning import Planner
from .desire import build_arbiter
from .objectlooker import ObjectLooker
from .skills.motor import Chew
from .state import DRAG, RULE_TIER, STUN, SWIM, T_IDLE, THREAT, ZEROG, FuncState, State
from ..control.mouse import GrabController

# 被惹生气后的持续时间（tick）
T_POSTTHROW_WANDER = 200
T_POSTTHROW_STAND = 400
ANGER_TOTAL = T_POSTTHROW_WANDER + T_POSTTHROW_STAND

_NO_STATE = State(None)      # 未注册状态名的空声明（见 BehaviorFSM._cur）


def _lerpmap(x, lo, hi, flo, fhi):
    if hi == lo:
        return flo
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return flo + (fhi - flo) * t


class BehaviorFSM:
    def __init__(self, window, seed: int | None = None):
        self.win = window
        self.traits = window.traits
        self.body = window.body
        self.gfx = window.gfx
        self.WL = window._WL
        self.HL = window._HL
        self.rng = random.Random(seed)
        self.grab = GrabController(self.body, self.gfx)
        self.mood = build_arbiter(self.rng)
        self.looker = ObjectLooker(self.rng, self.traits.activity)

        self.state = "IdleStand"
        self.timer = 0
        self.phase = 0
        self.point_side = 0
        self._point_stopped = False
        self.cursor = None
        self.chew = Chew()
        self._prev_zerog = False
        self._zerog_entered = False
        self._wake_then = None
        self._hibernating = False
        self._exhausted = False
        self._revive_timer = 0
        self._reincarnate = False

        self.climb = None
        self.social = window.social
        self.planner = Planner(window)
        self.anger = 0
        self._cursor_prev = None
        self._cursor_speed = 0.0
        self._dwell = 0                   # 光标在中下高度带内静止的 tick 数
        self.cursorfx = getattr(window, "cursorfx", None)
        self._force_energy = None
        _fs = os.environ.get("SLUGCATPET_FORCE_ENERGY")
        if _fs:
            try:
                self._force_energy = max(0.0, min(1.0, float(_fs)))
            except ValueError:
                pass
        self._force_temper = None
        _ft = os.environ.get("SLUGCATPET_FORCE_TEMPER")
        if _ft:
            try:
                self._force_temper = max(-1.0, min(1.0, float(_ft)))
            except ValueError:
                pass
        self._force_food = None
        _ff = os.environ.get("SLUGCATPET_FORCE_FOOD")
        if _ff:
            try:
                self._force_food = max(0, min(self.body.food_max, int(_ff)))
            except ValueError:
                pass

        self._states = {}
        self._mood_entries = {}           # 心情 → (状态名, 进入前回调)
        self._register_core_states()
        self._ext_tickers = []
        self._rules = []                  # (优先级, 序号, fn)，见 register_rule
        self._rule_seq = ()
        self._stun_hooks = []
        self._provided = {}
        self._interaction_blockers = set()
        self._threat_responders = []
        self.drag_takeover = None         # fn(拎住帧数) → 是否接管（超度）
        self.stun_takeover = None         # fn() → 砸晕醒来是否接管（超度）
        self.drown_burst_fx = None
        self.kill_cancel_temper = None    # 自己取消杀死弹窗时的好感变化（舌头躲杀挂）
        for ab in getattr(self.win, "abilities", {}).values():
            ab.mount(self)
        if getattr(self.win, "cat", None) is not None:
            from ..behaviors import mount_all
            mount_all(self)

        self._enter("IdleStand")

    def _register_core_states(self):
        from .core_states import CORE_STATES
        for cls in CORE_STATES:
            self.add_state(cls)

    def register_state(self, name, enter=None, tick=None, brk=None, kill_break=None, fx=None,
                       mood=None, mood_entry=True, tier=T_IDLE, energy=None, stun_break=None):
        """mood_entry=False 时 mood 只参与新鲜度结算、不直接进入。"""
        self._states[name] = FuncState(self, name, enter=enter, tick=tick, brk=brk,
                                       kill_break=kill_break, fx=fx, mood=mood, tier=tier,
                                       energy=energy, stun_break=stun_break)
        if mood is not None and mood_entry:
            self.register_mood_entry(mood, name)

    def register_mood_entry(self, mood, state, before=None):
        self._mood_entries[mood] = (state, before)

    def add_state(self, cls):
        st = self._states[cls.name] = cls(self)
        return st

    def state_obj(self, name):
        return self._states.get(name)

    def register_rule(self, fn, rule=None):
        """追加每 tick 规则 fn(cursor)，在状态 tick 前运行；rule 为强制规则，优先级高者先跑。"""
        tier = RULE_TIER[rule] if rule is not None else -1
        self._rules.append((-tier, len(self._rules), fn))
        self._rule_seq = tuple(f for _, _, f in sorted(self._rules))

    def on_stun(self, fn):
        self._stun_hooks.append(fn)

    def provide(self, name, fn):
        self._provided[name] = fn

    def ask(self, name, default=False):
        fn = self._provided.get(name)
        return default if fn is None else fn()

    def items(self, use):
        return self.win.items_affording(use)

    def register_ticker(self, fn):
        self._ext_tickers.append(fn)

    def add_threat_responder(self, fn):
        """杀死弹窗应对 fn() → 是否已应对；按挂载顺序询问，第一个应对的生效。"""
        self._threat_responders.append(fn)

    def block_interaction(self, state_name):
        self._interaction_blockers.add(state_name)

    def blocks_interaction(self) -> bool:
        return self.state in self._interaction_blockers

    def exclusive_fx(self):
        st = self._states.get(self.state)
        return None if st is None else st.fx()

    def on_press(self, cursor):
        if self.blocks_interaction():
            return False
        return self.grab.begin(cursor)

    def on_release(self):
        self.grab.end()

    def apply_stun(self, ticks):
        if self.blocked(STUN):
            return False
        if self.grab.active:
            self.grab.force_release()
        self._break_tongue()
        self.climb = None
        for fn in self._stun_hooks:
            fn()
        self._states[self.state].stun_break() if self.state in self._states else None
        self.body.drop_carried()
        self._clear_hands()
        self.body.zerog_pole = None
        self.body.set_posture(False)
        self.body.stun = max(self.body.stun, int(ticks))
        self.gfx.stunned = True
        self.body.temper_shift(tuning.TEMPER_STUN)
        self._transition("Stunned")
        return True

    def kill(self):
        if self.state == "Dead":
            return
        st = self._states.get(self.state)
        if st is not None:
            st.kill_break()
        self._hibernating = False
        self.body.food_eat(-tuning.FOOD_KILL_PENALTY)
        if self.body.karma > 0 or self.body.karma_bottomed():
            self.body.karma_drop()    # 业力锁底也照常空转复活
            self.body.temper_shift(tuning.TEMPER_KILL_REVIVED)
            self.body.die()
            self.gfx.dead = True
            self._transition("Dead")
            self._revive_timer = tuning.REVIVE_TICKS
        else:
            self.body.die()
            self._transition("Dead")
            self._revive_timer = 0

    def kill_cold(self):
        self._env_death()

    def kill_drown(self):
        self._env_death(in_water=True)

    def kill_drown_burst(self):
        if self.state == "Dead":
            return
        if self.drown_burst_fx is not None:
            self.drown_burst_fx()
        self._env_death(in_water=True, defuse=True)

    def _env_death(self, in_water=False, defuse=False):
        """环境致死：转世复活，不计好感。"""
        if self.state == "Dead":
            return
        self.body.karma_drop()
        self._dismiss_kill_dialog()
        self._break_active_controllers()
        self.grab.force_release()
        if in_water:
            self.body.swim_target = None
        if defuse:
            self.body.drown_burst = False
        self._hibernating = False
        self._exhausted = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._reincarnate = True
        self._revive_timer = tuning.REINCARNATE_TICKS

    def kill_threat_canceled(self, by_self: bool):
        """杀死弹窗被取消：by_self=猫自己（舌头躲杀）取消，否则是用户点的。"""
        self.body.temper_shift(self.kill_cancel_temper if by_self
                               else tuning.TEMPER_KILL_CANCEL_HUMAN)

    def is_truly_dead(self) -> bool:
        return self.state == "Dead" and self._revive_timer <= 0

    def is_reincarnating(self) -> bool:
        return self.state == "Dead" and self._reincarnate and self._revive_timer > 0

    def enter_dead(self):
        """直接置真死态（持久化恢复用）。"""
        self._break_active_controllers()
        self.grab.force_release()
        self._hibernating = False
        self.body.die()
        self.gfx.dead = True
        self._transition("Dead")
        self._revive_timer = 0

    def _break_active_controllers(self):
        st = self._states.get(self.state)
        if st is not None:
            st.brk()

    def _break_tongue(self):
        tg = self.win.tongue
        if tg is not None:
            tg.retract()
            tg.reset_config()
        self.body.suspended = False

    def update(self, cursor):
        self.cursor = cursor
        for fn in self._ext_tickers:
            fn()
        self._track_cursor(cursor)
        disturbed = self.grab.active

        z = self._zerog()
        if z and not self._prev_zerog:
            self._zerog_entered = True
        elif (self._prev_zerog and not z and self.state == "IdleStand"
                and self.body.carried_fruit is not None):
            f = self.body.carried_fruit
            self.body.release_fruit()
            f.state = "free"
        self._prev_zerog = z

        if (getattr(self.win, "_kill_dialog", None) is not None
                and self._threat_responders
                and not self.blocked(THREAT)):
            self._break_active_controllers()
            self.grab.force_release()
            for respond in self._threat_responders:
                if respond():
                    break

        self.grab.tick()
        if self.grab.active:
            self.interrupt(DRAG, "Dragged")
            self.grab.drag(cursor) if cursor is not None else None

        if self.body.drown_burst and self.state != "Dead":
            self.kill_drown_burst()
        elif self.body.drown >= 1.0 and self.state != "Dead":
            self.kill_drown()
        elif self.body.swimming:
            self.interrupt(SWIM, "Swimming")
        elif self.state == "Swimming":
            self.body.swim_target = None
            self.settle()

        if self._zerog():
            self.interrupt(ZEROG, "IdleStand")

        for rule in self._rule_seq:
            rule(cursor)

        self.gfx.look_at = None
        self.gfx.sleeping = (self.state == "Sleep")
        self.body.sleeping = (self.state == "Sleep")
        self.gfx.dead = (self.state == "Dead")
        self.gfx.stunned = (self.state == "Stunned")

        st = self._states.get(self.state)
        if st is not None:
            st.tick(cursor, disturbed)
        self.body.energy_change(self._cur().energy_delta(self.traits.drain))
        if self._force_energy is not None:
            self.body.energy = self._force_energy
        if self._force_temper is not None:
            self.body.temper = self._force_temper
        if self._force_food is not None:
            self.body.food = self._force_food
        self.mood.tick_freshness(self._active_mood())
        self.timer += 1

    def _transition(self, new):
        if new == self.state:
            return
        self.state = new
        self.timer = 0
        self.phase = 0
        self._enter(new)

    def settle(self):
        self._transition("IdleStand" if self.body.on_floor() else "Airborne")

    def _act_or_wake(self, target):
        """趴/睡态先起身并稳定一会再行动；已站立则直接进入目标态。"""
        if self.state in ("LieDown", "Sleep"):
            self._transition("WakeSequence")   # 顺序：_enter 会清 _wake_then
            self._wake_then = target
        else:
            self._transition(target)

    def _enter(self, st):
        state = self._states.get(st)
        if state is not None:
            state.enter()

    def _active_mood(self):
        return self._cur().mood

    def _cur(self):
        """当前状态对象；未注册的名字给空声明（最低优先级、不耗体力）。"""
        return self._states.get(self.state, _NO_STATE)

    def blocked(self, rule) -> bool:
        """当前状态的优先级不低于这条规则，规则不能打断它。"""
        return RULE_TIER[rule] <= self._cur().tier

    def interrupt(self, rule, target) -> bool:
        """规则打断当前状态、收尾后转入 target；已在 target 或被挡住时什么都不做。"""
        if self.state == target or self.blocked(rule):
            return False
        self._break_active_controllers()
        self._transition(target)
        return True

    def _look_candidates(self, cursor):
        # 键用对象本身，避免 id() 字符串撞码
        c = []
        if cursor is not None:
            c.append(("cursor", cursor, tuning.LOOK_CURSOR_BASE, self._cursor_speed))
        for f in self.items(EDIBLE):
            c.append((f, (f.x, f.y), tuning.LOOK_ITEM_BASE, 0.0))
        for p in self.items(CLIMBABLE):
            c.append((p, (p.bx, p.by), tuning.LOOK_ITEM_BASE, 0.0))
        for s in self.items(THROWABLE):
            c.append((s, (s.x, s.y), tuning.LOOK_ITEM_BASE, 0.0))
        return c

    def _ambient_look(self, cursor):
        head = (self.gfx.head.x, self.gfx.head.y)
        return self.looker.update(head, self._look_candidates(cursor), self.WL, self.HL)

    def _zerog(self) -> bool:
        return getattr(self.body, "zerog", False)

    def _track_cursor(self, cursor):
        inst = 0.0
        if cursor is not None and self._cursor_prev is not None:
            inst = math.hypot(cursor[0] - self._cursor_prev[0],
                              cursor[1] - self._cursor_prev[1])
        self._cursor_speed = self._cursor_speed * 0.5 + inst * 0.5
        in_band = (cursor is not None
                   and self.HL * tuning.CURSOR_DWELL_BAND_LO <= cursor[1]
                   <= self.HL * tuning.CURSOR_DWELL_BAND_HI)
        if in_band and inst < tuning.CURSOR_DWELL_TOL:
            self._dwell += 1
        else:
            self._dwell = 0
        self._cursor_prev = cursor

    def _clear_hands(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    def _dismiss_kill_dialog(self):
        if getattr(self.win, "_kill_dialog", None) is not None:
            self.win.dismiss_kill_dialog()
