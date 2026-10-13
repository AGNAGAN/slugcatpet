"""啃手里的食物：手先抬到嘴边，之后每个咀嚼周期咬一口。"""

from __future__ import annotations

EAT_INTERVAL = 15  # 两口之间的帧数
EAT_APPROACH = 12  # 开吃前手进入啃食姿态的帧数
EAT_PEAK_PHASE = 0.5  # 一个咀嚼周期里第几成咬下


class Chew:
    __slots__ = ("counter", "bit", "approach")

    def __init__(self):
        self.reset()

    def reset(self):
        self.counter = 0
        self.bit = False
        self.approach = True

    def step(self, pet, f) -> bool:
        """推进一 tick；咬完最后一口返回 True。"""
        body, gfx = pet.body, pet.gfx
        gfx.look_at = (f.x, f.y)
        self.counter += 1
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
