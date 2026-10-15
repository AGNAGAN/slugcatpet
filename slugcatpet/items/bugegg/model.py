"""蛋虫蛋的物理：单个质点带一截软柄，会滚，掉下来后慢慢胀大，刚掉或被咬时滴一阵液；y↓。"""

from __future__ import annotations

import math
import random as _random

from ...core.chunkphys import aabb_wall_collide, apply_water
from ...core.units import inv_lerp, lerp, lerp_tick
from ...world.liquid_drip import new_drip, step_drips
from ..state import ItemState

RAD = 4.0
MASS = 0.2
GRAVITY = 0.9
AIR_FRICTION = 0.999
BOUNCE = 0.2
SURFACE_FRICTION = 0.7
BUOYANCY = 1.1
WATER_FRICTION = 0.95
BITES = 2
SWELL_K = 0.15  # 胀满时比刚掉下来大这么多
LIQUID_TICKS = (40, 80)
ROLL_K = 0.12  # 在地上滚动时转速随水平速度
DRIP_CHANCE = 0.25
STALK_SEGS = 5
STALK_GAP = 2.0
STALK_ROOT = 7.0  # 柄根离蛋心（随胀大缩放）


class BugEgg:
    collision_layer = 1
    edible = True
    throwable = False
    is_meat = False
    carnivore_full = True  # 肉食的猫吃它也得满格

    __slots__ = (
        "x",
        "y",
        "vx",
        "vy",
        "last_x",
        "last_y",
        "rad",
        "mass",
        "gravity",
        "air_friction",
        "bounce",
        "surface_friction",
        "buoyancy",
        "water_friction",
        "water_y",
        "room_gravity",
        "_bites",
        "state",
        "rotation",
        "last_rotation",
        "rot_vel",
        "stalk",
        "held_by_hand",
        "collide_with_objects",
        "hue",
        "swell",
        "liquid",
        "liquid_ticks",
        "dissolve",
        "drips",
        "stalk_pts",
        "_id",
        "_rng",
        "_contact_floor",
        "_contact_x",
        "_impact_cb",
    )

    def __init__(self, x: float, y: float, seed: int = 0, hue: float = 0.0, fresh: bool = False):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = self.vy = 0.0
        self.rad = RAD
        self.mass = MASS
        self.gravity = GRAVITY
        self.air_friction = AIR_FRICTION
        self.bounce = BOUNCE
        self.surface_friction = SURFACE_FRICTION
        self.buoyancy = BUOYANCY
        self.water_friction = WATER_FRICTION
        self.water_y = None
        self.room_gravity = 1.0
        self._bites = BITES
        self.state = ItemState.FREE
        rng = self._rng = _random.Random(seed * 31 + 7)
        a = rng.uniform(0.0, math.tau)
        self.rotation = self.last_rotation = (math.sin(a), -math.cos(a))
        self.rot_vel = 0.0
        self.stalk = None
        self.held_by_hand = None
        self.collide_with_objects = True
        self.hue = hue
        self.swell = 0.0 if fresh else 1.0
        self.liquid = 1.0 if fresh else 0.0
        self.liquid_ticks = rng.randint(*LIQUID_TICKS)
        self.dissolve = -1
        self.drips = []
        self.stalk_pts = []  # 软柄各节 [x, y, 上帧 x, 上帧 y, vx, vy]
        self.reset_stalk()
        self._id = int(seed)
        self._contact_floor = False
        self._contact_x = 0
        self._impact_cb = None

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def swell_fac(self):
        return 1.0 + SWELL_K * self.swell

    @property
    def bites(self):
        return self._bites

    @bites.setter
    def bites(self, v):
        if v < self._bites:
            self.liquid = 1.0  # 被咬一口，又滴一阵
        self._bites = v

    def set_rotation(self, rx, ry):
        self.rotation = self.last_rotation = (rx, ry)
        self.reset_stalk()

    def reset_stalk(self):
        rx, ry = self.rotation
        self.stalk_pts = [[self.x + rx * i, self.y + ry * i] * 2 + [0.0, 0.0] for i in range(STALK_SEGS)]

    def collision_chunks(self):
        self.collide_with_objects = not (
            self.state in (ItemState.CARRIED, ItemState.MOUSE, ItemState.EATEN, ItemState.GONE)
            or self.held_by_hand is not None
            or self.dissolve >= 0
        )
        return (self,)

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        """被拿着时竖起来，尖朝上。"""
        self.last_rotation = self.rotation
        dx, dy = gx - self.x, gy - self.y
        d = math.hypot(dx, dy) or 1.0
        px, py = dy / d, -dx / d
        self.rotation = (px, -abs(py))

    def step(self, WL: float, HL: float) -> None:
        self._liquid_tick(HL)
        if self.state in (ItemState.CARRIED, ItemState.MOUSE):
            self._contact_floor = False
            self._stalk()
            return
        self.last_x, self.last_y = self.x, self.y
        self.last_rotation = self.rotation
        if self.state == ItemState.EATEN:
            return
        if self.swell < 1.0:
            self.swell = lerp_tick(self.swell, 1.0, 0.01, self._rng.random() / 80.0)
            self.rad = RAD * self.swell_fac
        self.vy += self.gravity * self.room_gravity
        apply_water(
            self, self.water_y, self.buoyancy, self.water_friction, self.room_gravity, self.air_friction
        )
        self.x += self.vx
        self.y += self.vy
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if self._contact_floor:
            self.rot_vel = lerp(self.rot_vel, ROLL_K * self.vx, 0.8)
            self.vx *= 0.8
        if self.rot_vel > 0.0:
            rx, ry = self.rotation
            rx, ry = rx - ry * self.rot_vel, ry + rx * self.rot_vel
            n = math.hypot(rx, ry) or 1.0
            self.rotation = (rx / n, ry / n)
        self._stalk()

    def _stalk(self):
        """软柄：根接在蛋尖上，前半段顺着蛋的朝向伸、后半段下垂，各节间距 2。"""
        pts, g = self.stalk_pts, self.room_gravity
        rx, ry = self.rotation
        last = STALK_SEGS - 1
        for i, s in enumerate(pts):
            t = i / last
            s[2], s[3] = s[0], s[1]
            s[0] += s[4]
            s[1] += s[5]
            s[4] *= 0.995
            s[5] = s[5] * 0.995 + 0.9 * inv_lerp(0.5, 1.0, t) * g
            k = 5.0 * inv_lerp(0.5, 0.0, t)
            s[4] += rx * k
            s[5] += ry * k
            if i > 1:
                a = pts[i - 2]
                dx, dy = s[0] - a[0], s[1] - a[1]
                d = math.hypot(dx, dy)
                if d > 1e-9:
                    s[4] += dx / d
                    s[5] += dy / d
                    a[4] -= dx / d
                    a[5] -= dy / d
            self._link(i)
        for i in range(last, -1, -1):
            self._link(i)
        for i in range(STALK_SEGS):
            self._link(i)

    def _link(self, i):
        s = self.stalk_pts[i]
        if i == 0:
            sf = self.swell_fac
            ax, ay = self.x + self.rotation[0] * STALK_ROOT * sf, self.y + self.rotation[1] * STALK_ROOT * sf
            dx, dy = ax - s[0], ay - s[1]
            d = math.hypot(dx, dy)
            if d > 1e-9:
                k = (STALK_GAP - d) / d
                s[0] -= dx * k
                s[1] -= dy * k
                s[4] -= dx * k
                s[5] -= dy * k
            return
        a = self.stalk_pts[i - 1]
        dx, dy = a[0] - s[0], a[1] - s[1]
        d = math.hypot(dx, dy)
        if d > 1e-9:
            k = (STALK_GAP - d) / d * 0.5
            s[0] -= dx * k
            s[1] -= dy * k
            s[4] -= dx * k
            s[5] -= dy * k
            a[0] += dx * k
            a[1] += dy * k
            a[4] += dx * k
            a[5] += dy * k

    def _liquid_tick(self, HL):
        if self.liquid > 0.0:
            self.liquid = max(0.0, self.liquid - 1.0 / self.liquid_ticks)
            rng = self._rng
            if (
                rng.random() < DRIP_CHANCE
                and rng.random() < inv_lerp(0.0, 0.5, self.liquid)
                and len(self.drips) < 8
            ):
                a, r = rng.uniform(0.0, math.tau), rng.random()
                if self._bites < BITES:
                    x, y = self.x, self.y
                    vx = self.rotation[0] * 3.0 + math.cos(a) * r * 3.0
                    vy = self.rotation[1] * 3.0 + math.sin(a) * r * 3.0
                else:
                    a2, tip = self.stalk_pts[-2], self.stalk_pts[-1]
                    dx, dy = tip[0] - a2[0], tip[1] - a2[1]
                    d = math.hypot(dx, dy) or 1.0
                    sp = lerp(8.0, 1.0, self.liquid)
                    vx = dx / d * sp + tip[4] + math.cos(a) * 4.0 * r
                    vy = dy / d * sp + tip[5] + math.sin(a) * 4.0 * r
                    u = rng.random()
                    x, y = lerp(tip[2], tip[0], u), lerp(tip[3], tip[1], u)
                self.drips.append(new_drip(x, y, vx, vy, rng))
        if self.drips:
            self.drips = step_drips(self.drips, self.room_gravity, HL)
