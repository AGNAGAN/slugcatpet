"""Lizard：身体三节 + 寻路驱动的移动、咬 / 叼 / 被光标拖（Act / AttemptBite / Bite / CarryObject / Collide）。

模拟全在房间坐标（y↑）；x / y / vx / vy 属性是给物品宿主用的窗口坐标视图（y↓，身体中心）。
"""

from __future__ import annotations

import math
import random

from . import breeds, sfx, shortcut
from .ai import Behavior, LizardAI
from .gfx import LizardGraphics
from .pather import (
    DOUBLE_REACH_UP,
    DROP_TO_CLIMB,
    DROP_TO_FLOOR,
    LIZARD_TURN,
    OPEN_DIAGONAL,
    REACH_DOWN,
    REACH_OVER_GAP,
    REACH_UP,
    SEMI_DIAGONAL_REACH,
    STANDARD,
    LizardPather,
    MovementConnection,
)
from .physics import (
    Animation,
    BodyChunk,
    BodyChunkConnection,
    Creature,
    tile_xy,
    visual_contact,
    vslerp,
)
from .rw import (
    EIGHT_DIRECTIONS_DIAGONALS_LAST,
    FOUR_DIRECTIONS,
    V2,
    aim_from_one_vector_to_another,
    clamp,
    deg_to_vec,
    dir_vec,
    dist_less,
    distance,
    dot,
    int_clamp,
    int_clamp_at_one,
    inverse_lerp,
    lerp,
    lerp_and_tick,
    lerp_map,
    perpendicular_vector,
    rnv,
    round_to_int,
)
from ..state import ItemState
from .jump import LizardJumpModule
from .tongue import LizardTongue
from .voice import Emotion, LizardVoice
from .terrain import CLIMB, CURVED_FLOOR, FLOOR

_I_CLIMB = breeds.ACC_INDEX[CLIMB]
_TAU = 2.0 * math.pi
HEALTH_FLOOR = 0.1  # 互咬受伤但不会死：health 不低于它
ANIM_STILL = 0.3  # 头 / 尾 / 腿每 tick 动不到这么多（px）算静止
REGEN_PER_TICK = 1.0 / 2400.0  # health / limb_health / throat_health 每 tick 回这么多（约 1 分钟回满）


class Spark:
    """Spark：重力下落的细三角形拖尾；落到实心格上会弹一下，或消失。"""

    def __init__(self, pos: V2, vel: V2, color, gfx, standard_life: int, exceptional_life: int, rng):
        self.life = 1.0
        self.color = color
        self.lizard = gfx
        self.last_pos = self.last_last_pos = self.last_last_last_pos = pos
        self.vel = vel
        self.pos = pos + vel.normalized * (30.0 * rng.random())
        self.gravity = lerp(0.4, 0.9, rng.random())
        self.life_time = max(1, rng.randrange(0, max(1, standard_life)))
        if rng.random() < 0.1:
            self.life_time = max(1, rng.randrange(standard_life, exceptional_life))
        self.dead = False

    def update(self, T) -> None:
        self.last_last_last_pos = self.last_last_pos
        self.last_last_pos = self.last_pos
        self.vel = V2(self.vel.x, self.vel.y - self.gravity)
        self.life -= 1.0 / self.life_time
        if self.lizard is not None and self.lizard.white_flicker < 5:
            self.life -= 0.2
        t = tile_xy(self.pos)
        if T.solid(t):
            if self.vel.y < 0.0 and not T.solid(tile_xy(self.pos + V2(0.0, 20.0))):
                self.pos = V2(self.pos.x, T.middle_of(t).y + 10.0)
                self.vel = V2(self.vel.x, self.vel.y * -0.5)
                if abs(self.vel.y) < 3.0:
                    self.life -= 1.0 / 3.0
            else:
                self.dead = True
        if self.life <= 0.0:
            self.dead = True
        self.last_pos = self.pos
        self.pos = self.pos + self.vel


class FlashOrb:
    """StationaryEffect.FlashingOrb：头盾弹开时在撞击点闪一下，寿命 4 tick。"""

    def __init__(self, pos: V2, gfx):
        self.life = self.last_life = 1.0
        self.pos = self.last_pos = pos
        self.lizard = gfx
        self.dead = False

    def update(self, T) -> None:
        self.last_life = self.life
        self.life -= 0.25
        if self.lizard is not None and self.lizard.white_flicker < 0:
            self.life = 0.0
        if self.life <= 0.0:
            self.dead = True


class Noise:
    """Noise.InGameNoise：房间坐标；source 是发声的物体。"""

    __slots__ = ("pos", "strength", "source", "interesting")

    def __init__(self, pos: V2, strength: float, source, interesting: float):
        self.pos = pos
        self.strength = strength
        self.source = source
        self.interesting = interesting


def angle_between(a: V2, b: V2) -> float:
    """Vector2.Angle：无符号夹角（度）。"""
    d = a.magnitude * b.magnitude
    if d < 1e-9:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(a, b) / d))))


class Grasp:
    """Creature.Grasp：grabbed 需要 body_chunks / grabbed_by / is_creature，可选 grabbed() / on_released()。"""

    def __init__(
        self, grabber, grabbed, grasp_used: int, chunk_grabbed: int, dominance: float, pacifying: bool
    ):
        self.grabber = grabber
        self.grabbed = grabbed
        self.grasp_used = grasp_used
        self.chunk_grabbed = chunk_grabbed
        self.dominance = dominance
        self.pacifying = pacifying
        self.discontinued = False

    def release(self) -> None:
        self.discontinued = True
        gb = self.grabbed.grabbed_by
        if self in gb:
            gb.remove(self)
        if self.grabber.grasps[self.grasp_used] is self:
            self.grabber.grasps[self.grasp_used] = None
        cb = getattr(self.grabbed, "on_released", None)
        if cb is not None:
            cb(self)


class CursorGrasp(Grasp):
    """光标拖着蜥蜴：pacifying 让它晕到松手（Creature.Update 里 stun=10），之后走「被抓」的挣扎分支。"""

    def __init__(self, lizard: Lizard, chunk: int):
        self.grasps = [self]  # 兼作抓握者，供 grabbed_by 的清理判断
        super().__init__(self, lizard, 0, chunk, 1e9, True)
        lizard.grabbed_by.append(self)

    is_creature = False


class _Drag:
    __slots__ = ("index", "target", "vel", "grasp")

    def __init__(self, index: int, target: V2, grasp: CursorGrasp):
        self.index = index
        self.target = target
        self.vel = V2()
        self.grasp = grasp


class _Dest:
    """MovementAnimation 的单个身体目标。"""

    __slots__ = ("body_part", "destination", "finished_dist", "max_distance")

    def __init__(self, chunk: BodyChunk, destination: V2, finished_dist: float):
        self.body_part = chunk.index
        self.destination = destination
        self.finished_dist = finished_dist
        self.max_distance = distance(chunk.pos, destination) + 10.0


class MovementAnimation:
    """跨越缺口 / 转身 / 对角这类需要身体各节依次伸过去的连接。"""

    def __init__(
        self, parent: Lizard, connection: MovementConnection, step: int, friction: float, speed: float
    ):
        self.parent = parent
        self.connection = connection
        self.step = step
        self.friction = friction
        self.speed = speed
        self.finished = False
        self.total_steps = 0
        self.destinations: list[_Dest] = []
        c = parent.body_chunks
        mid = parent.mid
        s, d = connection.start_coord, connection.destination_coord
        t = connection.type
        if t == STANDARD:
            self.total_steps = 1
            self.destinations = [_Dest(c[0], mid(d), 5.0), _Dest(c[2], mid(s), 5.0)]
        elif t == REACH_OVER_GAP or t == REACH_UP or t == REACH_DOWN:
            self.total_steps = 2
            if step == 1:
                self.destinations = [_Dest(c[0], (mid(s) + mid(d)) * 0.5, 10.0)]
                return
            self.destinations = [
                _Dest(c[0], mid(d), 5.0),
                _Dest(c[1], (mid(s) + mid(d)) * 0.5, 100.0),
                _Dest(c[2], mid(s), 12.0),
            ]
        elif t == SEMI_DIAGONAL_REACH:
            self.total_steps = 1
            self.destinations = [_Dest(c[0], mid(d), 5.0), _Dest(c[2], mid(s), 15.0)]
        elif t == DOUBLE_REACH_UP:
            self.total_steps = 1
            self.destinations = [_Dest(c[0], mid(d), 5.0), _Dest(c[2], (mid(d) + mid(s)) * 0.5, 15.0)]
        elif t == LIZARD_TURN:
            self.total_steps = 2
            up = (0, 1)
            if step == 1:
                self.destinations = [
                    _Dest(c[0], mid(s), 8.0),
                    _Dest(c[1], mid((s[0] + up[0], s[1] + up[1])), 9.0),
                    _Dest(c[2], mid((d[0] + up[0], d[1] + up[1])), 10.0),
                ]
            else:
                self.destinations = [
                    _Dest(c[0], mid(d), 5.0),
                    _Dest(c[1], mid(s), 5.0),
                    _Dest(c[2], mid((s[0] + up[0], s[1] + up[1])), 8.0),
                ]
        elif t == DROP_TO_CLIMB:
            self.total_steps = 1
            self.destinations = [_Dest(c[0], mid(d) + V2(0.0, 5.0), 5.0), _Dest(c[1], mid(s), 12.0)]

    def update(self, speed_fac: float) -> None:
        p = self.parent
        rng = p.rng
        self.finished = True
        flag = False
        for dst in self.destinations:
            chunk = p.body_chunks[dst.body_part]
            if self.finished and not dist_less(chunk.pos, dst.destination, dst.finished_dist):
                self.finished = False
            chunk.vel = chunk.vel * self.friction
            num = self.speed * (p.body_force if dst.body_part == 0 else 1.0) * p.ai.run_speed**0.2
            if dist_less(chunk.pos, dst.destination, num):
                num = distance(chunk.pos, dst.destination)
            num *= p.body_desperation * p.lizard_params.max_muscle_power * 2.0 * rng.random() + 1.0
            chunk.vel = chunk.vel + dir_vec(chunk.pos, dst.destination) * (num * speed_fac)
            chunk.vel = chunk.vel + deg_to_vec(rng.random() * 360.0) * (
                p.body_desperation * p.lizard_params.max_muscle_power * 2.0 * rng.random() * self.speed
            )
            if not dist_less(chunk.pos, dst.destination, dst.max_distance):
                self.finished = True
                flag = True
                break
        if self.finished:
            if self.step < self.total_steps and not flag:
                p.movement_animation = MovementAnimation(
                    p, self.connection, self.step + 1, self.friction, self.speed
                )
            else:
                p.movement_animation_ended(self.connection, not flag)


class Lizard(Creature):
    Animation = Animation
    is_creature = True
    creature = True  # 物品宿主的「活物」标记
    predator = True  # 蛋虫怕它
    rad = 0.0  # 宿主的出界夹回按身体中心算，不另加半径
    dissolve = -1
    held_by_hand = None

    def __init__(self, x_room: float, y_room: float, breed_key: str, seed: int):
        super().__init__()
        p = breeds.get(breed_key)
        self.lizard_params = p
        self.seed = seed
        self.rng = random.Random(seed * 7919 + 13)
        self.effect_color = breeds.effect_color(breed_key, random.Random(seed))
        rad = 8.0 * p.body_size_fac * p.body_rad_fac
        mass = p.body_mass / 3.0
        origin = V2(float(x_room), float(y_room))
        self.body_chunks = [BodyChunk(self, i, origin, rad, mass) for i in range(3)]
        c = self.body_chunks
        length = 17.0 * p.body_length_fac * ((p.body_size_fac + 1.0) / 2.0)
        self.body_chunk_connections = [
            BodyChunkConnection(c[0], c[1], length, BodyChunkConnection.NORMAL, 0.95, 0.5),
            BodyChunkConnection(c[1], c[2], length, BodyChunkConnection.NORMAL, 0.95, 0.5),
            BodyChunkConnection(
                c[0],
                c[2],
                length * (1.0 + p.body_stiffnes),
                BodyChunkConnection.PUSH,
                1.0 - lerp(0.9, 0.5, p.body_stiffnes),
                0.5,
            ),
        ]
        self.animation = Animation.Standard
        self.air_friction = 0.999
        self.gravity = 0.9
        self.bounce = 0.1
        self.surface_friction = 0.5

        self.limb_health = [1.0, 1.0, 1.0, 1.0]
        self._jaw_open = 0.0
        self.last_jaw_open = 0.0
        self.jaw_forced_shut = 0.0
        self.bite_delay = 0
        self.lounge_dir = V2()
        self.bubble = 0
        self.bubble_intensity = 0.0
        self.lounge_delay = 0
        self.post_lounge_stun = 0
        self.time_in_animation = 0
        self.time_to_remain_in_animation = 0
        self.upcoming_connections: list[MovementConnection] = []
        self.following_connection: MovementConnection | None = None
        self.last_following_connection: MovementConnection | None = None
        self.commited_to_drop_connection: MovementConnection | None = None
        self.movement_animation: MovementAnimation | None = None
        self.apply_gravity = False
        self.in_allowed_terrain_counter = 0
        self.grip_point: V2 | None = None
        self.time_spent_trying_this_move = 0
        self.desperation_smoother = 0.0
        self.limbs_aim_for = V2()
        self.straighten_out_needed = 0.0
        self.narrow_upcoming = False
        self.climb_upcoming = False
        self.body_wiggle = 0.0
        self._bwc = 0
        self.grabbed_attack_counter = 0
        self.health = 1.0
        self.throat_health = 1.0
        self.kind_key = p.key
        self.visibility_bonus = 0.0
        self.voice = LizardVoice(self)
        self.ctx = None
        self.drag: _Drag | None = None
        self.state = ItemState.FREE
        self.last_x = self.last_y = 0.0
        self.room_gravity = 1.0
        self.water_y = None
        self._id = seed
        self._fvx = self._fvy = 0.0  # 被拖时光标的速度（窗口坐标），松手甩出去
        self._mx = self._my = 0.0  # 被拖时光标的位置（窗口坐标）
        self.sc_phase: str | None = None  # 钻出 / 在屏幕外 / 钻回，见 shortcut
        self.sc_hole = V2()
        self.sc_rad_add = 0.0
        self.sc_timer = 0
        self.sc_dir = 1

        self.tongue: LizardTongue | None = LizardTongue(self) if p.tongue else None
        self.jump_module: LizardJumpModule | None = LizardJumpModule(self) if p.key == "cyan" else None
        self.pather = LizardPather(p)
        self.ai = LizardAI(self)
        self.graphics_module: LizardGraphics = LizardGraphics(self, random.Random(seed))
        self.place_in_room(x_room, y_room)

    # 属性

    @property
    def jaw_open(self) -> float:
        if self.grasps[0] is not None:
            self._jaw_open = 0.0
        if self.tongue is not None and self.tongue.out:
            self._jaw_open = max(self._jaw_open, 0.5)
        if self.jaw_forced_shut > 0.0:
            self._jaw_open = min((1.0 - self.jaw_forced_shut) ** 4, self._jaw_open)
        return self._jaw_open

    @jaw_open.setter
    def jaw_open(self, value: float) -> None:
        self._jaw_open = clamp(value, 0.0, 1.0) if self.grasps[0] is None else 0.0

    @property
    def represented_creature(self) -> Lizard:
        return self

    @property
    def realized_creature(self) -> Lizard | None:
        return None if self.sc_phase == shortcut.AWAY else self

    @property
    def in_shortcut(self) -> bool:
        return self.sc_phase is not None

    @property
    def danger_pos(self) -> V2:
        t = self.tongue
        if t is not None and t.state == "LashingOut":
            return t.pos
        return self.body_chunks[0].pos

    @property
    def body_size(self) -> float:
        return self.lizard_params.body_size

    scaryness = 1.0

    @property
    def eating(self) -> bool:
        """走不到屏幕边缘、就地吃着叼着的猎物：护食，别的蜥蜴抢不走（原版在窝里吃，不会被抢；
        就地吃不护食的话一只猎物会被抢来抢去吃不完）。"""
        return self.grasps[0] is not None and self.ai.eat_counter > 0

    @property
    def jaw_ready_for_bite(self) -> bool:
        return self.jaw_open > 0.9 and self.bite_delay == 0

    @property
    def is_wall_climber(self) -> bool:
        return False

    @property
    def body_direction(self) -> int:
        c = self.body_chunks
        a = aim_from_one_vector_to_another(c[1].pos, c[0].pos)
        return (round_to_int((-a + 180.0) / 90.0) + 1) % 4

    @property
    def body_force(self) -> float:
        return clamp(self.desperation_smoother * 0.025, 1.0, self.lizard_params.max_muscle_power)

    @property
    def body_desperation(self) -> float:
        return inverse_lerp(120.0, 400.0, self.desperation_smoother)

    @property
    def legs_gripping(self) -> int:
        return self.graphics_module.legs_grabbing

    @property
    def no_grip_counter(self) -> int:
        return self.graphics_module.no_grip_counter

    @property
    def body_wiggle_fac(self) -> float:
        p = self.lizard_params
        return clamp((self.body_wiggle_counter - p.wiggle_delay) / (50.0 + p.wiggle_delay), 0.0, 1.0)

    @property
    def body_wiggle_counter(self) -> int:
        return self._bwc

    @body_wiggle_counter.setter
    def body_wiggle_counter(self, v: int) -> None:
        self._bwc = int_clamp(int(v), 0, 100)

    # 宿主用的窗口坐标视图（y↓，身体三节的平均）

    @property
    def _HL(self) -> float:
        return self.terrain.HL if self.terrain is not None else 0.0

    @property
    def x(self) -> float:
        c = self.body_chunks
        return (c[0].pos.x + c[1].pos.x + c[2].pos.x) / 3.0

    @x.setter
    def x(self, v: float) -> None:
        if self.state == ItemState.MOUSE:
            self._mx = v
        else:
            self._shift(v - self.x, 0.0)

    @property
    def y(self) -> float:
        c = self.body_chunks
        return self._HL - (c[0].pos.y + c[1].pos.y + c[2].pos.y) / 3.0

    @y.setter
    def y(self, v: float) -> None:
        if self.state == ItemState.MOUSE:
            self._my = v
        else:
            self._shift(0.0, self.y - v)

    @property
    def animating(self) -> bool:
        """身体不动时头、尾、腿也常在动（张望、甩尾）：窗口据此保持高帧率。"""
        if self.sc_phase == shortcut.AWAY:
            return False
        g = self.graphics_module
        for part in (g.head, *g.tail, *g.limbs):
            if abs(part.pos.x - part.last_pos.x) + abs(part.pos.y - part.last_pos.y) > ANIM_STILL:
                return True
        return False

    @property
    def vx(self) -> float:
        if self.state == ItemState.MOUSE:
            return self._fvx
        c = self.body_chunks
        return (c[0].vel.x + c[1].vel.x + c[2].vel.x) / 3.0

    @vx.setter
    def vx(self, v: float) -> None:
        if self.state == ItemState.MOUSE:
            self._fvx = v
        else:
            for c in self.body_chunks:
                c.vel = V2(v, c.vel.y)

    @property
    def vy(self) -> float:
        if self.state == ItemState.MOUSE:
            return self._fvy
        c = self.body_chunks
        return -(c[0].vel.y + c[1].vel.y + c[2].vel.y) / 3.0

    @vy.setter
    def vy(self, v: float) -> None:
        if self.state == ItemState.MOUSE:
            self._fvy = v
        else:
            for c in self.body_chunks:
                c.vel = V2(c.vel.x, -v)

    def _shift(self, dx: float, dy_room: float) -> None:
        if abs(dx) < 1e-9 and abs(dy_room) < 1e-9:
            return
        d = V2(dx, dy_room)
        for c in self.body_chunks:
            c.pos = c.pos + d
            c.last_pos = c.last_pos + d
            c.last_last_pos = c.last_last_pos + d
        self.graphics_module.reset()

    def dist_to(self, cx: float, cy: float) -> float:
        """窗口坐标点到身体（三节 + 头）表面的最近距离。"""
        hl = self._HL
        best = 1e9
        for c in self.body_chunks:
            best = min(best, math.hypot(cx - c.pos.x, cy - (hl - c.pos.y)) - c.rad)
        h = self.graphics_module.head
        return min(best, math.hypot(cx - h.pos.x, cy - (hl - h.pos.y)) - h.rad)

    # 地形辅助

    def mid(self, tile) -> V2:
        """Room.MiddleOfTile：杆所在格取杆的真实坐标。"""
        return self.terrain.middle_of(tile)

    def _accessible_at(self, pos: V2) -> bool:
        return self.terrain.accessible(tile_xy(pos), self.lizard_params)

    def _ray_trace_in_accessible_tiles(self, a, b) -> bool:
        """PathFinder.RayTraceInAccessibleTiles。"""
        x, y = a
        x2, y2 = b
        num = abs(x2 - x)
        num2 = abs(y2 - y)
        cx, cy = x, y
        count = 1 + num + num2
        sx = 1 if x2 > x else -1
        sy = 1 if y2 > y else -1
        err = num - num2
        num *= 2
        num2 *= 2
        reachable = self.pather.coordinate_reachable_and_getbackable
        while count > 0:
            if not reachable((cx, cy)):
                return False
            if err > 0:
                cx += sx
                err -= num2
            else:
                cy += sy
                err += num
            count -= 1
        return True

    # 放置与步进

    def place_in_room(self, x: float, y: float) -> None:
        """Creature.PlaceInRoom：三节叠在一点（加 1px 随机偏移），速度清零，图形重置。"""
        for ch in self.body_chunks:
            ch.pos = V2(x, y) + deg_to_vec(self.rng.random() * 360.0)
            ch.last_pos = ch.pos
            ch.last_last_pos = ch.pos
            ch.set_pos = None
            ch.vel = V2()
        self.pos_tile = tile_xy(self.body_chunks[0].pos)
        self.graphics_module.reset()
        self.graphics_module.look_at_nothing()

    def step(self, ctx) -> None:
        self.ctx = ctx
        if ctx.terrain is not self.terrain:
            self._new_terrain(ctx.terrain)
        self.terrain = ctx.terrain
        self.pather.update(self.terrain, tile_xy(self.body_chunks[0].pos))
        self._pin()
        self.update(not self.even_update)
        self._pin()
        self.graphics_module.update()

    def _new_terrain(self, new) -> None:
        """地形重建（放 / 删杆、窗口变了）：丢掉抓着杆的状态，身体夹回窗口里。"""
        old = self.terrain
        if old is None:
            return
        self.grip_point = None
        self.movement_animation = None
        self.commited_to_drop_connection = None
        self.upcoming_connections.clear()
        if self.jump_module is not None:
            self.jump_module.reset()
        if (old.WL, old.HL) != (new.WL, new.HL):
            moved = False
            for c in self.body_chunks:
                x = max(c.rad, min(new.WL - c.rad, c.pos.x))
                y = max(c.rad, min(new.HL - c.rad, c.pos.y))
                if x != c.pos.x or y != c.pos.y:
                    c.pos = V2(x, y)
                    c.last_pos = c.pos
                    moved = True
            if moved:
                self.graphics_module.reset()

    # 被光标拖

    def begin_drag(self, target: V2) -> None:
        """钉住离光标最近的一节；光标的抓握是 pacifying 的，蜥蜴随即进入「被抓」的挣扎分支。"""
        if self.drag is not None:
            return
        idx = min(range(3), key=lambda i: distance(self.body_chunks[i].pos, target))
        self.drag = _Drag(idx, target, CursorGrasp(self, idx))

    def drag_to(self, target: V2, vel: V2) -> None:
        if self.drag is not None:
            self.drag.target = target
            self.drag.vel = vel

    def end_drag(self, vel: V2) -> None:
        d = self.drag
        if d is None:
            return
        self.drag = None
        d.grasp.release()
        for c in self.body_chunks:
            c.vel = vel

    def _pin(self) -> None:
        d = self.drag
        if d is not None:
            c = self.body_chunks[d.index]
            c.pos = d.target
            c.vel = d.vel

    def enter_animation(self, anim: Animation, force_animation_change: bool) -> None:
        if (not force_animation_change and int(anim) < int(self.animation)) or self.animation == anim:
            return
        rng = self.rng
        p = self.lizard_params
        self.time_in_animation = 0
        self.animation = anim
        if anim == Animation.Standard:
            self.time_to_remain_in_animation = -1
        elif anim == Animation.HearSound:
            self.time_to_remain_in_animation = 40
            self.bubble = 40
            self.bubble_intensity = 0.1
            self.say("Curious")
        elif anim == Animation.PreySpotted:
            self.bubble = 30
            self.bubble_intensity = 1.0
            self.time_to_remain_in_animation = 30
            self.say("SpottedPreyFirstTime")
        elif anim == Animation.PreyReSpotted:
            self.bubble = 10
            self.bubble_intensity = 0.4
            self.time_to_remain_in_animation = 10
            self.say("ReSpottedPrey")
        elif anim == Animation.ThreatSpotted:
            self.bubble_intensity = 1.0
            self.time_to_remain_in_animation = rng.randrange(10, 50)
            self.say("Fear")
        elif anim == Animation.ThreatReSpotted:
            self.bubble_intensity = 1.0
            self.time_to_remain_in_animation = 10
        elif anim == Animation.ShootTongue:
            self.time_to_remain_in_animation = p.tongue_warm_up
            self.play("Lizard_Prepare_To_Shoot_Tongue")
        elif anim == Animation.PrepareToJump:
            self.bubble = 3
            self.bubble_intensity = 0.1
        elif anim == Animation.Jumping:
            self.time_to_remain_in_animation = -1
            self.jump_module.jump()
        elif anim == Animation.PrepareToLounge:
            self.bubble = 3
            self.bubble_intensity = 0.1
            self.time_to_remain_in_animation = p.pre_lounge_crouch + 5
            focus = self._focus_realized()
            if focus is not None:
                self.lounge_dir = dir_vec(self.main_body_chunk.pos, focus.main_body_chunk.pos)
            self.play("Lizard_Prepare_Lunge_Attack_Init")
        elif anim == Animation.Lounge:
            self.lounge_delay = (
                p.lounge_delay * (2 if rng.random() < p.risk_of_double_lounge_delay else 1)
                + p.lounge_maximum_frames
            )
            focus = self._focus_realized()
            if focus is not None:
                from .physics import vslerp

                self.lounge_dir = vslerp(
                    self.lounge_dir,
                    dir_vec(self.main_body_chunk.pos, focus.main_body_chunk.pos),
                    p.find_lounge_direction,
                )
            c = self.body_chunks
            if dot(dir_vec(c[1].pos, c[0].pos), self.lounge_dir) < 0.0:
                if p.can_exit_lounge or p.can_exit_lounge_warm_up:
                    self.enter_animation(Animation.Standard, True)
                else:
                    self.lounge_dir = dir_vec(c[1].pos, c[0].pos)
            if self.lounge_dir.y > 0.0:
                self.lounge_dir = V2(self.lounge_dir.x, self.lounge_dir.y + p.lounge_jumpyness)
            self.lounge_dir = V2(self.lounge_dir.x, self.lounge_dir.y * 0.5)
            self.time_to_remain_in_animation = p.lounge_maximum_frames + 5
            self.play("Lizard_Lunge_Attack_Init")
        elif anim == Animation.ShakePrey:
            self.bubble_intensity = 0.0
            self.time_to_remain_in_animation = rng.randrange(p.shake_prey, p.shake_prey * 2)
            self.time_to_remain_in_animation = int(
                self.time_to_remain_in_animation
                * self.ai.dynamic_relationship(self.grasps[0].grabbed).intensity
            )
        elif anim == Animation.FightingStance:
            self.bubble = 10
            self.bubble_intensity = 1.0
            self.time_to_remain_in_animation = rng.randrange(20, 50)

    def say(self, emotion: str, intensity: float | None = None) -> None:
        """voice.MakeSound(LizardVoice.Emotion.X, ...)；Emotion 缺这个名字时把名字原样交给 voice。"""
        self.voice.make_sound(getattr(Emotion, emotion, emotion), intensity)

    def play(self, sound_id: str, pos: V2 | None = None, vol: float = 1.0, pitch: float = 1.0) -> None:
        """room.PlaySound(SoundID.X, mainBodyChunk)。"""
        sfx.play(sound_id, self.body_chunks[0].pos if pos is None else pos, vol, pitch)

    def emit_noise(self, pos: V2, strength: float, interesting: float = 1.0) -> None:
        """Room.InGameNoise：本 tick 产生，下一 tick 起被各蜥蜴的 NoiseTracker 听到（见 ctx.noise_out）。"""
        out = getattr(self.ctx, "noise_out", None)
        if out is not None:
            out.append(Noise(pos, strength, self, interesting))

    def hear_noise(self, noise: Noise) -> None:
        """Creature.HeardNoise。"""
        if noise.source is not None and noise.source is not self and self.consious:
            self.ai.heard_noise(noise)

    def hurt(self, amount: float) -> None:
        """LizardState.health -= amount，不死：health 不低于 HEALTH_FLOOR。"""
        self.health = max(HEALTH_FLOOR, self.health - amount)

    def _focus_realized(self):
        """AI.focusCreature.representedCreature.realizedCreature，缺任何一环返回 None。"""
        f = self.ai.focus_creature
        if f is None or f.represented_creature is None:
            return None
        return f.represented_creature.realized_creature

    def update(self, eu: bool) -> None:
        p = self.lizard_params
        rng = self.rng
        self.last_jaw_open = self.jaw_open
        self.voice.update()
        if self.jaw_open > 0.9:
            if self.bite_delay > 0:
                self.bite_delay -= 1
        elif self.bite_delay < p.bite_delay:
            self.bite_delay += 1
        self.jaw_forced_shut = max(0.0, self.jaw_forced_shut - 1.0 / 60.0)
        h = self.health
        self.health = min(1.0, h + REGEN_PER_TICK)
        self.throat_health = min(1.0, self.throat_health + REGEN_PER_TICK)
        for i in range(4):
            self.limb_health[i] = min(1.0, self.limb_health[i] + REGEN_PER_TICK)
        if not self.dead and rng.random() * 0.7 > h and rng.random() < 0.125:
            hi = 27 - int_clamp(int(20.0 * h), 0, 10)
            inner = rng.randrange(1, hi)
            self.apply_stun(rng.randrange(1, inner) if inner > 1 else 1)
        if not self.dead and rng.random() * 0.2 > h and rng.random() < 0.025:
            self.graphics_module.white_flicker_start(rng.randrange(1, 5))
        if not self.dead and rng.random() * 0.5 > h and rng.random() < 0.05:
            self.jaw_open = rng.random()
        self.body_chunk_connections[2].active = self.body_stiff()
        if self.bubble > 0:
            self.bubble -= 1
        self.lounge_delay -= 1
        if self.tongue is not None:
            self.tongue.update()
        if self.consious:
            self.act()
        else:
            self.apply_gravity = True
        if (
            not self.consious
            and not self.dead
            and self.stun < 35
            and self.grabbed_by
            and self.grabbed_attack_counter < 22
        ):
            self.grabbed_attack_counter += 1
            self.jaw_forced_shut = max(0.0, self.jaw_forced_shut - 1.0 / 24.0)
            self.jaw_open = self.jaw_open + 0.1 + 0.1 * self.health
            rng = self.rng
            for ch in self.body_chunks:
                ch.vel = ch.vel + rnv(rng) * (rng.random() * 6.0 * self.health)
            grabber = self.grabbed_by[0].grabber
            grabber_red = getattr(grabber, "kind_key", None) == "red"
            if (
                self.grabbed_attack_counter == 22
                and self.jaw_ready_for_bite
                and getattr(grabber, "is_creature", False)
                and (
                    (
                        rng.random()
                        < p.get_free_bite_chance
                        * lerp_map(grabber.total_mass, self.total_mass, self.total_mass * 3.0, 1.0, 0.1)
                        * self.health
                        and not grabber_red
                    )
                    or (p.key == "red" and rng.random() < self.health)
                )
            ):
                self.damage_attack_closest_chunk(grabber)
        elif not self.grabbed_by:
            self.grabbed_attack_counter = 0
        if self.tongue is not None and (
            self.animation == Animation.ShootTongue or (p.key != "blue" and self.tongue.out)
        ):
            self.jaw_open += 0.1
        mov = self.movement_animation
        typ = (
            BodyChunkConnection.PULL
            if mov is not None and mov.connection.type == STANDARD
            else BodyChunkConnection.NORMAL
        )
        self.body_chunk_connections[0].type = typ
        self.body_chunk_connections[1].type = typ
        jm = self.jump_module
        if (
            self.animation == Animation.Lounge
            or self.post_lounge_stun > 0
            or (jm is not None and jm.no_run_behavior)
        ):
            self.air_friction = 0.999
            self.gravity = 0.9
            self.bounce = 0.1
            self.surface_friction = 0.5 if self.animation == Animation.Lounge else 0.4
            self.post_lounge_stun -= 1
        elif self.apply_gravity:
            self.air_friction = 0.999
            self.gravity = 0.9
            self.bounce = 0.1
            self.surface_friction = 0.3
        else:
            self.air_friction = 0.8
            self.gravity = 0.0
            self.bounce = 0.1
            self.surface_friction = 0.5
        if self.grasps[0] is not None:
            self.carry_object(eu)
        if p.pull_down_fac != 1.0 and self.terrain is not None:
            tx, ty = self.pos_tile
            T = self.terrain
            if not T.narrow_space((tx, ty)) and (T.solid((tx, ty - 1)) or T.solid((tx, ty - 2))):
                for i in (1, 2):
                    self.body_chunks[i].vel = V2(
                        self.body_chunks[i].vel.x, self.body_chunks[i].vel.y - (p.pull_down_fac - 1.0)
                    )
        if jm is not None:
            jm.update()
        super().update(eu)

    def carry_object(self, eu: bool) -> None:
        """叼着东西时每 tick 的处理：把被叼的那节搬到嘴前，拽不住或离太远就松口。"""
        g = self.grasps[0]
        if self.rng.random() < 0.025 and (
            not g.grabbed.is_creature or self.ai.dynamic_relationship(g.grabbed).type != "Eats"
        ):
            self.lose_all_grasps()
            return
        c = self.body_chunks
        main = c[0]
        vector = main.pos + dir_vec(c[1].pos, main.pos) * (25.0 * self.lizard_params.head_size)
        grabbed = g.grabbed
        gc = grabbed.body_chunks[g.chunk_grabbed]
        vector2 = gc.vel - main.vel
        gc.vel = main.vel
        if vector2.magnitude * gc.mass > 30.0 or not dist_less(vector, gc.pos, 70.0 + gc.rad):
            self.lose_all_grasps()
        else:
            gc.move_from_outside_my_update(eu, vector)
        g = self.grasps[0]
        if g is not None:
            for i in range(2):
                g.grabbed.push_out_of(c[i].pos, c[i].rad, g.chunk_grabbed)

    # 咬

    def attempt_bite(self, creature) -> None:
        """Lizard.AttemptBite：嘴没张开就先张；张开了按 biteChance 找嘴前够得着的那节去咬。"""
        if self.grasps[0] is not None or not self.consious:
            return
        p = self.lizard_params
        rng = self.rng
        if not self.jaw_ready_for_bite:
            self.jaw_open += 0.05
            return
        c = self.body_chunks
        flag = False
        if rng.random() < p.bite_chance and creature is not None:
            front = c[0].pos + dir_vec(c[1].pos, c[0].pos) * p.bite_in_front
            for chunk in creature.body_chunks:
                if dist_less(front, chunk.pos, max(8.0, chunk.rad) + p.bite_rad_bonus):
                    if self.tongue is not None and self.tongue.out:
                        if self.tongue.state != "StuckInTerrain":
                            self.tongue.retract()
                        return
                    flag = True
                    self.bite(chunk)
                    break
        elif creature is None:
            self.bite(None)
        if self.legs_gripping <= 0:
            return
        if flag:
            for j in range(3):
                c[j].vel = c[j].vel + deg_to_vec(rng.random() * 360.0) * 7.0
        elif creature is not None and (self.tongue is None or not self.tongue.out):
            v = dir_vec(c[0].pos, creature.main_body_chunk.pos)
            c[0].vel = c[0].vel + v * (3.0 * p.bite_homing_speed)
            c[1].vel = c[1].vel - v * p.bite_homing_speed
            c[2].vel = c[2].vel - v * p.bite_homing_speed

    def bite(self, chunk) -> None:
        """Lizard.Bite：能吃的、或质量小于自己 1.2 倍且掷中一半的，直接咬住（pacifying 抓握）；
        被咬的生物按 biteDamageChance 受伤；咬不住就把别的蜥蜴对它的抓握打掉。"""
        if (self.grasps[0] is not None and not self.grabbed_by) or (
            chunk is not None and chunk.owner.is_creature and chunk.owner.new_to_room_invincibility > 0
        ):
            return
        p = self.lizard_params
        rng = self.rng
        main = self.body_chunks[0]
        self.jaw_open = 0.0
        self.last_jaw_open = 0.0
        if chunk is None:
            self.play("Lizard_Jaws_Shut_Miss_Creature")
            return
        owner = chunk.owner
        chunk.vel = chunk.vel + main.vel * (lerp(main.mass, 1.1, 0.5) / max(1.0, chunk.mass))
        grabbed = False
        eats = owner.is_creature and self.ai.dynamic_relationship(owner).type == "Eats"
        if (
            eats
            or (rng.random() < 0.5 and owner.total_mass < self.total_mass * 1.2)
            or (not owner.is_creature and owner.total_mass < self.total_mass * 1.2)
        ):
            idx = getattr(owner, "grab_chunk_index", chunk.index)
            grabbed = self.grab(owner, 0, idx, p.bite_dominance * rng.random(), True, True)
        if grabbed:
            if owner.is_creature:
                if p.key == "red" and hasattr(owner, "lose_all_grasps"):
                    owner.lose_all_grasps()
                self.ai.bit_creature(chunk)
                if rng.random() < p.bite_damage_chance:
                    owner.violence(
                        main,
                        dir_vec(main.pos, chunk.pos) * 0.1,
                        chunk,
                        "Bite",
                        p.bite_damage * lerp(0.8, 1.2, rng.random()),
                        0.0,
                    )
            self.play("Lizard_Jaws_Grab_NPC")
            return
        if rng.random() < 0.5 and owner.is_creature and self.ai.dynamic_relationship(owner).type == "Attacks":
            self.damage_attack(chunk, 0.5)
            return
        self.play("Lizard_Jaws_Shut_Miss_Creature")
        for g in list(owner.grabbed_by):
            if (
                isinstance(g.grabber, Lizard) and g.dominance < 1.0
            ):  # 原版无条件打掉；吃着的（dominance 2）例外
                g.release()

    def damage_attack_closest_chunk(self, target) -> None:
        main = self.body_chunks[0]
        best, d = None, 1e30
        for ch in target.body_chunks:
            dd = distance(main.pos, ch.pos)
            if dd < d:
                best, d = ch, dd
        if best is not None:
            self.damage_attack(best, 1.0)

    def damage_attack(self, chunk, dmg_fac: float) -> None:
        """Lizard.DamageAttack：直接撕咬一节，伤害 biteDamage*随机*dmgFac，自己也晕一下并松口。"""
        if chunk is None or not chunk.owner.is_creature:
            return
        p = self.lizard_params
        rng = self.rng
        main = self.body_chunks[0]
        c = self.body_chunks
        if self.ai.dynamic_relationship(chunk.owner).type == "AgressiveRival":
            dmg_fac = 0.0
        chunk.owner.violence(
            main,
            dir_vec(main.pos, chunk.pos) * 11.0,
            chunk,
            "Bite",
            p.bite_damage * rng.random() * dmg_fac,
            30.0,
        )
        self.play("Lizard_Jaws_Grab_NPC")
        self.jaw_open = 0.0
        self.last_jaw_open = 0.0
        v = dir_vec(main.pos, chunk.pos)
        c[0].vel = c[0].vel + v * 8.0
        c[1].vel = c[1].vel - v * 6.0
        c[2].vel = c[2].vel - v * 6.0
        self.bite_delay = p.bite_delay
        self.stun = max(self.stun, int(16.0 * dmg_fac))
        self.lose_all_grasps()

    # 被咬

    def hit_in_mouth(self, direction: V2) -> bool:
        """Lizard.HitInMouth：从上往下的攻击不算；方向落在张开的嘴的锥角里算。"""
        if direction.y > 0.0:
            return False
        d = vslerp(direction, V2(0.0, 1.0), 0.1)
        return abs(angle_between(d, -self.body_chunks[0].rotation)) < lerp(-15.0, 11.0, self.jaw_open)

    def hit_head_shield(self, direction: V2) -> bool:
        """Lizard.HitHeadShield：从头正面来的攻击被头盾挡住（嘴张得越大角度越宽）。"""
        a = angle_between(direction, -self.body_chunks[0].rotation)
        if self.hit_in_mouth(direction):
            return False
        if a < self.lizard_params.head_shield_angle + 20.0 * self.jaw_open:
            self.play("Lizard_Head_Shield_Deflect")
            return True
        return False

    def violence(
        self, source, direction_and_momentum, hit_chunk, kind, damage: float, stun_bonus: float
    ) -> None:
        """Lizard.Violence：伤害按 baseDamageResistance，晕按 baseStunResistance；头盾挡下咬 / 刺的大部分，
        张嘴时打中嘴里加重。health 不低于 HEALTH_FLOOR（不会死）。"""
        p = self.lizard_params
        num = damage / p.base_damage_resistance
        num2 = (damage * 30.0 + stun_bonus) / p.base_stun_resistance
        self.say("PainImpact", max(num * 2.0, num2 / 40.0))
        d = direction_and_momentum
        if hit_chunk is not None and hit_chunk.index == 0 and d is not None:
            if self.hit_head_shield(d):
                if source is not None:
                    n = int(min(max(num2 / 2.0, int(num * 30.0)), 25.0))
                    g = self.graphics_module
                    rng = self.rng
                    sparks = getattr(self.ctx, "sparks", None)
                    if sparks is not None:
                        for _ in range(n):
                            sparks.append(
                                Spark(
                                    source.pos + deg_to_vec(rng.random() * 360.0) * (5.0 * rng.random()),
                                    source.vel * -0.1
                                    + deg_to_vec(rng.random() * 360.0)
                                    * (lerp(0.2, 0.4, rng.random()) * source.vel.magnitude),
                                    (1.0, 1.0, 1.0),
                                    g,
                                    10,
                                    170,
                                    rng,
                                )
                            )
                        self.ctx.orbs.append(FlashOrb(source.pos, g))
                    g.white_flicker_start(n)
                    g.head.vel = g.head.vel + d * 2.0
                num *= 0.1
                num2 = (damage * 0.5 * 30.0 + stun_bonus * (2.0 / 3.0)) / p.base_stun_resistance
                if p.key == "cyan":
                    num2 *= 1.2
                d = d / 3.0
            elif self.hit_in_mouth(d):
                num *= 1.5
                num2 = min(num2 * 2.0, 120.0)
                self.throat_health -= num
        if d is not None and hit_chunk is not None:
            hit_chunk.vel = hit_chunk.vel + d / hit_chunk.mass
        num2 *= 1.0 + inverse_lerp(0.75, 0.0, self.health) * self.rng.random()
        self.apply_stun(int(num2))
        self.hurt(num)
        # 咬在躯干 / 后肢上会伤到肢体（原版只有矛插中才改 limbHealth，这里借同一套选肢体的办法，1/7 概率）
        if kind == "Bite" and hit_chunk is not None and hit_chunk.index != 0 and num > 0.05:
            rng = self.rng
            if rng.random() < 1.0 / 7.0 and (hit_chunk.index != 1 or rng.random() < 0.5):
                side = angle_between(d if d is not None else V2(0.0, 1.0), -hit_chunk.rotation)
                lr = 1 if side > 90.0 else 0
                i = lr if hit_chunk.index == 1 else 2 + lr
                self.limb_health[i] = 0.0

    # 作为被抓的东西

    new_to_room_invincibility = 0

    def can_be_grabbed(self, grabber) -> bool:
        return not self.dead

    def grabbed(self, grasp) -> None:
        if grasp not in self.grabbed_by:
            self.grabbed_by.append(grasp)

    def grab(
        self,
        obj,
        grasp_used: int,
        chunk_grabbed: int,
        dominance: float,
        override_equally_dominant: bool,
        pacifying: bool,
    ) -> bool:
        """Creature.Grab：已被别人抓着时要压得过对方的 dominance 才抢得走（蜥蜴的抓握共享性互相排斥）。"""
        if not obj.can_be_grabbed(self):
            return False
        g = self.grasps[grasp_used]
        if g is not None and g.grabbed is obj:
            self.release_grasp(grasp_used)
            self.grasps[grasp_used] = Grasp(self, obj, grasp_used, chunk_grabbed, dominance, True)
            obj.grabbed(self.grasps[grasp_used])
            return True
        for item in obj.grabbed_by:
            if item.grabber is self or (
                (override_equally_dominant and item.dominance == dominance) or item.dominance > dominance
            ):
                return False
        for item in list(obj.grabbed_by):
            item.release()
        if self.grasps[grasp_used] is not None:
            self.release_grasp(grasp_used)
        self.grasps[grasp_used] = Grasp(self, obj, grasp_used, chunk_grabbed, dominance, pacifying)
        obj.grabbed(self.grasps[grasp_used])
        return True

    def finish_eating(self) -> None:
        """吃完了：松口，猎物标记为被吃掉，由物品层让它消失。"""
        g = self.grasps[0]
        if g is None:
            return
        prey = g.grabbed
        self.lose_all_grasps()
        prey.eaten = True
        self.ai.reset_eating()

    def collide(self, other, my_chunk: int, other_chunk: int) -> None:
        """Lizard.Collide：撞到生物就看见它；对手蜥蜴撞上来涨怒气；撞到想吃的，扑咬中用头直接咬，否则试着咬。"""
        ai = self.ai
        if other.is_creature:
            ai.tracker.see_creature(other)
            rel = ai.dynamic_relationship(other)
            if rel.type == "AgressiveRival" and ai.submitted_to is not other and not ai.has_retreated(other):
                rep = ai.tracker.representation_for_creature(other)
                if rep is not None:
                    ai.agression_tracker.increment_anger(rep, 0.05 * rel.intensity)
        if (
            self.consious
            and self.grasps[0] is None
            and other.is_creature
            and ai.dynamic_relationship(other).go_for_kill
        ):
            if self.animation == Animation.Lounge and my_chunk == 0:
                self.bite(other.body_chunks[other_chunk])
            else:
                self.attempt_bite(other)

    def body_stiff(self) -> bool:
        if not self.consious:
            return True
        if self.movement_animation is not None:
            return False
        return True

    def movement_animation_ended(self, connection, success: bool) -> None:
        self.movement_animation = None

    def jaws_snap_shut(self, pos: V2) -> None:
        c = self.body_chunks
        self.play("Lizard_Jaws_Shut_Miss_Creature")
        self.jaw_open = 0.0
        self.last_jaw_open = 0.0
        c[0].vel = c[0].vel + dir_vec(c[0].pos, pos) * 8.0
        c[1].vel = c[1].vel - dir_vec(c[0].pos, pos) * 6.0
        c[2].vel = c[2].vel - dir_vec(c[0].pos, pos) * 6.0
        self.bite_delay = self.lizard_params.bite_delay
        self.jaw_forced_shut = 1.0

    def terrain_impact(self, chunk: int, direction, speed: float, first_contact: bool) -> None:
        if first_contact and speed > 10.0:
            self.graphics_module.terrain_impact(chunk, direction, speed)
        if speed > 1.5 and first_contact:
            k = inverse_lerp(6.0, 14.0, speed)
            pitch = lerp(1.0 / self.lizard_params.body_size_fac, 1.0, 0.8)
            if k < 1.0:
                self.play("Lizard_Light_Terrain_Impact", None, 1.0 - k, pitch)
            if k > 0.0:
                self.play("Lizard_Heavy_Terrain_Impact", None, k, pitch)
        c = self.body_chunks[chunk]
        m = speed * lerp(c.mass, 1.0, 0.5)  # BodyChunk.loudness = 1
        if first_contact and speed > 4.0 and m > 0.5:
            self.emit_noise(
                c.pos + V2(direction[0], direction[1]) * (c.rad * 0.9),
                lerp(350.0, lerp(100.0, 1500.0, inverse_lerp(0.5, 20.0, m)), 0.5),
                1.0,
            )

    def apply_stun(self, st: int) -> None:
        """Lizard.Stun。"""
        if self.health < 0.5:
            st = int(st * (1.0 + inverse_lerp(0.75, 0.0, self.health) * 1.5))
        if st > 5 and not self.stunned:
            self.graphics_module.stun(st)
        super().apply_stun(st)
        if self.stunned:
            self.grip_point = None
            self.movement_animation = None
            self.lose_all_grasps()

    # Act

    def act(self) -> None:
        p = self.lizard_params
        T = self.terrain
        rng = self.rng
        ai = self.ai
        c = self.body_chunks
        self.ai.update()
        flag = False
        flag2 = False
        for ch in c:
            if T.accessible(tile_xy(ch.pos), p):
                flag = flag or ch.index == 0
                flag2 = flag2 or ch.index > 0
        if (flag or flag2 or self.movement_animation is not None) and self.in_allowed_terrain_counter < 100:
            self.in_allowed_terrain_counter += 1
        else:
            flag3 = False
            n2 = 0
            while not flag3 and n2 < 3:
                n3 = 0
                tx, ty = tile_xy(c[n2].pos)
                while not flag3 and n3 < 4:
                    d = FOUR_DIRECTIONS[n3]
                    if T.accessible((tx + d[0], ty + d[1]), p):
                        flag3 = True
                    n3 += 1
                n2 += 1
            if flag3:
                self.in_allowed_terrain_counter = max(0, self.in_allowed_terrain_counter - 10)
            else:
                self.in_allowed_terrain_counter = 0
        self.apply_gravity = (
            self.in_allowed_terrain_counter < p.regain_footing_counter
            or self.no_grip_counter > 10
            or self.commited_to_drop_connection is not None
        )
        ai.stuck_tracker.satisfied_with_this_position = False
        num4 = self.act_animation()

        wc = tile_xy(c[0].pos)
        pf = self.pather
        if self.movement_animation is None and not pf.coordinate_reachable_and_getbackable(wc):
            for j in range(8):
                d = EIGHT_DIRECTIONS_DIAGONALS_LAST[j]
                cand = (wc[0] + d[0], wc[1] + d[1])
                if pf.coordinate_reachable_and_getbackable(cand):
                    wc = cand
                    break
        self.following_connection = pf.follow_path(wc, self.body_direction, True)
        if self.commited_to_drop_connection is not None:
            self.following_connection = self.commited_to_drop_connection
            self.commited_to_drop_connection = None
        fc = self.following_connection
        conns = self.body_chunk_connections
        if (
            fc is None
            or distance(c[0].pos, self.mid(fc.destination_coord))
            > distance(c[1].pos, self.mid(fc.destination_coord))
        ) and self.time_spent_trying_this_move > 10:
            conns[0].type = BodyChunkConnection.PULL
            conns[1].type = BodyChunkConnection.PULL
        else:
            conns[0].type = BodyChunkConnection.NORMAL
            conns[1].type = BodyChunkConnection.PULL
        sq = lerp_map(self.time_spent_trying_this_move, 10.0, 30.0, 1.0, 0.05)
        for ch in c:
            ch.terrain_squeeze = sq
        if num4 > 0.1 and (
            fc is None or ai.stuck_tracker.move_backlog.is_move_in_log(fc, int(lerp(1.0, 20.0, num4)))
        ):
            self.time_spent_trying_this_move = int_clamp(self.time_spent_trying_this_move + 1, 0, 600)
        else:
            self.time_spent_trying_this_move = 0
        self.desperation_smoother = lerp_and_tick(
            self.desperation_smoother,
            max(
                self.time_spent_trying_this_move + lerp(-300.0, 0.0, num4), ai.stuck_tracker.utility() * 100.0
            ),
            0.05,
            0.5,
        )
        if self.desperation_smoother > lerp(40.0, 10.0, num4):
            self.body_wiggle_counter += 2
        else:
            self.body_wiggle_counter -= 1
        ai.stuck_tracker.move_backlog.report_new_move(fc)
        self.upcoming_connections.clear()
        if fc is not None:
            self.limbs_aim_for = self.mid(fc.destination_coord)
            if fc.type in (
                REACH_UP,
                REACH_OVER_GAP,
                REACH_DOWN,
                LIZARD_TURN,
                SEMI_DIAGONAL_REACH,
                DOUBLE_REACH_UP,
            ):
                self.movement_animation = MovementAnimation(self, fc, 1, 0.99, 0.75)
            mc2 = fc
            self.narrow_upcoming = False
            self.climb_upcoming = False
            solid = T.solid
            for _ in range(5):
                dx, dy = mc2.destination_coord
                if not self.narrow_upcoming and (
                    (solid((dx, dy + 1)) and solid((dx, dy - 1)))
                    or (solid((dx + 1, dy)) and solid((dx - 1, dy)))
                ):
                    self.narrow_upcoming = True
                if not self.climb_upcoming and T.acc((dx, dy)) == CLIMB:
                    self.climb_upcoming = True
                self.upcoming_connections.append(mc2)
                mc2 = pf.follow_path(mc2.destination_coord, None, False)
                for u in self.upcoming_connections:
                    if mc2 is None:
                        break
                    if u.destination_coord == mc2.destination_coord or u.start_coord == mc2.destination_coord:
                        mc2 = None
                if mc2 is None:
                    break
        self.time_in_animation += 1
        if (
            self.time_to_remain_in_animation > -1
            and self.time_in_animation > self.time_to_remain_in_animation
        ):
            self.enter_animation(Animation.Standard, True)
        if (
            self.bubble == 0
            and rng.random() < 0.05
            and rng.random() < ai.excitement
            and rng.random() < ai.excitement
        ):
            self.bubble_intensity = ai.excitement * ai.excitement * rng.random()
            self.bubble = 1
        jm = self.jump_module
        if jm is not None and self.grip_point is None and jm.no_run_behavior:
            return
        if self.grip_point is not None:
            self.grip_point_behavior()
        elif self.movement_animation is not None:
            self.movement_animation.update(num4 * p.base_speed * 0.5)
        elif self.following_connection is not None:
            self.follow_connection(num4)
        fc = self.following_connection
        if fc is None and self.movement_animation is None:
            if not self.apply_gravity and not self._accessible_at(c[0].pos):
                tx, ty = tile_xy(c[0].pos)
                d = FOUR_DIRECTIONS[rng.randrange(4)]
                t2 = (tx + d[0], ty + d[1])
                if T.accessible(t2, p):
                    self.following_connection = MovementConnection(STANDARD, (tx, ty), t2, 1)
            elif flag and not flag2 and self.time_spent_trying_this_move > 20:
                tx, ty = tile_xy(c[1].pos)
                for d in FOUR_DIRECTIONS:
                    t2 = (tx + d[0], ty + d[1])
                    if T.accessible(t2, p):
                        c[1].vel = c[1].vel + dir_vec(c[1].pos, self.mid(t2))
                        break
        if self.body_desperation > 0.0:
            vector = deg_to_vec(rng.random() * 360.0) * (
                self.body_desperation * p.max_muscle_power * 2.0 * rng.random()
            )
            c[0].vel = c[0].vel + vector * 0.5
            c[1].vel = c[1].vel - vector
            c[2].vel = c[2].vel + vector * 0.5
        conns[2].elasticity = 0.7 + 0.3 / self.body_force
        if self.animation == Animation.ShakePrey:
            self.body_wiggle_counter = int_clamp(50 - self.time_in_animation, 0, 100)
            vector2 = deg_to_vec(rng.random() * 360.0) * (12.0 * rng.random())
            g = self.grasps[0]
            if g is None:
                vector2 = vector2 * 0.5
            else:
                gc = g.grabbed.body_chunks[g.chunk_grabbed]
                value = abs(gc.mass - c[0].mass * 0.5)
                value = inverse_lerp(c[0].mass * 0.5, 0.0, value)
                value = value**1.5
                vector2 = vector2 * value
                self.body_wiggle_counter = int_clamp(
                    int(self.body_wiggle_counter * lerp(value, 1.0, 0.5)), 0, 100
                )
                if value == 0.0 and rng.random() < 0.025:
                    self.body_wiggle_counter = 0
                    self.enter_animation(Animation.Standard, True)
            c[0].vel = c[0].vel - vector2 * 0.5
            c[1].vel = c[1].vel + vector2
            c[2].vel = c[2].vel - vector2 * 0.5
        wf = self.body_wiggle_fac
        if wf > 0.0:
            self.body_wiggle += lerp(0.05, 0.15, wf) * lerp(0.5, 0.8, p.wiggle_speed)
            num10 = math.sin(self.body_wiggle * _TAU)
            from .physics import vslerp

            vector3 = perpendicular_vector(
                vslerp(dir_vec(c[1].pos, c[0].pos), dir_vec(c[2].pos, c[1].pos), 0.5)
            )
            num11 = (wf + 2.0) / ((1.0 - p.wiggle_speed) ** 2 + 2.0)
            vector4 = vector3 * (num10 * num11)
            c[0].vel = c[0].vel + vector4
            c[1].vel = c[1].vel - vector4 * 2.0
            c[2].vel = c[2].vel + vector4
        if self.following_connection is not None:
            self.last_following_connection = self.following_connection
        self.straighten_out_needed = lerp_and_tick(self.straighten_out_needed, 0.0, 0.1, 0.05)

    def follow_connection(self, run_speed: float) -> None:
        p = self.lizard_params
        T = self.terrain
        c = self.body_chunks
        fc = self.following_connection
        conns = self.body_chunk_connections
        frame_speed = self.get_frame_speed(run_speed)
        s, d = fc.start_coord, fc.destination_coord
        up = self.upcoming_connections
        main = c[0]
        if (
            self.time_spent_trying_this_move < 20
            and self.narrow_upcoming
            and frame_speed > 0.2
            and len(up) > 1
            and T.narrow_space(up[1].destination_coord)
        ):
            iv = int_clamp_at_one(d[0] - s[0], d[1] - s[1])
            iv2 = int_clamp_at_one(
                up[1].destination_coord[0] - up[1].start_coord[0],
                up[1].destination_coord[1] - up[1].start_coord[1],
            )
            if iv[0] != iv2[0] and iv[1] != iv2[1]:
                c[0].vel = c[0].vel * 0.75 + V2(iv2[0], iv2[1]) * 2.0
                c[1].vel = c[1].vel * 0.75
                c[2].vel = c[2].vel * 0.5
        if fc.type == STANDARD or fc.type == OPEN_DIAGONAL:
            vx = vy = 0.0
            if T.acc(d) == CLIMB:
                if up:
                    ref = up[min(2, len(up) - 1)].destination_coord
                    i3x, i3y = int_clamp_at_one(ref[0] - s[0], ref[1] - s[1])
                else:
                    i3x, i3y = int_clamp_at_one(d[0] - s[0], d[1] - s[1])
                if d[1] == s[1]:
                    vy = i3y * 8.0
                elif d[0] == s[0]:
                    if T.acc(s) != CLIMB:
                        i3x = -1 if c[2].pos.x < self.mid(tile_xy(main.pos)).x else 1
                    vx = i3x * 8.0
                if self.is_tile_solid(0, i3x, 0):
                    i3x *= -1
                    vx = 0.0
                if self.is_tile_solid(0, 0, i3y):
                    i3y *= -1
                    vy = 0.0
            elif (
                self.no_grip_counter == 0
                and (d[1] == s[1] or T.acc(d) == CURVED_FLOOR)
                and not self.is_tile_solid(0, 0, 1)
                and not self.is_tile_solid(
                    0, (-1 if d[0] < self.pos_tile[0] else 0) + (1 if d[0] > self.pos_tile[0] else 0), 1
                )
            ):
                vy = p.floor_leverage
            mm = self.mid(tile_xy(main.pos))
            if s[0] != d[0] and s[1] == d[1]:
                if (self.is_tile_solid(0, 0, -1) and main.pos.y < mm.y) or (
                    self.is_tile_solid(0, 0, 1) and main.pos.y > mm.y
                ):
                    main.vel = V2(main.vel.x, main.vel.y - (main.pos.y - mm.y) * 0.5)
            elif (
                s[1] != d[1]
                and s[0] == d[0]
                and (
                    (self.is_tile_solid(0, -1, 0) and main.pos.x < mm.x)
                    or (self.is_tile_solid(0, 1, 0) and main.pos.x > mm.x)
                )
            ):
                main.vel = V2(main.vel.x - (main.pos.x - mm.x) * 0.5, main.vel.y)
            ivx, ivy = d[0] - s[0], d[1] - s[1]
            if ivy != 0:
                for i in range(3):
                    ch = c[i]
                    cpx, cpy = ch.contact_point
                    if cpy != 0 and not self.is_tile_solid(i, 0, cpy):
                        ch.vel = V2(ch.vel.x - (ch.pos.x - self.mid(tile_xy(ch.pos)).x) * 0.25, ch.vel.y)
                        vx *= 0.0
            elif ivx != 0:
                for j in range(3):
                    ch = c[j]
                    cpx, cpy = ch.contact_point
                    if cpx != 0 and not self.is_tile_solid(j, cpx, 0):
                        ch.vel = V2(ch.vel.x, ch.vel.y - (ch.pos.y - self.mid(tile_xy(ch.pos)).y) * 0.25)
                        vy *= 0.0
            vector2 = self.mid(d)
            if up and T.acc_index(up[-1].destination_coord) < _I_CLIMB:
                mt = tile_xy(main.pos)
                for k in range(len(up) - 1, -1, -1):
                    ud = up[k].destination_coord
                    if (
                        math.hypot(mt[0] - ud[0], mt[1] - ud[1]) < 2.0
                        and visual_contact(T, main.pos, self.mid(ud))
                    ) or self._ray_trace_in_accessible_tiles(mt, ud):
                        vector2 = self.mid(ud)
                        break
            vector2 = vector2 + V2(vx, vy)
            pnt = vector2 + dir_vec(vector2, c[0].pos) * conns[0].distance
            body_force = self.body_force
            c[0].vel = c[0].vel + dir_vec(c[0].pos, vector2) * (frame_speed * body_force)
            c[1].vel = c[1].vel + dir_vec(c[1].pos, pnt) * (
                frame_speed
                * body_force
                * lerp_map(dot(dir_vec(c[1].pos, vector2), dir_vec(c[1].pos, pnt)), -1.0, 1.0, 0.5, 1.0)
            )
            if self.animation == Animation.Standard and self.ai.run_speed > 0.1:
                num2 = inverse_lerp(0.0, -1.0, dot(dir_vec(c[0].pos, vector2), dir_vec(c[1].pos, c[0].pos)))
                if num2 > 0.5:
                    self.straighten_out_needed = lerp_and_tick(self.straighten_out_needed, 1.0, 0.1, 0.1)
                num2 = lerp(num2, 1.0, inverse_lerp(20.0, 40.0, self.time_spent_trying_this_move))
                num2 *= max(
                    1.0 if self.narrow_upcoming else 0.2,
                    0.5 if self.climb_upcoming else 0.2,
                    inverse_lerp(5.0, 20.0, self.time_spent_trying_this_move),
                    self.straighten_out_needed,
                )
                push = (num2 * 2.0 * body_force + self.body_desperation * 2.0) * frame_speed
                c[0].vel = c[0].vel + dir_vec(c[1].pos, vector2) * push
                v3 = dir_vec(c[1].pos, vector2) * (
                    (num2 * 2.0 * body_force + self.body_desperation * 2.0)
                    * 0.5
                    * lerp_map(self.time_spent_trying_this_move, 20.0, 60.0, 1.0, 0.5)
                    * frame_speed
                )
                c[1].vel = c[1].vel - v3
                c[2].vel = c[2].vel - v3
        else:
            if fc.type != DROP_TO_FLOOR and fc.type != DROP_TO_CLIMB:
                return
            flag = True
            if abs(self.pos_tile[0] - s[0]) > 4 and abs(self.pos_tile[0] - d[0]) > 4:
                flag = False
            for k in range(3):
                if c[k].contact_point[1] < 0:
                    flag = False
            if flag:
                self.commited_to_drop_connection = fc
            c[0].vel = V2(c[0].vel.x, c[0].vel.y - 0.01)
            c[2].vel = V2(c[2].vel.x, c[2].vel.y + 0.01)
            md = self.mid(d)
            if abs(main.pos.x - md.x) < 5.0:
                if abs(main.vel.x) < 5.0:
                    main.vel = V2(main.vel.x * 0.8, main.vel.y)
            elif main.pos.x < md.x:
                main.vel = V2(main.vel.x + 0.5, main.vel.y)
            else:
                main.vel = V2(main.vel.x - 0.5, main.vel.y)
            flag2 = False
            flag3 = False
            flag4 = False
            body_force = self.body_force
            for ch in c:
                if ch.contact_point[1] < 0:
                    flag2 = True
                ct = tile_xy(ch.pos)
                if ct[1] >= s[1]:
                    flag4 = True
                    if ct[0] == s[0]:
                        ch.vel = ch.vel + dir_vec(ch.pos, md) * (
                            frame_speed * (body_force if ch.index == 0 else 1.0)
                        )
                        flag3 = True
                    else:
                        ch.vel = ch.vel + dir_vec(ch.pos, self.mid(s)) * (
                            frame_speed * (body_force if ch.index == 0 else 1.0)
                        )
                if ct[0] == s[0]:
                    ch.vel = V2(ch.vel.x, ch.vel.y - 1.0)
            if flag3:
                return
            if up:
                lastd = up[-1].destination_coord
                c[0].vel = V2(c[0].vel.x - 0.3 * (d[0] - lastd[0]), c[0].vel.y)
                c[2].vel = V2(c[2].vel.x + 0.3 * (d[0] - lastd[0]), c[2].vel.y)
            if main.pos.y <= main.last_pos.y:
                mt = tile_xy(main.pos)
                if fc.type == DROP_TO_CLIMB:
                    n3 = tile_xy(main.last_pos)[1] + 1
                    n4 = mt[1] - 1
                    for n5 in range(n3, n4 - 1, -1):
                        if n5 <= d[1] and T.acc((mt[0], n5)) == CLIMB:
                            self.play("Lizard_Grab_Pole")
                            self.grip_point = self.mid((mt[0], n5))
                            main.vel = V2(main.vel.x, 0.0)
                            break
                elif d[0] != s[0] and abs(mt[0] - d[0]) < 2:
                    n6 = tile_xy(main.last_pos)[1] + 1
                    n7 = mt[1] - 1
                    for n8 in range(n6, n7 - 1, -1):
                        if n8 <= d[1] and T.acc((d[0], n8)) == FLOOR:
                            self.grip_point = self.mid((d[0], n8))
                            main.vel = V2(main.vel.x, 0.0)
                            break
            if flag2 and not flag4 and self.grip_point is None:
                self.following_connection = None

    def act_animation(self) -> float:
        p = self.lizard_params
        c = self.body_chunks
        rng = self.rng
        ai = self.ai
        anim = self.animation
        num = 0.0
        snap = False
        if anim == Animation.Standard:
            num = ai.run_speed
        elif anim == Animation.HearSound:
            num = 0.0
            self.jaw_open = 0.2
        elif anim == Animation.ThreatSpotted:
            num = 0.5
            self.jaw_open = rng.random()
            focus = ai.focus_creature
            if focus is not None and ai.dynamic_relationship(focus).type == "Afraid" and focus.visual_contact:
                v = dir_vec(c[0].pos, focus.represented_creature.realized_creature.danger_pos)
                c[0].vel = c[0].vel + v * (5.0 * self.legs_gripping)
                c[1].vel = c[1].vel - v * (6.0 * self.legs_gripping)
        elif anim == Animation.ThreatReSpotted:
            num = ai.run_speed * 0.8
            self.jaw_open = lerp(self.jaw_open, rng.random(), rng.random())
        elif anim == Animation.PreySpotted:
            num = 0.0
            self.jaw_open = 1.0
        elif anim == Animation.PreyReSpotted:
            num = ai.run_speed * 0.3
            self.jaw_open = lerp(self.jaw_open, 1.0, rng.random() * rng.random())
        elif anim == Animation.FightingStance:
            self.jaw_open = 1.0
            num = 0.0
            focus = ai.focus_creature
            if focus is not None and not ai.unpleasant_fall_risk(tile_xy(c[0].pos)) and focus.visual_contact:
                danger = focus.represented_creature.realized_creature.danger_pos
                legs = float(self.legs_gripping)
                c[0].vel = c[0].vel + dir_vec(c[0].pos, danger) * (4.0 * legs)
                c[1].vel = c[1].vel - dir_vec(c[0].pos, danger) * (2.2 * legs)
                c[2].vel = c[2].vel - dir_vec(c[0].pos, danger) * (
                    (2.2 if self.is_wall_climber else 2.6) * legs
                )
        elif anim == Animation.PrepareToLounge:
            self.body_wiggle_counter = 0
            focus = ai.focus_creature
            if not p.can_exit_lounge_warm_up or (
                ai.behavior == Behavior.Hunt and focus is not None and focus.visual_contact
            ):
                num = 0.0
                realized = self._focus_realized()
                if realized is not None:
                    if self.legs_gripping > 0:
                        for ch in c:
                            v = dir_vec(ch.pos, realized.main_body_chunk.pos)
                            ch.vel = ch.vel + v * p.pre_lounge_crouch_movement
                    if self.time_in_animation >= p.pre_lounge_crouch:
                        self.enter_animation(Animation.Lounge, False)
                else:
                    self.enter_animation(Animation.Standard, True)
            else:
                self.enter_animation(Animation.Standard, True)
        elif anim == Animation.Lounge:
            focus = ai.focus_creature
            if self.time_in_animation < p.lounge_maximum_frames:
                if p.can_exit_lounge and not (
                    ai.behavior == Behavior.Hunt and focus is not None and focus.visual_contact
                ):
                    snap = True
                else:
                    num = self._lounge_propel()
            else:
                snap = True
        elif anim == Animation.ShakePrey:
            num = 0.75
            if self.grasps[0] is None and rng.random() < 0.025:
                self.enter_animation(Animation.Standard, True)
        elif anim == Animation.ShootTongue:
            self.body_wiggle_counter = 0
            num = 0.2
            focus = ai.focus_creature
            if (
                ai.behavior != Behavior.Hunt
                or focus is None
                or not focus.visual_contact
                or dot(
                    dir_vec(c[1].pos, c[0].pos),
                    dir_vec(c[0].pos, focus.represented_creature.realized_creature.main_body_chunk.pos),
                )
                < 0.3
            ):
                self.enter_animation(Animation.Standard, True)
            if (
                self.time_in_animation == self.time_to_remain_in_animation // 2
                and focus is not None
                and focus.represented_creature.realized_creature is not None
            ):
                self.jaw_open = 1.0
                real = focus.represented_creature.realized_creature
                self.tongue.lash_out(real.body_chunks[rng.randrange(len(real.body_chunks))].pos)
        elif anim == Animation.PrepareToJump:
            jm = self.jump_module
            a = jm.act_on_jump
            T = self.terrain
            if (
                a is not None
                and self.consious
                and dist_less(c[1].pos, T.middle_of(tile_xy(a.best_jump.start_pos)), 50.0)
            ):
                n = a.best_jump.init_vel.normalized
                c[1].vel = c[1].vel * 0.5
                c[1].pos = vslerp(
                    c[1].pos,
                    T.middle_of(tile_xy(a.best_jump.start_pos)) - n * (self.time_in_animation * 0.5),
                    0.2,
                )
                num = 0.0
                c[0].vel = c[0].vel + n * 1.5
                c[2].vel = c[2].vel - n * 2.0
                g = self.graphics_module
                g.head.vel = (
                    g.head.vel + dir_vec(c[0].pos, T.middle_of(a.best_jump.goal_cell.world_coordinate)) * 10.0
                )
                perp = perpendicular_vector(c[0].pos - c[2].pos)
                sgn = -5.0 if self.time_in_animation % 6 < 3 else 5.0
                for i, t in enumerate(g.tail):
                    t.vel = t.vel - (n * i + perp * sgn)
                if self.time_in_animation > self.time_to_remain_in_animation - 5:
                    self.enter_animation(Animation.Jumping, False)
                self.in_allowed_terrain_counter = p.regain_footing_counter + 10
            else:
                self.enter_animation(Animation.Standard, True)
        if snap:
            self.jaws_snap_shut(c[0].pos + dir_vec(c[1].pos, c[0].pos) * 10.0)
            self.enter_animation(Animation.Standard, True)
            self.post_lounge_stun = 40
            self.in_allowed_terrain_counter = 0
        if self.tongue is not None and self.tongue.stuck_to_something:
            if p.key == "white":
                self.body_wiggle_counter += 2
                num = 0.0
                if not self.apply_gravity:
                    k = 1.0 - self.legs_gripping / 4.0
                    for ch in c:
                        ch.vel = ch.vel * k
                    if self.legs_gripping > 0:
                        c[2].vel = c[2].vel + dir_vec(self.tongue.pos, c[2].pos) * 1.2
            else:
                num *= 0.6
        if self.post_lounge_stun > 0:
            num *= 0.1
        if p.key == "red" and self.ai.run_speed > 0.1:
            num = lerp(num, 1.0, lerp(0.2, 0.7, self.ai.hunger))
        return num

    def _lounge_propel(self) -> float:
        p = self.lizard_params
        self.jaw_open += 0.1
        if self.time_in_animation < p.lounge_propulsion_frames and self.legs_gripping > 0:
            for k, ch in enumerate(self.body_chunks):
                ch.vel = ch.vel + self.lounge_dir * p.lounge_speed / (k + 1)
        return 0.0

    def get_frame_speed(self, run_speed: float) -> float:
        p = self.lizard_params
        c = self.body_chunks
        T = self.terrain
        num = self.legs_gripping / 4.0
        num = num * (1.0 - p.no_grip_speed) + p.no_grip_speed
        if self.no_grip_counter < 1:
            num = lerp(num, 1.0 + self.body_desperation, self.body_force - 1.0)
        if num == 0.0 and self.body_wiggle_fac > 0.0:
            for ch in c:
                if ch.contact_point[0] != 0 or ch.contact_point[1] != 0:
                    num = self.body_wiggle_fac * (0.5 + 0.5 * math.sin(self.body_wiggle * _TAU)) * 0.2
                    break
        if num < 0.1 or self.body_force > 1.2:
            self.body_wiggle_counter += 1
        else:
            self.body_wiggle_counter -= 1
        num2 = p.base_speed * num * lerp(run_speed, 1.0, self.body_force - 1.0)
        num2 *= lerp(self.rng.random(), 1.0, (self.health - 0.5) * 2.0)
        sp = hor = upv = dn = 0.0
        for ch in c:
            m = p.terrain_speed(T.acc(tile_xy(ch.pos)))
            sp += m.speed
            hor += m.horizontal
            upv += m.up
            dn += m.down
        sp, hor, upv, dn = sp / 3.0, hor / 3.0, upv / 3.0, dn / 3.0
        num2 *= sp
        fc = self.following_connection
        ddx = fc.destination_coord[0] - fc.start_coord[0]
        ddy = fc.destination_coord[1] - fc.start_coord[1]
        if ddx != 0:
            return num2 * hor
        if ddy > 0:
            return num2 * upv
        return num2 * dn

    def grip_point_behavior(self) -> None:
        c = self.body_chunks
        rng = self.rng
        main = c[0]
        if main.vel.magnitude > 10.0 and self.in_allowed_terrain_counter > 5:
            self.grip_point = None
            self.following_connection = None
        elif not self.apply_gravity:
            mc = self.pather.follow_path(tile_xy(main.pos), 0, True)
            self.movement_animation = None
            fc = self.following_connection
            if (
                fc is not None
                and fc.type == DROP_TO_CLIMB
                and mc is not None
                and mc.destination_coord[1] - mc.start_coord[1] == 0
                and abs(mc.destination_coord[0] - mc.start_coord[0]) == 1
            ):
                mc = mc._replace(type=DROP_TO_CLIMB)
                self.movement_animation = MovementAnimation(self, mc, 1, 0.99, 0.75)
            self.grip_point = None
            self.following_connection = None
        else:
            if c[1].pos.y < c[0].pos.y:
                c[1].vel = V2(c[1].vel.x, c[1].vel.y + rng.random() * 2.0)
            up = self.upcoming_connections
            if up:
                mt = tile_xy(main.pos)
                lastd = up[-1].destination_coord
                sx = int_clamp_at_one(mt[0] - lastd[0], mt[1] - lastd[1])[0]
                c[1].vel = V2(c[1].vel.x + 3.0 * sx, c[1].vel.y)
                c[2].vel = V2(c[2].vel.x + rng.random() * 3.0 * sx, c[2].vel.y)
            else:
                c[1].vel = V2(c[1].vel.x + (-2.0 + rng.random() * 4.0), c[1].vel.y)
        main.vel = V2()
        if self.grip_point is not None:
            main.vel = main.vel - (main.pos - self.grip_point)
