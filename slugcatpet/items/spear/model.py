"""矛物理内核：单点质点，自由 / 投掷 / 扎墙 / 扎身四种形态；y↓。"""

from __future__ import annotations

import math
import random as _random

from ...core.chunkphys import aabb_wall_collide, apply_water
from ...core.units import lerp
from ..state import ItemState

RAD = 5.0
MASS = 0.07
GRAVITY = 0.9  # y↓
AIR_FRICTION = 0.999
BOUNCE = 0.4
SURFACE_FRICTION = 0.4
BUOYANCY = 0.4
WATER_FRICTION = 0.98

HALF_LEN = 26.5  # 贴图矛身半长
TIP_PIVOT = 0.85  # 投掷 / 扎身时以靠近矛尖处为轴

THROW_SPEED = 40.0
THROW_LIFT = 1.5  # 横扔时的上抛初速，y↓ 取负
THROWN_LIFT = 0.45  # 投掷态每 tick 抵消的重力
THROWN_WATER_IMMUNITY = 0.9
EXIT_SPEED = 30.0  # 慢过此速脱离投掷态
WEAK_THROW_FRAMES = 18
WEAK_VX = 0.77
STRONG_VX = 1.2
UP_VY = 0.87
AIM_MAX_DEG = 60.0

STICK_RANGE = 560.0  # 离出手点多远以内才可能扎墙
SURE_STICK = 140.0  # 此距离内必扎，外面按概率
STICK_CHANCE = 0.33
STICK_MIN_SPEED = 10.0
TILE = 20.0  # 扎墙位置按格对齐，一格只扎一根
WALL_OUT = 15.0  # 扎墙时矛中心离墙面
BEAM_LEN = 40.0  # 扎墙后当杆用的长度（两格）

SPIN_LO, SPIN_HI = 50.0, 150.0
STILL_MOVE = 4.0
STILL_TICKS = 20
RESPIN_MOVE = 6.0

FREE, THROWN, WALL, BODY = "free", "thrown", "wall", "body"


def _unit(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 1e-9 else (0.0, -1.0)


def _turn(v, deg):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


class Spear:
    edible = False
    throwable = True
    pierces = True  # 扎得进东西
    bulky = True  # 大件：不能双持的猫同时只拿一件
    aims_line = True  # 出手按投掷态飞，矛身朝向只取水平

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
        "mode",
        "rot",
        "last_rot",
        "rotation_speed",
        "spinning",
        "still",
        "vibrate",
        "fling",
        "thrown_by",
        "thrown_x",
        "thrown_y",
        "throw_dir",
        "throw_frames",
        "exit_speed",
        "trace_from",
        "damage",
        "wall_hit",
        "wall",
        "stuck_in",
        "stuck_ang",
        "pinned_to_wall",
        "impaled",
        "geom_dirty",
        "has_been_climbed",
        "collision_layer",
        "collide_with_objects",
        "held_by_hand",
        "behind",
        "unfetchable",
        "fetch_fails",
        "_rng",
        "_id",
        "_contact_floor",
        "_contact_ceil",
        "_contact_x",
        "_impact_cb",
    )

    def __init__(self, x: float, y: float, seed: int = 0):
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
        self.water_y = None  # 外部每 tick 注入水面高；None=无水
        self.room_gravity = 1.0
        self.state = ItemState.FREE
        self.mode = FREE
        self._rng = _random.Random(seed)
        a = self._rng.uniform(0.0, 360.0)
        self.rot = self.last_rot = _turn((0.0, -1.0), a)  # 指向矛尖
        self.rotation_speed = 0.0
        self.spinning = False
        self.still = 0
        self.vibrate = 0
        self.fling = False  # 被光标甩出
        self.thrown_by = None  # 扔出它的猫身体
        self.thrown_x = self.thrown_y = 0.0
        self.throw_dir = (0, 0)
        self.throw_frames = -1
        self.exit_speed = EXIT_SPEED
        self.trace_from = None  # 出手首帧的命中判定起点
        self.damage = 1.0
        self.wall_hit = False  # 本 tick 沿投掷方向撞墙，等外部判定扎不扎
        self.wall = None  # 扎墙：(边 l/r/t/b, 墙面坐标, 沿墙坐标)
        self.stuck_in = None  # 扎身：被扎的 BodyChunk
        self.stuck_ang = 0.0  # 扎身：矛相对身体轴的角度
        self.pinned_to_wall = None  # 扎身且把这一节钉在墙上：钉点
        self.impaled = []  # 串在矛上的小东西 [(物体, 槽位)]
        self.geom_dirty = False  # 扎进 / 拔出墙，路径前提变了
        self.has_been_climbed = False
        self.collision_layer = 2  # 自由态与石头同层互推，投掷 / 扎住时为 0
        self.collide_with_objects = True
        self.held_by_hand = None
        self.behind = False
        self.unfetchable = False
        self.fetch_fails = 0
        self._id = int(seed)
        self._contact_floor = False
        self._contact_ceil = False
        self._contact_x = 0
        self._impact_cb = None
        self.set_random_spin()

    @property
    def pos(self):
        return (self.x, self.y)

    # 形态

    def flying(self) -> bool:
        return self.mode == THROWN and self.state == ItemState.FREE

    def in_flight(self) -> bool:
        """在投掷态或被光标甩出还在飞：能被招架、能和别的飞行武器相撞。"""
        return self.flying() or (self.fling and self.state == ItemState.FREE)

    def set_random_spin(self) -> None:
        sign = -1.0 if self._rng.random() < 0.5 else 1.0
        self.rotation_speed = (
            sign * lerp(SPIN_LO, SPIN_HI, self._rng.random()) * lerp(0.05, 1.0, self.room_gravity)
        )
        self.spinning = True

    def to_free(self) -> None:
        """转自由态（从投掷态脱离、撞墙弹开、被弹开）。"""
        self.mode = FREE
        self.collision_layer = 2
        self.throw_frames = -1
        self.trace_from = None
        self.set_random_spin()

    def bounce_off(self) -> None:
        """撞上扎不进的东西：反向减半并随机偏开。"""
        v = math.hypot(self.vx, self.vy)
        a = self._rng.uniform(0.0, 360.0)
        k = lerp(0.1, 0.4, self._rng.random()) * v
        ox, oy = _turn((0.0, -1.0), a)
        self.vx = self.vx * -0.5 + ox * k
        self.vy = self.vy * -0.5 + oy * k
        self.vibrate = 20
        self.to_free()

    def clash(self, mx, my, dx, dy, speed, rng=None) -> None:
        """和另一件飞行武器迎面相撞：挪向交点，朝 (dx, dy) 以一半速度弹开。"""
        self.x += (mx - self.x) * 0.5
        self.y += (my - self.y) * 0.5
        self.vibrate = 20
        self.to_free()
        self.vx, self.vy = dx * speed * 0.5, dy * speed * 0.5

    def parried(self, dx, dy) -> None:
        """被招架弹开：失去投掷态，朝 (dx, dy) 飞出。"""
        self.fling = False
        self.to_free()
        self.vx, self.vy = dx * 20.0, dy * 20.0

    # 投掷

    def aim_for(self, body, dir_x, origin, target):
        """瞄准 target 的出手方向（单位向量）；够不着返回 None。"""
        sx, sy = origin
        dx = (target[0] - sx) * dir_x
        if dx < 1.0:
            return None
        speed = THROW_SPEED * (0.5 if body.exhausted else 1.0)
        skill = body.stats.throw_skill
        kx = WEAK_VX if skill == 0 else (STRONG_VX if skill == 2 else 1.0)
        frames = WEAK_THROW_FRAMES if skill == 0 else None
        g = (self.gravity - THROWN_LIFT) * self.room_gravity
        best, best_err = None, None
        step = 0.5
        a = -AIM_MAX_DEG
        while a <= AIM_MAX_DEG:
            t = math.radians(a)
            vx = math.cos(t) * speed * kx
            vy = -math.sin(t) * speed
            n = dx / vx
            if frames is None or n <= frames:
                y = sy + vy * n + 0.5 * g * n * (n + 1.0)
                err = abs(y - target[1])
                if best_err is None or err < best_err:
                    best, best_err = a, err
            a += step
        if best is None or best_err > 4.0:
            return None
        t = math.radians(best)
        return (math.cos(t) * dir_x, -math.sin(t))

    def on_thrown(self, throw) -> None:
        """按投掷方向与力气定初速、投掷时长与伤害；throw.aim 给定时朝该方向出手，矛身仍取水平。"""
        by = throw.by
        dx, dy = throw.dir_x, throw.dir_y
        frc = throw.force
        c0 = by.chunk0
        aim = getattr(throw, "aim", None)
        if aim is not None:
            self.vx = aim[0] * THROW_SPEED * frc
            self.vy = aim[1] * THROW_SPEED * frc
        elif dx:
            self.vx = c0.vx * 0.2 + dx * THROW_SPEED * frc
            self.vy = c0.vy * 0.5 - THROW_LIFT
        else:
            self.vx = c0.vx * 0.5
            self.vy = dy * THROW_SPEED * frc
        self.exit_speed = EXIT_SPEED if frc >= 1.0 else min(EXIT_SPEED, frc * 20.0)
        self.throw_frames = -1
        self.damage = 1.0
        skill = by.stats.throw_skill
        if skill == 0:
            self.throw_frames = WEAK_THROW_FRAMES
            self.damage = 0.6 + 0.3 * self._rng.random() ** 4
            self.vx *= WEAK_VX
        elif dy < 0:
            self.damage = 0.8
            self.vy *= UP_VY
        elif skill == 2:
            self.damage = 1.25
            self.vx *= STRONG_VX
        self.mode = THROWN
        self.collision_layer = 0
        self.thrown_by = by
        self.thrown_x, self.thrown_y = self.x, self.y
        self.throw_dir = (dx, dy)
        self.trace_from = (c0.x - dx * 10.0, c0.y - dy * 10.0)
        self.rot = self.last_rot = (float(dx), float(dy))
        self.rotation_speed = 0.0
        self.spinning = False
        self.fling = False
        self.wall_hit = False

    def on_flung(self) -> None:
        """被光标甩出：自由态打转，不进投掷态。"""
        self.mode = FREE
        self.fling = True
        self.thrown_by = None
        self.set_random_spin()

    # 扎墙

    def wall_spot(self, WL, HL):
        """投掷方向上要扎进的位置：(边 l/r/t/b, 墙面坐标, 沿墙按格对齐的坐标)。"""
        dx, dy = self.throw_dir
        if dx:
            side, face = ("l", 0.0) if dx < 0 else ("r", WL)
            along = (math.floor(self.y / TILE) + 0.5) * TILE
        else:
            side, face = ("t", 0.0) if dy < 0 else ("b", HL)
            along = (math.floor(self.x / TILE) + 0.5) * TILE
        return side, face, along

    def stick(self, WL, HL) -> None:
        """扎进投掷方向上的墙；墙外露出的一截当杆用。"""
        dx, dy = self.throw_dir
        self.wall = self.wall_spot(WL, HL)
        self.wall_hit = False
        self._place_on_wall()
        self.rot = self.last_rot = (float(dx), float(dy))
        self.last_x, self.last_y = self.x, self.y
        self.vx = self.vy = 0.0
        self.mode = WALL
        self.state = ItemState.STUCK
        self.collision_layer = 0
        self.rotation_speed = 0.0
        self.spinning = False
        self.vibrate = 10
        self.geom_dirty = True

    def _place_on_wall(self) -> None:
        side, face, along = self.wall
        ox, oy = self._out()
        if side in ("l", "r"):
            self.x, self.y = face + ox * WALL_OUT, along
        else:
            self.x, self.y = along, face + oy * WALL_OUT

    def _out(self):
        """扎墙时离开墙面的方向。"""
        side = self.wall[0]
        return {"l": (1.0, 0.0), "r": (-1.0, 0.0), "t": (0.0, 1.0), "b": (0.0, -1.0)}[side]

    def pull_out(self) -> None:
        """从墙里或身上拔出；状态由拔它的一方设。"""
        if self.mode == WALL:
            self.geom_dirty = True
        self.wall = None
        self.stuck_in = None
        self.pinned_to_wall = None
        self.mode = FREE
        self.collision_layer = 2
        self.vibrate = 20

    def shift_floor(self, old, new) -> None:
        if self.wall is not None and self.wall[0] == "b":
            side, face, along = self.wall
            self.wall = (side, new, along)
            self._place_on_wall()
            self.last_x, self.last_y = self.x, self.y

    # 当杆用（扎墙时）

    @property
    def kind(self):
        side = self.wall[0] if self.wall is not None else "l"
        return "horizontal" if side in ("l", "r") else "vertical"

    @property
    def grounded(self) -> bool:
        """竖着扎在地上（底端着地）。"""
        return self.wall is not None and self.wall[0] == "b"

    def _beam(self):
        side, face, along = self.wall
        ox, oy = self._out()
        if side in ("l", "r"):
            return face, along, face + ox * BEAM_LEN, along
        return along, face, along, face + oy * BEAM_LEN

    @property
    def ax(self):
        return self._beam()[0]

    @property
    def ay(self):
        return self._beam()[1]

    @property
    def bx(self):
        return self._beam()[2]

    @property
    def by(self):
        return self._beam()[3]

    @property
    def top_y(self):
        b = self._beam()
        return min(b[1], b[3])

    # 扎身

    def lodge(self, chunk, body_ang, pin=None) -> None:
        """扎进一节身体；pin 给定时把这一节钉在该墙点上。"""
        self.stuck_in = chunk
        a = math.degrees(math.atan2(self.rot[0], -self.rot[1]))
        self.stuck_ang = a - body_ang
        self.pinned_to_wall = pin
        self.mode = BODY
        self.state = ItemState.STUCK
        self.collision_layer = 0
        self.vx = self.vy = 0.0
        self.rotation_speed = 0.0
        self.spinning = False

    def follow_body(self, body_ang) -> None:
        c = self.stuck_in
        self.last_x, self.last_y = self.x, self.y
        self.last_rot = self.rot
        if self.pinned_to_wall is not None:
            c.x, c.y = self.pinned_to_wall
            c.vx = c.vy = 0.0
        self.x, self.y = c.x, c.y
        self.rot = _turn((0.0, -1.0), self.stuck_ang + body_ang)

    def tip(self):
        """矛尖位置。"""
        k = HALF_LEN * (1.0 - TIP_PIVOT) * 2.0 if self.pivot_at_tip() else HALF_LEN
        return self.x + self.rot[0] * k, self.y + self.rot[1] * k

    def pivot_at_tip(self) -> bool:
        return self.mode in (THROWN, BODY)

    # 手持 / 物体接口

    def collision_chunks(self):
        self.collide_with_objects = (
            self.state not in (ItemState.CARRIED, ItemState.MOUSE, ItemState.GONE, ItemState.STUCK)
            and self.mode == FREE
        )
        return (self,)

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        self.last_rot = self.rot

    def set_held_direction(self, dx: float, dy: float) -> None:
        self.last_rot = self.rot
        self.rot = _unit(dx, dy)

    def at_rest_on_ground(self, HL: float) -> bool:
        return (
            self.mode == FREE and self.y + self.rad >= HL - 0.5 and abs(self.vx) < 0.6 and abs(self.vy) < 0.6
        )

    # 推进

    def step(self, WL: float, HL: float) -> None:
        if self.vibrate > 0:
            self.vibrate -= 1
        if self.state in (ItemState.MOUSE, ItemState.CARRIED):
            self._contact_floor = False
            return
        if self.state == ItemState.GONE or self.mode in (WALL, BODY):
            self.last_x, self.last_y = self.x, self.y
            self.last_rot = self.rot
            return

        self.last_x, self.last_y = self.x, self.y
        self.last_rot = self.rot
        if self.rotation_speed:
            self.rot = _unit(*_turn(self.rot, self.rotation_speed))

        thrown = self.mode == THROWN
        if thrown:
            if self.throw_frames > 0:
                self.throw_frames -= 1
            if math.hypot(self.vx, self.vy) < self.exit_speed or self.throw_frames == 0:
                self.to_free()
                thrown = False

        self.vy += self.gravity * self.room_gravity
        if thrown:
            self.vy -= THROWN_LIFT * self.room_gravity
        apply_water(
            self,
            self.water_y,
            self.buoyancy,
            self.water_friction,
            self.room_gravity,
            self.air_friction,
            THROWN_WATER_IMMUNITY if thrown else 0.0,
        )
        self.x += self.vx
        self.y += self.vy
        aabb_wall_collide(self, WL, HL, impact=self._impact_cb)

        if thrown:
            dx, dy = self.throw_dir
            hit = (
                (dx and self._contact_x == dx)
                or (dy > 0 and self._contact_floor)
                or (dy < 0 and self._contact_ceil)
            )
            self.wall_hit = bool(hit)
            return

        moved = math.hypot(self.x - self.last_x, self.y - self.last_y)
        sub = self.water_y is not None and self.y + self.rad > self.water_y
        if sub and abs(self.rotation_speed) > 5.0:
            self.rotation_speed *= 0.7
        if self.spinning:
            self.still = self.still + 1 if moved < STILL_MOVE * self.room_gravity else 0
            if self._contact_floor or self.still > STILL_TICKS:
                self.spinning = False
                self.rotation_speed = 0.0
                self.rot = _turn((0.0, 1.0), lerp(-50.0, 50.0, self._rng.random()))
                self.vx = self.vy = 0.0
        elif moved > RESPIN_MOVE:
            self.set_random_spin()
        if self.fling and math.hypot(self.vx, self.vy) < 8.0:
            self.fling = False

    def hit_wall(self) -> None:
        """撞墙没扎进：打着转弹开。"""
        self.wall_hit = False
        self.to_free()
