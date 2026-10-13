"""石头物理内核：单点质点，重力积分+碰撞+自旋。"""

from __future__ import annotations
import math
import random
from ...core.chunkphys import aabb_wall_collide, apply_water
from ...core.units import lerp
from ..state import ItemState

RAD = 5.0
MASS = 0.07
GRAVITY = 0.9  # y↓
AIR_FRICTION = 0.999
BOUNCE = 0.4
SURFACE_FRICTION = 0.4
BUOYANCY = 0.4  # 沉，高速打水漂
WATER_FRICTION = 0.98

PEBBLE_FRAMES = 14

REST_VEL_EPS = 0.6
EXIT_FLING_SPEED = 8.0  # 脱离投掷阈，同砸晕阈


class Stone:
    collision_layer = 2  # 与 Saint(层1) 不同层
    edible = False
    throwable = True

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
        "state",
        "rotation_deg",
        "last_rotation",
        "spin",
        "vibrate",
        "fling",
        "thrown_by_cat",
        "frame",
        "collide_with_objects",
        "_id",
        "_contact_floor",
        "_contact_ceil",
        "_contact_x",
        "_impact_cb",
        "unfetchable",
        "fetch_fails",
        "held_by_hand",
        "behind",
    )

    def __init__(self, x: float, y: float, seed: int = 0):
        self.x = self.last_x = float(x)
        self.y = self.last_y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.rad = RAD
        self.mass = MASS
        self.gravity = GRAVITY
        self.air_friction = AIR_FRICTION
        self.bounce = BOUNCE
        self.surface_friction = SURFACE_FRICTION
        self.buoyancy = BUOYANCY
        self.water_friction = WATER_FRICTION
        self.water_y = None  # 外部每 tick 注入水面高；None=无水
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.rotation_deg = 0.0
        self.last_rotation = 0.0
        self.spin = 0.0
        self.vibrate = 0
        self.fling = False
        self.thrown_by_cat = False
        self.collide_with_objects = True
        self._id = int(seed)
        self.frame = "Pebble" + str(1 + (int(seed) % PEBBLE_FRAMES))
        self._contact_floor = False
        self._contact_ceil = False
        self._contact_x = 0  # batfly 用，本体不读
        self._impact_cb = None  # 窗口抖动回调；None=不触发
        self.unfetchable = False
        self.fetch_fails = 0
        self.held_by_hand = None
        self.behind = False  # 拿在手里时画到猫身后

    @property
    def pos(self):
        return (self.x, self.y)

    def collision_chunks(self):
        self.collide_with_objects = (
            self.state not in (ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE) and not self.fling
        )
        return (self,)

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        self.last_rotation = self.rotation_deg

    def set_held_direction(self, dx: float, dy: float) -> None:
        """拿在手里时按方向转，取最近的等价角免得插值绕圈。"""
        self.last_rotation = self.rotation_deg
        a = math.degrees(math.atan2(dx, -dy))
        self.rotation_deg += (a - self.rotation_deg + 180.0) % 360.0 - 180.0

    def on_thrown(self, throw) -> None:
        self.spin = throw.dir_x * 8.0
        self.fling = False
        self.thrown_by_cat = True

    def in_flight(self) -> bool:
        """被扔或甩出、还在飞：能被招架、能和别的飞行武器相撞。"""
        return self.fling or self.thrown_by_cat

    def parried(self, dx, dy) -> None:
        """被招架弹开：失去投掷态，朝 (dx, dy) 飞出。"""
        self.fling = False
        self.thrown_by_cat = False
        self.vx, self.vy = dx * 20.0, dy * 20.0
        self.spin = lerp(-100.0, 100.0, random.random()) * lerp(0.05, 1.0, self.room_gravity)

    def clash(self, mx, my, dx, dy, speed, rng) -> None:
        """和另一件飞行武器迎面相撞：挪向交点，朝 (dx, dy) 以一半速度弹开。"""
        self.x += (mx - self.x) * 0.5
        self.y += (my - self.y) * 0.5
        self.vx, self.vy = dx * speed * 0.5, dy * speed * 0.5
        self.vibrate = 20
        self.fling = False
        self.thrown_by_cat = False
        self.spin = rng.uniform(-40.0, 40.0) * lerp(0.05, 1.0, self.room_gravity)

    def at_rest_on_ground(self, HL: float) -> bool:
        return self.y + self.rad >= HL - 0.5 and abs(self.vx) < REST_VEL_EPS and abs(self.vy) < REST_VEL_EPS

    def step(self, WL: float, HL: float) -> None:
        if self.state in (ItemState.MOUSE, ItemState.CARRIED):
            self._contact_floor = False
            return

        self.last_x, self.last_y = self.x, self.y
        self.last_rotation = self.rotation_deg

        if self.state == ItemState.GONE:
            return

        self.rotation_deg += self.spin
        self.vy += self.gravity * self.room_gravity
        apply_water(
            self, self.water_y, self.buoyancy, self.water_friction, self.room_gravity, self.air_friction
        )
        self.x += self.vx
        self.y += self.vy

        self._collide(WL, HL)

        if self._contact_floor or self._contact_ceil:
            self.spin = (self.spin * 2.0 + self.vx * 5.0) / 3.0

        if self.vibrate > 0:
            self.vibrate -= 1

        if (self.fling or self.thrown_by_cat) and (
            self.at_rest_on_ground(HL) or math.hypot(self.vx, self.vy) < EXIT_FLING_SPEED
        ):
            self.fling = False
            self.thrown_by_cat = False

    def _collide(self, WL: float, HL: float) -> None:
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)

    def deflect(self, rng) -> None:
        v = math.hypot(self.vx, self.vy)
        a = rng.uniform(0.0, math.tau)
        mag = rng.uniform(0.1, 0.4) * v
        self.vx = -0.5 * self.vx + math.cos(a) * mag
        self.vy = -0.5 * self.vy + math.sin(a) * mag
        self.vibrate = 20
        self.spin = rng.uniform(-40.0, 40.0) * lerp(0.05, 1.0, self.room_gravity)
