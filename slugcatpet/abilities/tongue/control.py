"""操控时的舌头：空中按跳射出，粘住后上下收放绳、再按跳松开起跳。"""

from __future__ import annotations

import math

from .aim import ray_target, tongue_of

AIM_UP = 0.7  # 不按上时朝前上方射，竖直分量
VEL_BIAS = 0.2  # 射出方向叠加的当前速度方向
REEL_STEP = 3.0  # 按上下每 tick 收放的绳长
ROPE_MIN = 50.0
ROPE_MAX = 170.0
RELEASE_HEAD_VY = 8.0  # 松舌起跳的竖直速度
RELEASE_HIP_VY = 7.0
RELEASE_BOOST = 8.0
RELEASE_MIN_ATTACHED = 2  # 粘住这么多 tick 后才能按跳松开


class TongueControl:
    def __init__(self, pet):
        self.pet = pet

    def update(self, body, inp0, inp1, can_jump):
        """操控移动开头、抓杆之前调：空中按跳射舌，粘住时收放绳和松舌；都不消耗跳跃预输入。"""
        t = tongue_of(self.pet)
        if t is None:
            return
        press = inp0.jmp and not inp1.jmp
        if t.attached:
            self._attached(body, t, inp0, press)
        elif press and not inp0.pckp and can_jump <= 0 and t.is_idle():
            self._shoot(body, t, inp0)

    def _shoot(self, body, t, inp0):
        c0 = body.chunk0
        ux, uy = (0.0, -1.0) if inp0.y > 0 else (float(body.facing or 1), -AIM_UP)
        n = math.hypot(ux, uy)
        ux, uy = ux / n, uy / n
        sp = math.hypot(c0.vx, c0.vy)
        if sp > 1e-6:
            ux += c0.vx / sp * VEL_BIAS
            uy += c0.vy / sp * VEL_BIAS
            n = math.hypot(ux, uy)
            ux, uy = ux / n, uy / n
        if not t.try_acquire(self):
            return False
        t.reset_config()
        mx, my = self.pet.gfx.mouth_world()
        hx, hy, obj, hit = ray_target(self.pet, mx, my, ux, uy, t.total)
        if not t.shoot(mx, my, hx, hy, hit, obj=obj, owner=self):
            t.release(self)
            return False
        return True

    def _attached(self, body, t, inp0, press):
        if inp0.y > 0:
            t.ideal = max(ROPE_MIN, t.ideal - REEL_STEP)
        elif inp0.y < 0:
            t.ideal = min(ROPE_MAX, t.ideal + REEL_STEP)
        if press and t.attached_time >= RELEASE_MIN_ATTACHED:
            t.retract()
            if t.room_gravity >= 0.5:
                body.chunk0.vy = -RELEASE_HEAD_VY
                body.chunk1.vy = -RELEASE_HIP_VY
                body.jump_boost = RELEASE_BOOST

    def leave(self):
        """退出操控：收回舌头。"""
        t = tongue_of(self.pet)
        if t is not None and not t.is_idle() and t.owner is self:
            t.retract()
