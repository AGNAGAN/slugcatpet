"""Saint 舌头：弹道舌尖 + 单向弹簧拉上身 chunk。"""

from __future__ import annotations
import math

from ...core.units import K_VEL, K_IMP
from ...items.state import ItemState

IDLE = "idle"
SHOOTING = "shooting"
ATTACHED = "attached"
RETRACTING = "retracting"

ZEROG_THRESH = 0.5  # 判零重力
ZEROG_VEL_CLAMP = 4.0 * K_VEL


def _zerog_velo(base_v, inc):
    """零重力目标速度：朝输入方向加 inc，各轴钳 ±4。"""
    v = base_v + inc
    if base_v < 0.0:
        return v if v > -ZEROG_VEL_CLAMP else -ZEROG_VEL_CLAMP
    return v if v < ZEROG_VEL_CLAMP else ZEROG_VEL_CLAMP


class Tongue:
    """Saint 舌头：update 须在 body 物理前调用。"""

    def __init__(self, mouth_x: float, mouth_y: float, n: int, widths: list[float]):
        self.n = n
        self.widths = widths
        self.x, self.y = mouth_x, mouth_y
        self.vx = self.vy = 0.0
        self.mouth = (mouth_x, mouth_y)
        self.mode = IDLE
        self.owner = None
        self.elastic = 0.0
        self.requested = 0.0
        self.anchor = None
        self.attached_obj = None
        self._target_obj = None  # 飞行中待粘目标，命中转 attached_obj
        self.attached_time = 0
        self.room_gravity = 1.0
        self.body = None
        self.travel = 0.0
        self.floor_y = None
        self.shoot_v = 70.0 * K_VEL
        self.base_ideal = 150.0
        self.ideal = self.base_ideal
        self.total = 200.0
        self.reel_rate = 0.0  # 0=纯弹性门控，非0=手动收绳速率

    def reset_config(self) -> None:
        self.shoot_v = 70.0 * K_VEL
        self.ideal = self.base_ideal
        self.total = 200.0
        self.reel_rate = 0.0

    def try_acquire(self, owner) -> bool:
        if self.owner is None or self.owner is owner:
            self.owner = owner
            return True
        return False

    def release(self, owner) -> None:
        if self.owner is owner:
            self.owner = None

    def owned_by_other(self, owner) -> bool:
        return self.owner is not None and self.owner is not owner

    def is_idle(self) -> bool:
        return self.mode == IDLE

    def set_targets(self, *, ideal=None, reel_rate=None, shoot_v=None, total=None) -> None:
        if ideal is not None:
            self.ideal = ideal
        if reel_rate is not None:
            self.reel_rate = reel_rate
        if shoot_v is not None:
            self.shoot_v = shoot_v
        if total is not None:
            self.total = total

    @property
    def state(self):
        return self.mode

    @state.setter
    def state(self, v):
        self.mode = v

    @property
    def attached(self) -> bool:
        return self.mode == ATTACHED

    @property
    def visible(self) -> bool:
        return self.mode != IDLE and self.travel > 1.0

    def shoot(self, mouth_x, mouth_y, tx, ty, hit: bool, obj=None, owner=None) -> bool:
        if self.mode != IDLE or self.owned_by_other(owner):
            return False
        dx, dy = tx - mouth_x, ty - mouth_y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        self.mouth = (mouth_x, mouth_y)
        self.x = mouth_x + ux * 5.0
        self.y = mouth_y + uy * 5.0
        self.vx = ux * self.shoot_v
        self.vy = uy * self.shoot_v
        self.elastic = 1.0
        self.requested = 140.0
        self.anchor = (tx, ty) if hit else None
        self.attached_obj = None
        self._target_obj = obj if hit else None
        self.travel = 0.0
        self.mode = SHOOTING
        self._zerog_propel(ux, uy)
        return True

    def _zerog_propel(self, ux, uy):
        if self.room_gravity >= ZEROG_THRESH or self.body is None:
            return
        # 连续瞄准分量，非 sign；逐次累积至封顶
        for c in (self.body.chunk0, self.body.chunk1):
            c.vx = _zerog_velo(c.vx, ux * K_VEL)
            c.vy = _zerog_velo(c.vy, uy * K_VEL)

    def retract(self) -> None:
        if self.mode in (SHOOTING, ATTACHED):
            self.mode = RETRACTING

    def update(self, mouth_x, mouth_y, head) -> None:
        """在 body 物理之前调；对上身 chunk 施单向弹簧力。"""
        self.mouth = (mouth_x, mouth_y)
        mx, my = mouth_x, mouth_y

        if self.mode == IDLE:
            self.x, self.y = mx, my
            self.travel = 0.0
            return

        if self.mode == SHOOTING:
            self.requested = max(0.0, self.requested - 4.0 * K_VEL)
            self.x += self.vx
            self.y += self.vy
            self.travel = math.hypot(self.x - mx, self.y - my)
            if self.anchor is not None:
                ax, ay = self.anchor
                if self.travel >= math.hypot(ax - mx, ay - my) - 1e-3:
                    if self._target_obj is not None:
                        self.attached_obj = self._target_obj
                        ax, ay = self.attached_obj.x, self.attached_obj.y
                        self.anchor = (ax, ay)
                    self.x, self.y = ax, ay
                    self.vx = self.vy = 0.0
                    # 与 _elasticity 基准保持一致
                    self.requested = math.hypot(self.x - head.x, self.y - head.y)
                    self.elastic = 1.0
                    self.travel = math.hypot(self.x - mx, self.y - my)
                    self.attached_time = 0
                    self.mode = ATTACHED
            elif self.travel >= self.total:
                self.mode = RETRACTING

        elif self.mode == ATTACHED:
            self.attached_time += 1
            if self.room_gravity < ZEROG_THRESH and self.attached_time < 3:
                self.mode = RETRACTING  # 零重力附着不稳定
                return
            o = self.attached_obj
            if o is not None and getattr(o, "state", None) not in (ItemState.HANGING, ItemState.FREE):
                self.mode = RETRACTING
            else:
                if o is not None:
                    self.anchor = (o.x, o.y)
                self.x, self.y = self.anchor
                self.travel = math.hypot(self.x - mx, self.y - my)
                self.elastic = max(0.0, self.elastic - 0.05 * K_VEL)
                gated = (1.0 - self.elastic) * 2.0 * K_VEL  # 门控速率，命中瞬间≈0
                if self.requested < self.ideal:
                    self.requested = min(self.requested + gated, self.ideal)
                elif self.requested > self.ideal:
                    reel = max(gated, self.reel_rate * K_VEL)
                    self.requested = max(self.requested - reel, self.ideal)
                self._elasticity(head)
                if self.travel > self.total * 2.5:  # 超长保险丝
                    self.mode = RETRACTING

        elif self.mode == RETRACTING:
            self.travel = max(0.0, self.travel - self.shoot_v)
            d = math.hypot(self.x - mx, self.y - my) or 1.0
            ux, uy = (self.x - mx) / d, (self.y - my) / d
            self.x = mx + ux * self.travel
            self.y = my + uy * self.travel
            if self.travel <= 1.0:
                self.mode = IDLE
                self.owner = None  # 释权防死锁
                self.anchor = None
                self.attached_obj = None
                self._target_obj = None
                self.x, self.y = mx, my

        if self.floor_y is not None and self.y > self.floor_y:
            self.y = self.floor_y

    def _elasticity(self, head) -> None:
        if getattr(head, "pinned", False):  # 拖拽中由光标驱动，不受舌头弹力
            return
        hx0, hy0 = head.x, head.y
        obj = self.attached_obj if self.mode == ATTACHED else None
        if obj is not None:
            mass_ratio = obj.mass / (obj.mass + getattr(head, "mass", 0.35))
        else:
            mass_ratio = 1.0
        total_len = math.hypot(self.x - hx0, self.y - hy0)
        a = 1.1
        allowed = min(self.requested, self.total) * (a + (1.0 - a) * self.elastic)
        if total_len <= allowed or total_len < 1e-6:
            return
        over = total_len - allowed
        k = 0.85 + (0.25 - 0.85) * self.elastic
        dx, dy = self.x - hx0, self.y - hy0
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        pslide = 1.0 - 0.5 * self.elastic
        vt = (over * k * mass_ratio) * K_IMP
        pt = (over * k * mass_ratio * pslide) * K_VEL
        if hasattr(head, "vx"):
            head.x += ux * pt
            head.y += uy * pt
            head.vx += ux * vt
            head.vy += uy * vt
        else:  # Verlet Point：经 ox 注入冲量
            head.x += ux * pt
            head.y += uy * pt
            head.ox += ux * (pt - vt)
            head.oy += uy * (pt - vt)
        if obj is not None and mass_ratio < 1.0:
            ovt = (over * k * (1.0 - mass_ratio)) * K_IMP
            opt = (over * k * (1.0 - mass_ratio) * pslide) * K_VEL
            obj.x -= ux * opt
            obj.y -= uy * opt
            obj.vx -= ux * ovt
            obj.vy -= uy * ovt

    def positions(self) -> list:
        mx, my = self.mouth
        if self.mode == IDLE:
            return [(mx, my)] * self.n
        return [
            (mx + (self.x - mx) * (i / (self.n - 1)), my + (self.y - my) * (i / (self.n - 1)))
            for i in range(self.n)
        ]
