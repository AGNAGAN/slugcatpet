"""行为状态基类：状态机只经这些钩子和声明与状态打交道。"""

from __future__ import annotations

# 优先级：强制规则只能打断优先级比它低的状态，其余的等状态自己做完
T_IDLE = 0  # 待机、空中、生完气闲逛、爬架
T_ACTIVITY = 20  # 玩耍、让路：同级互不打断
T_STALL = 25  # 走到一半路断了：放下玩耍、待机；找吃的、歇着、取暖、躲雨自己接着处理
T_NEED = 30  # 饿了去找吃的
T_REST = 35  # 累了趴下、睡觉
T_WARM = 40  # 取暖、起身
T_BODY = 60  # 晕、游泳
T_HOLD = 65  # 定身
T_CARRIED = 68  # 被别的猫拉着、背着
T_FORCED = 70  # 被拖
T_REFLEX = 80  # 躲杀
T_HIT = 90  # 被砸中
T_LOCKED = 100  # 死亡、超度

ZEROG = "zerog"  # 无重力 → 漂浮待机
SWIM = "swim"  # 入水 → 游泳
COLD = "cold"  # 寒冷 → 找暖源
RAIN = "rain"  # 大雨 → 躲到遮挡下
EXHAUST = "exhaust"  # 体力告急 → 趴下
SLEEPY = "sleepy"  # 困到撑不住就地睡
HUNGER = "hunger"  # 饿了 → 找吃的
CROWD = "crowd"  # 别的猫要过 → 让路
STALL = "stall"  # 走到一半路断了 → 不做这件事了
DRAG = "drag"  # 被光标抓住 → 被拖
THREAT = "threat"  # 杀死弹窗 → 应对
STUN = "stun"  # 被砸中 → 晕
HOLD = "hold"  # 用户让它定身 → 定身
CARRY = "carry"  # 被别的猫拉住、背上 → 被带着
RULE_TIER = {
    STUN: T_HIT,
    HOLD: T_HOLD,
    CARRY: T_CARRIED,
    THREAT: T_REFLEX,
    DRAG: T_FORCED,
    ZEROG: T_BODY,
    SWIM: T_BODY,
    COLD: T_WARM,
    RAIN: T_WARM,
    EXHAUST: T_REST,
    SLEEPY: T_REST,
    HUNGER: T_NEED,
    CROWD: T_ACTIVITY,
    STALL: T_STALL,
}


VIGOROUS, LIGHT, REST, IDLE = "vigorous", "light", "rest", "idle"
EN_DRAIN_VIGOROUS = 1.0 / 1200.0
EN_DRAIN_LIGHT = 1.0 / 4800.0
EN_REC_REST = 1.0 / 800.0
EN_REC_IDLE = 1.0 / 1600.0


class State:
    name = ""
    mood = None  # 对应的心情候选名，用于新鲜度结算
    tier = T_IDLE  # 优先级
    energy = None  # 体力档位，None 为不变
    hands = "any"  # 需要的空手：any 拿着东西也行 / one 至少一只 / free 两只
    needs = True  # False 时困意不涨

    def __init__(self, fsm):
        self.fsm = fsm

    def hands_needed(self):
        """进入时需要的空手，见 hands。"""
        return self.hands

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
