"""啃手里的食物：手抬到嘴边后每个咀嚼周期咬一口，身子在动或头泡在水里时停嘴；尸体伏下身子啃，啃完扔开。"""

from __future__ import annotations

import math
import random

EAT_INTERVAL = 15  # 两口之间的帧数
EAT_APPROACH = 12  # 开吃前手进入啃食姿态的帧数
EAT_PEAK_PHASE = 0.5  # 一个咀嚼周期里第几成咬下
STILL_STEP = 3.6  # 头一 tick 移动不到这么多才吃得了
HEAD_WET = 0.5  # 头入水超过这么多吃不了（水生的不限）
MEAT_PULL = 20  # 尸体拉到胸口用的帧数，之后伏下身子
MEAT_FIRST = 48  # 第一口在第几帧
MEAT_INTERVAL = 15
MEAT_TOSS = 80  # 啃完后到这个帧数的整倍数时扔开
MEAT_LET_GO = 60  # 手动松开拾取键时已啃过这么久就扔开
MEAT_RESUME = 50  # 松开后计数回落，最多留到这里
MEAT_SHAKE = 5  # 每隔几帧抖一下、啄一下
MEAT_JOLT = 3.0
MEAT_PECK = 4.0
MEAT_PULL_HEAD, MEAT_PULL_REAR = 0.5, 0.6  # 啃时上身被拽向尸体、下身往后撑
MEAT_BITE_NUDGE = 4.0  # 咬下那口时上身往上半圈随机方向一顿
TOSS_VX, TOSS_VY = 3.0, -4.0
_RNG = random.Random(0x3EA7)


def can_chew(body) -> bool:
    """身子停住、头没泡在水里。"""
    c0 = body.chunk0
    if (c0.x - c0.last_x) ** 2 + (c0.y - c0.last_y) ** 2 >= STILL_STEP**2:
        return False
    return body.aquatic or body.head_sub < HEAD_WET


class Chew:
    __slots__ = ("counter", "bit", "approach", "crouched")

    def __init__(self):
        self.crouched = None
        self.reset()

    def reset(self):
        self.counter = 0
        self.bit = False
        self.approach = True

    def stop(self, body):
        """中途停下：伏下的身子站起来。"""
        if self.crouched is body:
            body.standing = True
        self.crouched = None

    def hold_meat(self, pet, f, pressing) -> None:
        """手动控制：按住拾取键啃尸体；松开时啃得够久就扔开，否则计数慢慢回落。"""
        if pressing:
            self.step(pet, f)
        elif self.counter > MEAT_LET_GO:
            self._toss(pet.body, f)
        else:
            self.counter = max(0, min(self.counter - 1, MEAT_RESUME))
            pet.body.set_eat_raise(f, min(1.0, self.counter / MEAT_PULL))

    def step(self, pet, f) -> bool:
        """推进一 tick；咬完最后一口返回 True。"""
        body, gfx = pet.body, pet.gfx
        gfx.look_at = (f.x, f.y)
        if not can_chew(body):
            return False
        self.counter += 1
        if getattr(f, "carcass", False):
            return self._meat(pet, f)
        if self.approach:
            body.set_eat_raise(f, min(1.0, self.counter / EAT_APPROACH))
            if self.counter >= EAT_APPROACH:
                self.approach = False
                self.counter = 0
            return False
        done = False
        if self.counter >= EAT_INTERVAL * EAT_PEAK_PHASE and not self.bit:
            self.bit = True
            gfx.bite(body.hand_of(f))
            done = body.consume(f, pet.traits.nourishment(f))
        if self.counter >= EAT_INTERVAL:
            self.counter = 0
            self.bit = False
        return done

    def _meat(self, pet, f) -> bool:
        """啃尸体：拉到胸口，伏下、闭眼、一下下啄，到点咬一口，啃完或吃饱就扔开站起来。"""
        body, gfx = pet.body, pet.gfx
        t = self.counter
        body.set_eat_raise(f, min(1.0, t / MEAT_PULL))
        if t <= MEAT_PULL:
            return False
        if body.standing:
            body.standing = False
            self.crouched = body
        gfx.blink = max(gfx.blink, 5)
        c0, c1 = body.chunk0, body.chunk1
        dx, dy = f.x - c0.x, f.y - c0.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            dx, dy = dx / d, dy / d
            c0.vx += dx * MEAT_PULL_HEAD
            c0.vy += dy * MEAT_PULL_HEAD
            c1.vx -= dx * MEAT_PULL_REAR
            c1.vy -= dy * MEAT_PULL_REAR
        rng = pet.behavior.rng if pet.behavior is not None else _RNG
        if t % MEAT_SHAKE == 0:
            a = rng.uniform(0.0, math.tau)
            body.chunk0.vx += math.cos(a) * MEAT_JOLT * 0.3
            body.chunk0.vy += math.sin(a) * MEAT_JOLT * 0.3
            a = rng.uniform(0.0, math.tau)
            gfx.head.vx += math.cos(a) * MEAT_PECK * 0.5
            gfx.head.vy += math.sin(a) * MEAT_PECK * 0.5
        if (
            t >= MEAT_FIRST
            and (t - MEAT_FIRST) % MEAT_INTERVAL == 0
            and f.meat > 0
            and body.food < body.food_max
        ):
            gfx.bite(body.hand_of(f))
            a = rng.uniform(-0.5 * math.pi, 0.5 * math.pi)
            body.chunk0.x += math.sin(a) * MEAT_BITE_NUDGE
            body.chunk0.y -= math.cos(a) * MEAT_BITE_NUDGE
            body.consume(f, pet.traits.nourishment(f))
            bleed = getattr(f, "bleed", None)
            if bleed is not None:
                bleed(rng.randint(1, 3))
        if t % MEAT_TOSS == 0 and (f.meat <= 0 or body.food >= body.food_max):
            self._toss(body, f)
            return True
        return False

    def _toss(self, body, f):
        body.release(f, to_free=True)
        f.vx, f.vy = -body.facing * TOSS_VX, TOSS_VY
        self.stop(body)
        self.reset()
