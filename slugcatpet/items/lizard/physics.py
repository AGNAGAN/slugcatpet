"""蜥蜴的物理层：BodyChunk、BodyChunkConnection、PhysicalObject / Creature 的物理与晕眩计时。

坐标 y↑、格 20px，对格子地形（terrain.Terrain）碰撞；没有斜坡、平台、水、地形曲面。
"""

from __future__ import annotations

import math
from enum import IntEnum

from .rw import EIGHT_DIRECTIONS_AND_ZERO, V2, clamp, dir_vec, sign

TILE = 20.0
_OUT_OF_ROOM = 1200.0


class Animation(IntEnum):
    """Lizard.Animation：数值保持原版注册顺序，EnterAnimation 按它比较优先级。"""

    Standard = 0
    HearSound = 1
    PreyReSpotted = 2
    PreySpotted = 3
    FightingStance = 4
    ThreatSpotted = 5
    ThreatReSpotted = 6
    ShootTongue = 7
    Spit = 8
    PrepareToJump = 9
    Jumping = 10
    PrepareToLounge = 11
    Lounge = 12
    ShakePrey = 13


def tile_xy(p: V2) -> tuple[int, int]:
    """Room.GetTilePosition。"""
    return (math.floor(p.x / TILE), math.floor(p.y / TILE))


def fdir(ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    """Custom.DirVec 的标量版：重合返回 (0,1)。"""
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return 0.0, 1.0
    m = math.hypot(dx, dy)
    if m > 1e-5:
        return dx / m, dy / m
    return 0.0, 0.0


def solid_cache(terrain):
    """(W, H, 实心网格, 九邻域实心位掩码)：把 terrain 的格子一次取出，按 terrain 对象缓存。
    下标 = (tx+1) + (ty+1)*W，格范围 -1..cols / -1..rows；范围外都是实心，查询时把坐标夹进范围即可。"""
    c = terrain.__dict__.get("_solid_cache")
    if c is not None and c[0] == terrain.version:
        return c[1]
    W, H = terrain.cols + 2, terrain.rows + 2
    solid = terrain.solid
    g = bytearray(W * H)
    for iy in range(H):
        for ix in range(W):
            if solid((ix - 1, iy - 1)):
                g[ix + iy * W] = 1
    masks = [0] * (W * H)
    for iy in range(H):
        for ix in range(W):
            m = 0
            for k, (dx, dy) in enumerate(EIGHT_DIRECTIONS_AND_ZERO):
                x, y = ix + dx, iy + dy
                if x < 0 or y < 0 or x >= W or y >= H or g[x + y * W]:
                    m |= 1 << k
            masks[ix + iy * W] = m
    r = (W, H, bytes(g), masks)
    terrain._solid_cache = (terrain.version, r)
    return r


def visual_contact(terrain, a: V2, b: V2) -> bool:
    """Room.VisualContact(Vector2, Vector2)：两端与沿线每 20px 采样点都不是实心。"""
    if terrain.solid(tile_xy(a)) or terrain.solid(tile_xy(b)):
        return False
    dist = math.hypot(a.x - b.x, a.y - b.y)
    d = TILE
    while d < dist:
        t = d / dist
        if terrain.solid(tile_xy(V2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t))):
            return False
        d += TILE
    return True


def vslerp(a: V2, b: V2, t: float) -> V2:
    """Vector3.Slerp 作用在 z=0 的二维向量上：方向在平面内旋转，长度线性插值。"""
    t = clamp(t, 0.0, 1.0)
    la, lb = a.magnitude, b.magnitude
    if la < 1e-5 or lb < 1e-5:
        return V2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
    lerped = la + (lb - la) * t
    d = (a.x * b.x + a.y * b.y) / (la * lb)
    if d > 1.0 - 1e-5:
        return V2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)
    if d < -1.0 + 1e-5:
        ang, s = math.pi * t, 1.0
    else:
        ang, s = math.acos(d) * t, sign(a.x * b.y - a.y * b.x)
    c, sn = math.cos(ang), math.sin(s * ang)
    nx, ny = a.x / la, a.y / la
    return V2((c * nx - sn * ny) * lerped, (sn * nx + c * ny) * lerped)


class BodyChunk:
    __slots__ = (
        "owner",
        "index",
        "pos",
        "last_pos",
        "last_last_pos",
        "set_pos",
        "vel",
        "rad",
        "terrain_squeeze",
        "mass",
        "rotation_chunk",
        "collide_with_terrain",
        "contact_point",
        "last_contact_point",
        "restrict_in_room_range",
    )

    def __init__(self, owner, index: int, pos: V2, rad: float, mass: float):
        self.owner = owner
        self.index = index
        self.pos = pos
        self.last_pos = pos
        self.last_last_pos = pos
        self.set_pos: V2 | None = None
        self.vel = V2()
        self.rad = rad
        self.terrain_squeeze = 1.0
        self.mass = mass
        self.rotation_chunk: BodyChunk | None = None
        self.collide_with_terrain = True
        self.contact_point = (0, 0)
        self.last_contact_point = (0, 0)
        self.restrict_in_room_range = _OUT_OF_ROOM

    @property
    def terrain_rad(self) -> float:
        return max(self.rad * self.terrain_squeeze, 1.0)

    @property
    def rotation(self) -> V2:
        if self.rotation_chunk is None:
            return V2(0.0, 1.0)
        return (self.pos - self.rotation_chunk.pos).normalized

    def update(self) -> None:
        o = self.owner
        vx, vy = self.vel.x, self.vel.y
        if vy != vy:
            vy = 0.0
        if vx != vx:
            vx = 0.0
        vy -= o.gravity
        af = o.air_friction
        vx *= af
        vy *= af
        self.last_last_pos = self.last_pos
        self.last_pos = self.pos
        if self.set_pos is not None:
            px, py = self.set_pos.x, self.set_pos.y
            self.set_pos = None
        else:
            px, py = self.pos.x + vx, self.pos.y + vy
        self.last_contact_point = self.contact_point
        if self.collide_with_terrain:
            px, py, vx, vy = self._collide(o, px, py, vx, vy)
        else:
            self.contact_point = (0, 0)
        if not o.grabbed_by:
            tw, th = o.terrain.WL, o.terrain.HL
            r = self.restrict_in_room_range
            if px < -r:
                vx, px = 0.0, -r
            elif px > tw + r:
                vx, px = 0.0, tw + r
            if py < -r:
                vy, py = 0.0, -r
            elif py > th + r:
                vy, py = 0.0, th + r
        self.pos = V2(px, py)
        self.vel = V2(vx, vy)

    def _collide(self, o, px: float, py: float, vx: float, vy: float):
        """CheckVerticalCollision 然后 CheckHorizontalCollision（无地形曲面、斜坡与平台）。"""
        W, H, grid, _ = solid_cache(o.terrain)
        w1, h1 = W - 1, H - 1

        def S(tx, ty):
            i = tx + 1
            j = ty + 1
            i = 0 if i < 0 else (w1 if i > w1 else i)
            j = 0 if j < 0 else (h1 if j > h1 else j)
            return grid[i + j * W]

        fl = math.floor
        tr = max(self.rad * self.terrain_squeeze, 1.0)
        lx, ly = self.last_pos.x, self.last_pos.y
        ltx, lty = fl(lx / TILE), fl(ly / TILE)
        last_solid = S(ltx, lty)
        bounce = o.bounce
        thr = o.impact_treshhold
        slide = clamp(o.surface_friction * 2.0, 0.0, 1.0)
        rest = 1.0 + 9.0 * (1.0 - bounce)
        idx = self.index
        lcx, lcy = self.last_contact_point
        cx = cy = 0
        # 竖直
        if py > ly:
            y_hi = fl((py + tr + 0.01) / TILE)
            y_lo = fl((ly + tr) / TILE)
            x_lo = fl((px - tr + 1.0) / TILE)
            x_hi = fl((px + tr - 1.0) / TILE)
            done = False
            for i in range(y_lo, y_hi + 1):
                for j in range(x_lo, x_hi + 1):
                    if S(j, i) and not S(j, i - 1) and (lty < i or last_solid):
                        py = i * TILE - tr
                        if vy > thr:
                            o.terrain_impact(idx, (0, 1), abs(vy), lcy < 1)
                        cy = 1
                        vy = -abs(vy) * bounce
                        if abs(vy) < rest:
                            vy = 0.0
                        vx *= slide
                        done = True
                        break
                if done:
                    break
        elif py < ly:
            y_lo = fl((py - tr - 0.01) / TILE)
            y_hi = fl((ly - tr) / TILE)
            x_lo = fl((px - tr + 1.0) / TILE)
            x_hi = fl((px + tr - 1.0) / TILE)
            done = False
            for i in range(y_hi, y_lo - 1, -1):
                for k in range(x_lo, x_hi + 1):
                    if S(k, i) and not S(k, i + 1) and (lty > i or last_solid):
                        py = (i + 1) * TILE + tr
                        if vy < -thr:
                            o.terrain_impact(idx, (0, -1), abs(vy), lcy > -1)
                        cy = -1
                        vy = abs(vy) * bounce
                        if vy < o.gravity or vy < rest:
                            vy = 0.0
                        vx *= slide
                        done = True
                        break
                if done:
                    break
        # 水平
        if vx > 0.0:
            x_hi = fl((px + tr + 0.01) / TILE)
            x_lo = fl((lx + tr) / TILE)
            y_hi = fl((py + tr - 1.0) / TILE)
            y_lo = fl((py - tr + 1.0) / TILE)
            done = False
            for i in range(x_lo, x_hi + 1):
                for j in range(y_lo, y_hi + 1):
                    if S(i, j) and not S(i - 1, j) and (ltx < i or last_solid):
                        px = i * TILE - tr
                        if vx > thr:
                            o.terrain_impact(idx, (1, 0), abs(vx), lcx < 1)
                        cx = 1
                        vx = -abs(vx) * bounce
                        if abs(vx) < rest:
                            vx = 0.0
                        vy *= slide
                        done = True
                        break
                if done:
                    break
        elif vx < 0.0:
            x_lo = fl((px - tr - 0.01) / TILE)
            x_hi = fl((lx - tr) / TILE)
            y_hi = fl((py + tr - 1.0) / TILE)
            y_lo = fl((py - tr + 1.0) / TILE)
            done = False
            for i in range(x_hi, x_lo - 1, -1):
                for j in range(y_lo, y_hi + 1):
                    if S(i, j) and not S(i + 1, j) and (ltx > i or last_solid):
                        px = (i + 1) * TILE + tr
                        if vx < -thr:
                            o.terrain_impact(idx, (-1, 0), abs(vx), lcx > -1)
                        cx = -1
                        vx = abs(vx) * bounce
                        if abs(vx) < rest:
                            vx = 0.0
                        vy *= slide
                        done = True
                        break
                if done:
                    break
        self.contact_point = (cx, cy)
        return px, py, vx, vy

    def hard_set_position(self, new_pos: V2) -> None:
        self.pos = new_pos
        self.last_pos = new_pos
        self.last_last_pos = new_pos
        if self.set_pos is not None:
            self.set_pos = new_pos

    def move_from_outside_my_update(self, eu: bool, move_to: V2) -> None:
        if self.owner.even_update == eu:
            self.pos = move_to
        else:
            self.set_pos = move_to


class BodyChunkConnection:
    NORMAL = "Normal"
    PULL = "Pull"
    PUSH = "Push"

    __slots__ = ("chunk1", "chunk2", "distance", "elasticity", "weight_symmetry", "active", "type")

    def __init__(self, chunk1, chunk2, distance, type_, elasticity, weight_symmetry):
        self.chunk1 = chunk1
        self.chunk2 = chunk2
        self.distance = distance
        self.type = type_
        self.elasticity = elasticity
        if weight_symmetry == -1.0:
            self.weight_symmetry = chunk2.mass / (chunk1.mass + chunk2.mass)
        else:
            self.weight_symmetry = weight_symmetry
        self.active = True
        chunk1.rotation_chunk = chunk2
        chunk2.rotation_chunk = chunk1

    def update(self) -> None:
        if not self.active:
            return
        c1, c2 = self.chunk1, self.chunk2
        d = math.hypot(c1.pos.x - c2.pos.x, c1.pos.y - c2.pos.y)
        t = self.type
        if (
            t == BodyChunkConnection.NORMAL
            or (t == BodyChunkConnection.PULL and d > self.distance)
            or (t == BodyChunkConnection.PUSH and d < self.distance)
        ):
            v = dir_vec(c1.pos, c2.pos)
            k = (self.distance - d) * self.elasticity
            v2 = v * (k * self.weight_symmetry)
            v3 = v * (k * (1.0 - self.weight_symmetry))
            c1.pos = c1.pos - v2
            c1.vel = c1.vel - v2
            c2.pos = c2.pos + v3
            c2.vel = c2.vel + v3


class PhysicalObject:
    """terrain 在每次 step 里由外部写入。room.gravity 恒为 1，所以 gravity 就是 PhysicalObject.g * 1。"""

    def __init__(self):
        self.terrain = None
        self.body_chunks: list[BodyChunk] = []
        self.body_chunk_connections: list[BodyChunkConnection] = []
        self.grabbed_by: list = []
        self.gravity = 0.9
        self.air_friction = 0.999
        self.surface_friction = 0.5
        self.bounce = 0.1
        self.impact_treshhold = 1.0
        self.even_update = False
        self.pos_tile = (0, 0)

    @property
    def first_chunk(self) -> BodyChunk:
        return self.body_chunks[0]

    @property
    def total_mass(self) -> float:
        return sum(c.mass for c in self.body_chunks)

    def update(self, eu: bool) -> None:
        for c in self.body_chunks:
            c.update()
        self.pos_tile = tile_xy(self.body_chunks[0].pos)
        for conn in self.body_chunk_connections:
            conn.update()
        for i in range(len(self.grabbed_by) - 1, -1, -1):
            g = self.grabbed_by[i]
            if g.discontinued or g.grabber.grasps[g.grasp_used] is not g:
                del self.grabbed_by[i]
        self.even_update = eu

    def terrain_impact(
        self, chunk: int, direction: tuple[int, int], speed: float, first_contact: bool
    ) -> None:
        pass

    def weighted_push(self, a: int, b: int, direction: V2, frc: float) -> None:
        ca, cb = self.body_chunks[a], self.body_chunks[b]
        num = cb.mass / (ca.mass + cb.mass)
        ca.vel = ca.vel + direction * (frc * num)
        cb.vel = cb.vel - direction * (frc * (1.0 - num))

    def is_tile_solid(self, b_chunk: int, relative_x: int, relative_y: int) -> bool:
        tx, ty = tile_xy(self.body_chunks[b_chunk].pos)
        return self.terrain.solid((tx + relative_x, ty + relative_y))

    def push_out_of(self, pos: V2, rad: float, excepted_chunk: int) -> None:
        for c in self.body_chunks:
            if c.index != excepted_chunk and math.hypot(c.pos.x - pos.x, c.pos.y - pos.y) < rad + c.rad:
                d = math.hypot(c.pos.x - pos.x, c.pos.y - pos.y)
                v = dir_vec(c.pos, pos)
                c.pos = c.pos - v * (rad + c.rad - d)
                c.vel = c.vel - v * (rad + c.rad - d)


class Creature(PhysicalObject):
    """晕眩计时与意识。不会死亡，所以 dead 恒为 False。"""

    def __init__(self):
        super().__init__()
        self.stun = 0
        self.dead = False
        self.grasps: list = [None]

    @property
    def stunned(self) -> bool:
        return self.stun >= 10

    @property
    def consious(self) -> bool:
        return not self.stunned and not self.dead

    @property
    def main_body_chunk(self) -> BodyChunk:
        return self.body_chunks[0]

    def update(self, eu: bool) -> None:
        if self.stun > 0:
            self.stun -= 1
        if self.stun < 10:
            for g in self.grabbed_by:
                if g.pacifying:
                    self.stun = 10
                    break
        super().update(eu)

    def apply_stun(self, st: int) -> None:
        """Creature.Stun。"""
        self.stun = max(self.stun, st)

    def lose_all_grasps(self) -> None:
        for i in range(len(self.grasps)):
            self.release_grasp(i)

    def release_grasp(self, grasp: int) -> None:
        if self.grasps[grasp] is not None:
            self.grasps[grasp].release()
