"""行为状态基类：FSM 只通过这组钩子与声明与状态交互。"""

from __future__ import annotations

# 优先级：强制规则只能打断优先级比它低的状态，其余的等状态自己做完
T_IDLE = 0  # 待机、空中、生完气闲逛
T_ACTIVITY = 20  # 玩耍、让路：同级互不打断
T_NEED = 30  # 取果
T_REST = 35  # 累了趴下、睡觉
T_WARM = 40  # 取暖、起身
T_BODY = 60  # 晕、游泳
T_FORCED = 70  # 被拖
T_REFLEX = 80  # 躲杀
T_HIT = 90  # 被砸中
T_LOCKED = 100  # 死亡、超度

ZEROG = "zerog"  # 无重力 → 漂浮待机
SWIM = "swim"  # 入水 → 游泳
COLD = "cold"  # 寒冷 → 找暖源
EXHAUST = "exhaust"  # 体力告急 → 趴下
FETCH = "fetch"  # 饿了 → 取果
CROWD = "crowd"  # 被顶住 → 让路
DRAG = "drag"  # 被光标抓住 → 被拖
THREAT = "threat"  # 杀死弹窗 → 应对
STUN = "stun"  # 被砸中 → 晕
RULE_TIER = {
    STUN: T_HIT,
    THREAT: T_REFLEX,
    DRAG: T_FORCED,
    ZEROG: T_BODY,
    SWIM: T_BODY,
    COLD: T_WARM,
    EXHAUST: T_REST,
    FETCH: T_NEED,
    CROWD: T_ACTIVITY,
}


VIGOROUS, LIGHT, REST, IDLE = "vigorous", "light", "rest", "idle"
EN_DRAIN_VIGOROUS = 1.0 / 1200.0
EN_DRAIN_LIGHT = 1.0 / 4800.0
EN_REC_REST = 1.0 / 800.0
EN_REC_IDLE = 1.0 / 1600.0


class State:
    name = ""
    mood = None  # 对应的心情候选名（新鲜度结算）
    tier = T_IDLE  # 优先级
    energy = None  # 体力档位；None=不变

    def __init__(self, fsm):
        self.fsm = fsm

    def enter(self):
        pass

    def tick(self, cursor, disturbed):
        pass

    def brk(self):
        pass

    def kill_break(self):
        """被杀死时收尾（与 brk 分开：有的状态被杀不收尾）。"""
        pass

    def stun_break(self):
        pass

    def fx(self):
        return None

    def energy_delta(self, drain_fac):
        # 恢复不受体力影响，消耗按 drain_fac 缩放
        e = self.energy
        if e == REST:
            return EN_REC_REST
        if e == IDLE:
            return EN_REC_IDLE
        if e == VIGOROUS:
            return -EN_DRAIN_VIGOROUS * drain_fac
        if e == LIGHT:
            return -EN_DRAIN_LIGHT * drain_fac
        return 0.0


class FuncState(State):
    def __init__(
        self,
        fsm,
        name,
        enter=None,
        tick=None,
        brk=None,
        kill_break=None,
        fx=None,
        mood=None,
        tier=T_IDLE,
        energy=None,
        stun_break=None,
    ):
        super().__init__(fsm)
        self.name = name
        self.mood = mood
        self.tier = tier
        self.energy = energy
        self._enter = enter
        self._tick = tick
        self._brk = brk
        self._kill_break = kill_break
        self._stun_break = stun_break
        self._fx = fx

    def enter(self):
        if self._enter is not None:
            self._enter()

    def tick(self, cursor, disturbed):
        if self._tick is not None:
            self._tick(cursor, disturbed)

    def brk(self):
        if self._brk is not None:
            self._brk()

    def kill_break(self):
        if self._kill_break is not None:
            self._kill_break()

    def stun_break(self):
        if self._stun_break is not None:
            self._stun_break()

    def fx(self):
        return None if self._fx is None else self._fx()
