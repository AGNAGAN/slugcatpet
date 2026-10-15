"""蝙蝠 batfly 物理核心；y↓。"""

from __future__ import annotations
import math
import random as _random

from ...core.chunkphys import aabb_wall_collide, apply_water
from ...core.units import lerp, inv_lerp, clampf
from ..base import HIT_SLAM, HIT_SPEAR, HIT_STONE
from ..state import ItemState
from .gfx import update_render
from ...core.vecmath import _dist, _dirvec

RAD, MASS = 6.0, 0.05
GRAVITY = 0.9
AIR_FRICTION, BOUNCE = 0.98, 0.1
SURFACE_FRICTION, SURFACE_FRICTION_DEAD = 0.5, 0.3
WATER_FRICTION, BUOYANCY = 0.9, 0.94
DROWN_RATE = 0.0125
BITES = 3
VEL_DAMP = 0.92
GRAV_FLY_FAC = 0.45
DIR_ACCEL_X = 0.6
FLAP_THRUST_LO, FLAP_THRUST_HI, FLAP_THRUST_POW = 1.1, 1.7, 1.5
FLAPSPEED_DOWN_A, FLAPSPEED_DOWN_B = -0.04, 0.15
FLAPSPEED_UP_A, FLAPSPEED_UP_B = 0.2, 0.8
WALL_REFLECT_X = -6.0
WATER_JUMP = 7.0  # y↓ 取负
EATEN_COUNTDOWN = 3
HELD_DIE_CHANCE = 1.0 / 160.0  # 活着被拿在手里时每 tick 死掉的概率
STONE_KILL_CHANCE = 0.8  # 被石头砸中时砸死的概率，不然砸晕
STONE_STUN_TICKS = 80

WANDER_REPICK_TICKS, WANDER_REACH, WANDER_MARGIN = 180, 30.0, 24.0
STUCK_DIST, STUCK_TICKS, STUCK_KICK = 40.0, 40, 2.0
EXHAUST_FLAPS, EXHAUST_RECOVER = 34, 12


def _deg_to_vec(deg):
    """角度转单位向量的 y↓ 镜像：0°=上 (0,-1)。"""
    t = math.radians(deg)
    return (math.sin(t), -math.cos(t))


class BatFly:
    """单节小飞虫：扑翅游荡，飞累落地即死，可手动喂给猫；接口同 Fruit。"""

    collision_layer = 0  # 层 0：不参与物体间碰撞
    edible = True
    throwable = False
    creature = True

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
        "drown",
        "_contact_floor",
        "_contact_x",
        "_impact_cb",
        "state",
        "held_by_hand",
        "stalk",
        "bites",
        "dead",
        "stun",
        "eaten",
        "is_meat",
        "_id",
        "collide_with_objects",
        "flap",
        "flap_speed",
        "flap_depth",
        "last_flap_depth",
        "dir_x",
        "dir_y",
        "lower_x",
        "lower_y",
        "last_lower_x",
        "last_lower_y",
        "lower_vx",
        "lower_vy",
        "wings",
        "_death_wing",
        "steer",
        "last_steer",
        "facing",
        "rotation",
        "last_rotation",
        "goal",
        "_grounded",
        "_flaps_since_rest",
        "_exhausted",
        "_goal_timer",
        "_stuck_ref",
        "_stuck_timer",
        "_rng",
    )

    def __init__(self, x: float, y: float, seed: int = 0):
        self.x = self.last_x = self.lower_x = self.last_lower_x = float(x)
        self.y = self.last_y = self.lower_y = self.last_lower_y = float(y)
        self.vx = self.vy = self.lower_vx = self.lower_vy = 0.0
        self.rad, self.mass, self.gravity = RAD, MASS, GRAVITY
        self.air_friction, self.bounce = AIR_FRICTION, BOUNCE
        self.surface_friction, self.buoyancy, self.water_friction = SURFACE_FRICTION, BUOYANCY, WATER_FRICTION
        self.water_y = None  # 水面高度，由外部每 tick 写入；None 为无水
        self.room_gravity, self.drown = 1.0, 0.0
        self._contact_floor, self._contact_x, self._impact_cb = False, 0, None
        self.state = ItemState.FREE
        self.held_by_hand = None
        self.stalk = None  # 恒为 None，只为和果子接口一致
        self.bites, self.dead, self.eaten = BITES, False, 0
        self.stun = 0  # 被砸晕的剩余帧：掉下来不扑翅
        self.is_meat = True
        self._id, self.collide_with_objects = int(seed), True
        rng = self._rng = _random.Random(seed)
        self.flap = rng.random()
        self.flap_speed = rng.random() + 0.1
        self.flap_depth = self.last_flap_depth = 0.0
        self.dir_x, self.dir_y = 0.0, -1.0
        f = self.flap
        self.wings = [[f, f], [f, f]]  # [i][0]=今 [i][1]=昨；i=0 左 1 右
        self._death_wing = (rng.random(), rng.random())
        self.steer = self.last_steer = 0.0
        self.facing = "right"
        self.rotation = self.last_rotation = (0.0, -1.0)  # 被叼/死态朝向（尖朝上）
        self.goal = (self.x + rng.uniform(-50.0, 50.0), self.y + rng.uniform(-50.0, 50.0))
        self._grounded, self._flaps_since_rest, self._exhausted = False, 0, False
        self._goal_timer, self._stuck_ref, self._stuck_timer = 0, (self.x, self.y), 0

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def fetch_ready(self):
        # 飞着够不到，落地或死了才能抓
        return self.state == ItemState.FREE and self.held_by_hand is None and (self.dead or self._grounded)

    @property
    def huntable(self):
        return not self._grounded

    def struck(self, how, rng=None) -> None:
        """被武器打中：矛和撞击必死，石头多半砸死、不然砸晕。"""
        if how == HIT_STONE and rng.random() >= STONE_KILL_CHANCE:
            self.stun = STONE_STUN_TICKS
        elif how in (HIT_STONE, HIT_SPEAR, HIT_SLAM):
            self.die()

    def collision_chunks(self):
        # 被拿着、拖着、吃掉或消失时不参与碰撞
        self.collide_with_objects = not (
            self.state in (ItemState.CARRIED, ItemState.MOUSE, ItemState.EATEN, ItemState.GONE)
            or self.held_by_hand is not None
        )
        return (self,)

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        self.last_rotation = self.rotation
        dx, dy = _dirvec(self.x, self.y, gx, gy)
        px, py = (dy, -dx)
        self.rotation = (px, py) if self.dead else (px, -abs(py))

    def step(self, WL: float, HL: float) -> None:
        st = self.state
        if st == ItemState.EATEN or st == ItemState.GONE:
            return
        self.last_flap_depth = self.flap_depth
        if st == ItemState.CARRIED:
            self.last_x, self.last_y = self.x, self.y
            if not self.dead and (self.bites < BITES or self._rng.random() < HELD_DIE_CHANCE):
                self.die()
            if not self.dead:
                self._flap_wings()  # 活着被拿着时乱扑
            update_render(self, self._submersion())
            self._eaten_countdown()
            return
        if st == ItemState.MOUSE:
            self.last_x, self.last_y = self.x, self.y
            update_render(self, self._submersion())
            self._eaten_countdown()
            return
        self.last_x, self.last_y = self.x, self.y
        sub = self._submersion()
        if self.stun > 0:
            self.stun -= 1
        if not self.dead and self.stun <= 0 and sub == 0.0:
            self._batflight()
        else:
            if not self.dead and sub > 0.0:
                self._water_behavior(sub)
            self.vy += self.gravity * self.room_gravity  # 水中或死了受全重力，浮力另算
        apply_water(
            self, self.water_y, self.buoyancy, self.water_friction, self.room_gravity, self.air_friction
        )
        self.x += self.vx
        self.y += self.vy
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)
        if not self.dead and self.flap_speed > 0.0 and self._contact_x != 0:
            self.vx = self._contact_x * WALL_REFLECT_X
        self._grounded = self._contact_floor
        if not self.dead:
            self.drown = clampf(self.drown + DROWN_RATE * (1.0 if sub == 1.0 else -1.0), 0.0, 1.0)
            if self.drown >= 1.0:
                self.die()
            self._exhaust()
            self._wander(WL, HL)
        update_render(self, sub)
        if not self.dead and (self.state == ItemState.CARRIED or self.bites < BITES):
            self.die()
        self._eaten_countdown()

    def _submersion(self) -> float:
        """浸没度：无水为 0，全浸为 1。"""
        if self.water_y is None:
            return 0.0
        s = (self.y + self.rad - self.water_y) / (2.0 * self.rad)
        if s < 0.0:
            return 0.0
        return 1.0 if s > 1.0 else s

    def _batflight(self) -> None:
        """扑翅飞行：一冲一沉朝 goal 游走。"""
        dx, dy = _dirvec(self.x, self.y, self.goal[0], self.goal[1])
        self.dir_x, self.dir_y = dx, dy
        if dx > 0.1:
            self.facing = "right"
        elif dx < -0.1:
            self.facing = "left"
        self.flap_depth = inv_lerp(1.0, -1.0, dy)  # y↓：goal 在上→1
        self.vx *= VEL_DAMP
        self.vy *= VEL_DAMP
        self.vy += self.gravity * self.room_gravity * GRAV_FLY_FAC  # 下坠 +；零重力=0
        self.vx += dx * DIR_ACCEL_X
        if self.flap_speed > 0.0 and not self._exhausted:
            self.vy -= (1.0 + self.flap_speed) ** FLAP_THRUST_POW * lerp(
                FLAP_THRUST_LO, FLAP_THRUST_HI, self.flap_depth
            )
        self._flap_wings()

    def _flap_wings(self) -> None:
        """翅膀一扇一收。"""
        self.flap += self.flap_speed
        if self.flap_speed > 0.0:
            if self.flap > 1.0:
                self.flap = 1.0
                self.flap_speed = FLAPSPEED_DOWN_A - self.flap_depth * FLAPSPEED_DOWN_B
                self._flaps_since_rest += 1
        elif self.flap_speed < 0.0 and self.flap < 0.0:
            self.flap = 0.0
            self.flap_speed = FLAPSPEED_UP_A + self.flap_depth * FLAPSPEED_UP_B

    def _water_behavior(self, sub: float) -> None:
        if sub == 1.0:
            self.flap = clampf(self.flap + lerp(-1.0, 1.0, self._rng.random()) * 0.1, 0.0, 1.0)
            kx, ky = _deg_to_vec(-45.0 + 90.0 * self._rng.random())
            self.vx += kx * 0.75
            self.vy += ky * 0.75
        elif self.held_by_hand is None:
            self.vy -= WATER_JUMP

    def _exhaust(self) -> None:
        """扑翅次数攒满就力竭，力竭后落地即死；碰墙或落地时恢复。"""
        if self._flaps_since_rest >= EXHAUST_FLAPS:
            self._exhausted = True
        if self._exhausted and self._contact_floor and self.room_gravity > 1e-6:
            self.die()
        elif self._contact_x != 0 or self._contact_floor:
            self._flaps_since_rest = max(0, self._flaps_since_rest - EXHAUST_RECOVER)
            if self._flaps_since_rest == 0:
                self._exhausted = False

    def _wander(self, WL: float, HL: float) -> None:
        self._goal_timer += 1
        if (
            _dist(self.x, self.y, self.goal[0], self.goal[1]) < WANDER_REACH
            or self._goal_timer >= WANDER_REPICK_TICKS
        ):
            self._pick_goal(WL, HL)
        self._stuck_timer += 1
        if self._stuck_timer >= STUCK_TICKS:
            if _dist(self.x, self.y, self._stuck_ref[0], self._stuck_ref[1]) < STUCK_DIST:
                kx, ky = _deg_to_vec(self._rng.random() * 360.0)
                self.vx += kx * STUCK_KICK
                self.vy += ky * STUCK_KICK
            self._stuck_ref = (self.x, self.y)
            self._stuck_timer = 0

    def _pick_goal(self, WL: float, HL: float) -> None:
        m = WANDER_MARGIN
        self.goal = (self._rng.uniform(m, max(m, WL - m)), self._rng.uniform(m, max(m, HL - m)))
        self._goal_timer = 0

    def _eaten_countdown(self) -> None:
        if self.eaten > 0:
            self.eaten -= 1
            if self.eaten == 0:
                self.state = ItemState.EATEN

    def bite(self) -> bool:
        """被咬一口；吃完时返回 True，可结算食物。"""
        self.bites -= 1
        if not self.dead:
            self.die()
        if self.bites < 1 and self.eaten == 0:
            self.eaten = EATEN_COUNTDOWN
            return True
        return False

    def die(self) -> None:
        self.dead = True
        self.surface_friction = SURFACE_FRICTION_DEAD
