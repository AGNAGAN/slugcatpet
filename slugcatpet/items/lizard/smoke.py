"""跳跃烟雾：Smoke.CyanLizardSmoke 及其粒子（SmokeSystem / SmokeSystemParticle / SpriteSmoke 里用到的部分）。

只做模拟；绘制端对每个粒子调 draw_data(ts)，按其中的数值画两个 Futile_White 圆（scale 1.0 = 16px）。
room 是 terrain.Terrain；update(physical_objects) 的物体用 body_chunks（pos / last_pos / rad / mass）搅动烟雾。
"""

from __future__ import annotations

import math
import random

from .physics import tile_xy
from .rw import (
    V2,
    clamp_magnitude,
    closest_point_on_line,
    dir_vec,
    dist_less,
    distance,
    distance_to_line,
    inverse_lerp,
    lerp,
    lerp_map,
    perpendicular_vector,
    rnv,
    vec_to_deg,
    vlerp,
)

TILE = 20.0
_NAN = float("nan")


def _div(a: float, b: float) -> float:
    if b == 0.0:
        return _NAN if a == 0.0 else math.copysign(math.inf, a)
    return a / b


def _vertical_cross_point(a: V2, b: V2, x: float) -> V2:
    if a.y == b.y:
        return V2(x, a.y)
    k = _div(a.y - b.y, a.x - b.x)
    return V2(x, (a.y - a.x * k) + k * x)


def _horizontal_cross_point(a: V2, b: V2, y: float) -> V2:
    if a.x == b.x:
        return V2(a.x, y)
    k = _div(a.y - b.y, a.x - b.x)
    return V2(_div(y - (a.y - a.x * k), k), y)


def rect_collision(pos: V2, last_pos: V2, rect: tuple[float, float, float, float]) -> tuple[V2, V2]:
    """Custom.RectCollision：线段 last_pos→pos 与矩形 (left, bottom, right, top) 的第一个交点和面法向（朝矩形里）。
    原版把这两个值塞进 FloatRect 返回（GetCorner(D) / GetCorner(B)）。"""
    left, bottom, right, top = rect
    v1 = _vertical_cross_point(last_pos, pos, left)
    v2 = _vertical_cross_point(last_pos, pos, right)
    v3 = _horizontal_cross_point(last_pos, pos, bottom)
    v4 = _horizontal_cross_point(last_pos, pos, top)
    if last_pos.x == pos.x:
        v3 = V2(last_pos.x, bottom)
        v4 = V2(last_pos.x, top)
    inside = left < last_pos.x < right and bottom < last_pos.y < top
    dst = 3.4e38 if inside else distance(last_pos, pos)
    hit, normal = pos, V2()
    if bottom <= v1.y <= top and dist_less(last_pos, v1, dst):
        hit, dst, normal = v1, distance(last_pos, v1), V2(1.0, 0.0)
    if bottom <= v2.y <= top and dist_less(last_pos, v2, dst):
        hit, dst, normal = v2, distance(last_pos, v2), V2(-1.0, 0.0)
    if left <= v3.x <= right and dist_less(last_pos, v3, dst):
        hit, dst, normal = v3, distance(last_pos, v3), V2(0.0, 1.0)
    if left <= v4.x <= right and dist_less(last_pos, v4, dst):
        hit, dst, normal = v4, distance(last_pos, v4), V2(0.0, -1.0)
    return hit, normal


def ray_trace_first_solid(terrain, a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int] | None:
    """SharedPhysics.RayTraceTilesForTerrainReturnFirstSolid(IntVector2, IntVector2)。"""
    x0, y0 = a
    x1, y1 = b
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    x, y = x0, y0
    n = 1 + dx + dy
    sx = 1 if x1 > x0 else -1
    sy = 1 if y1 > y0 else -1
    err = dx - dy
    dx *= 2
    dy *= 2
    while n > 0:
        if terrain.solid((x, y)):
            return (x, y)
        if err > 0:
            x += sx
            err -= dy
        else:
            y += sy
            err += dx
        n -= 1
    return None


def closest_point_on_line_segment(a: V2, b: V2, test: V2) -> V2:
    """Custom.ClosestPointOnLineSegment。"""
    v = perpendicular_vector((a - b).normalized)
    if distance_to_line(test, a + v, a - v) >= 0.0:
        return a
    if distance_to_line(test, b + v, b - v) <= 0.0:
        return b
    return closest_point_on_line(a, b, test)


class SmokeSystemParticle:
    """粒子生命周期：Reset → resting（等下一次 update 才开始）→ 活着 → life 归零后 resting 且不再续，被系统回收。"""

    def __init__(self):
        self.owner: SmokeSystem | None = None
        self.pos = V2()
        self.last_pos = V2()
        self.vel = V2()
        self.resting = False
        self.turn_on_next_update = False
        self.slated_for_deletetion = False
        self.last_life = 1.0
        self.life = 1.0
        self.life_time = 1.0
        self.last_emitted = False
        self._np: SmokeSystemParticle | None = None
        self._pp: SmokeSystemParticle | None = None
        self.linger_pos = V2()
        self.last_linger_pos = V2()

    @property
    def next_particle(self):
        np = self._np
        if np is not None and np.resting:
            if not np.turn_on_next_update:
                self._np = None
            return None
        return np

    @next_particle.setter
    def next_particle(self, v) -> None:
        self._np = v
        if v is not None:
            v._pp = self

    @property
    def prev_particle(self):
        pp = self._pp
        if pp is not None and pp.resting:
            if not pp.turn_on_next_update:
                self._pp = None
            return None
        return pp

    @prev_particle.setter
    def prev_particle(self, v) -> None:
        self._pp = v
        if v is not None:
            v._np = self

    object_wind = 1.0

    def reset(self, new_owner: SmokeSystem, new_pos: V2, new_vel: V2, new_life_time: float) -> None:
        self.owner = new_owner
        self.vel = new_vel
        self.life_time = new_life_time
        self.pos = new_pos
        self.last_pos = new_pos
        self.linger_pos = new_pos + rnv(new_owner.rng)
        self.last_linger_pos = self.linger_pos
        self.life = 1.0
        self.last_life = 1.0
        self._np = None
        self._pp = None
        self.turn_on_next_update = True
        self.resting = True
        self.last_emitted = True

    def update(self) -> None:
        self.last_life = self.life
        self.last_linger_pos = self.linger_pos
        if self.resting:
            if not self.turn_on_next_update:
                return
            self.resting = False
            self.turn_on_next_update = False
        self.last_pos = self.pos
        self.pos = self.pos + self.vel
        self.life = max(0.0, self.life - 1.0 / self.life_time)
        if self.life <= 0.0 and self.last_life <= 0.0:
            self.resting = True
            self.turn_on_next_update = False
            self.next_particle = None
        if self.last_emitted and self.prev_particle is not None:
            self.last_emitted = False


class SpriteSmoke(SmokeSystemParticle):
    """用一个拉长的圆角条（粒子→下一粒子）加一个圆画的烟。"""

    to_mid_speed = 0.7

    def __init__(self):
        super().__init__()
        self.rad = 0.0
        self.stretched = 0.0
        self.last_stretched = 0.0

    def update(self) -> None:
        super().update()
        if self.resting:
            return
        nxt = self.next_particle
        if nxt is not None:
            b = vlerp(self.vel, nxt.vel, 0.5)
            self.vel = vlerp(self.vel, b, self.to_mid_speed)
            nxt.vel = vlerp(nxt.vel, b, 0.7)
            self.linger_pos = nxt.pos
        self.last_stretched = self.stretched
        self.stretched = inverse_lerp(60.0, 200.0, distance(self.pos, self.linger_pos))

    def reset(self, new_owner, pos, vel, new_life_time) -> None:
        super().reset(new_owner, pos, vel, new_life_time)
        self.stretched = 0.0
        self.last_stretched = 0.0

    def rad_of(self, typ: int, use_life: float, use_stretched: float, ts: float) -> float:
        return 1.0

    def _geometry(self, ts: float) -> dict:
        use_life = lerp(self.last_life, self.life, ts)
        use_stretched = lerp(self.last_stretched, self.stretched, ts)
        p = vlerp(self.last_pos, self.pos, ts)
        nxt = self.next_particle
        linger = vlerp(self.last_linger_pos, self.linger_pos, ts)
        if nxt is not None:
            linger = vlerp(nxt.last_pos, nxt.pos, ts)
        mid = vlerp(p, linger, 0.5)
        return {
            "life": use_life,
            "x0": mid.x,
            "y0": mid.y,
            "scale_x0": self.rad_of(0, use_life, use_stretched, ts) / 16.0,
            "scale_y0": (distance(p, linger) + self.rad_of(2, use_life, use_stretched, ts)) / 16.0,
            "rotation0": vec_to_deg(linger - p),
            "x1": p.x,
            "y1": p.y,
            "scale1": self.rad_of(1, use_life, use_stretched, ts) / 16.0,
        }


class CyanLizardParticle(SpriteSmoke):
    def __init__(self):
        super().__init__()
        self.lizard_graphics = None
        self.move_dir = 0.0
        self.counter = 0
        self.big = False

    def reset(self, new_owner, pos, vel, new_life_time) -> None:
        super().reset(new_owner, pos, vel, new_life_time)
        rng = new_owner.rng
        self.rad = lerp(28.0, 46.0, rng.random())
        self.move_dir = rng.random() * 360.0
        self.counter = 0

    def update(self) -> None:
        super().update()
        if self.resting:
            return
        m = self.vel.magnitude
        if m > 0.0:
            self.vel = self.vel * (0.7 + 0.3 / m**0.5)
        self.move_dir += lerp(-1.0, 1.0, self.owner.rng.random()) * 50.0
        self.counter += 1
        T = self.owner.room
        if T.solid(tile_xy(self.pos)) and not T.solid(tile_xy(self.last_pos)):
            first = ray_trace_first_solid(T, tile_xy(self.last_pos), tile_xy(self.pos)) or tile_xy(self.pos)
            c = T.middle_of(first)
            hit, n = rect_collision(
                self.pos,
                self.last_pos,
                (c.x - 10.0 - 2.0, c.y - 10.0 - 2.0, c.x + 10.0 + 2.0, c.y + 10.0 + 2.0),
            )
            self.pos = hit
            if n.x < 0.0:
                self.vel = V2(abs(self.vel.x), self.vel.y)
            elif n.x > 0.0:
                self.vel = V2(-abs(self.vel.x), self.vel.y)
            elif n.y < 0.0:
                self.vel = V2(self.vel.x, abs(self.vel.y))
            elif n.y > 0.0:
                self.vel = V2(self.vel.x, -abs(self.vel.y))

    def rad_of(self, typ: int, use_life: float, use_stretched: float, ts: float) -> float:
        if typ == 0:
            num = lerp(4.0, self.rad, (1.0 - use_life) ** 0.2 + use_stretched)
        elif typ == 1:
            num = 1.5 * lerp(2.0, self.rad, (1.0 - use_life) ** 0.2)
        else:
            num = lerp(4.0, self.rad, (1.0 - use_life) ** 0.2)
        if self.big:
            return num * (1.0 + inverse_lerp(0.0, 10.0, self.counter + ts))
        return num * 0.2

    def draw_data(self, ts: float) -> dict | None:
        """resting（刚生成或已死）时返回 None。

        x0,y0,scale_x0,scale_y0,rotation0：拉长条（Futile_White，FireSmoke 着色器）；中心 (x0,y0)，
          scale_x0 是宽、scale_y0 是长（沿自身 y 轴），rotation0 是原版 Futile 度数（0 朝上，顺时针为正，y↑ 空间）。
        x1,y1,scale1：圆（同着色器）。
        alpha0 / alpha1：两个精灵的透明度。
        颜色（两个精灵相同）：base = big ? lizard_graphics.effect_color : lizard_graphics.HeadColor(ts)；
          color = lerp(base, fade_color, fade_t)；fade_color = lerp(房间黑色, 房间雾色, 0.6)，桌宠里用调色板暗色即可。
        """
        if self.resting:
            return None
        g = self._geometry(ts)
        num = g["life"]
        k = 1.0 - 0.2 * inverse_lerp(0.0, 10.0, self.counter + ts) if self.big else 1.0
        fade_t = inverse_lerp(1.0, 0.25, num) * (1.0 if self.big else 0.5)
        return {
            "x0": g["x0"],
            "y0": g["y0"],
            "scale_x0": g["scale_x0"],
            "scale_y0": g["scale_y0"],
            "rotation0": g["rotation0"],
            "x1": g["x1"],
            "y1": g["y1"],
            "scale1": g["scale1"],
            "alpha0": num**0.25 * (1.0 - self.stretched) * k,
            "alpha1": (0.3 + math.sin(num * math.pi) ** 0.7 * 0.65 * (1.0 - self.stretched)) * k,
            "fade_t": fade_t,
            "big": self.big,
            "lizard_graphics": self.lizard_graphics,
        }


class SmokeSystem:
    def __init__(self, room, connect_particles_time: int, min_particle_distance: float, rng=None):
        self.room = room
        self.rng = rng if rng is not None else random.Random()
        self.connect_particles_time = connect_particles_time
        self.min_particle_distance = min_particle_distance
        self.particles: list[SmokeSystemParticle] = []
        self.counter = 0
        self.check_phys_obj = 0
        self.object_wind = 1.0
        self.slated_for_deletetion = False

    @property
    def dead(self) -> bool:
        return self.counter > self.connect_particles_time + 100 and len(self.particles) < 1

    def disconnect_smoke(self) -> None:
        self.counter = self.connect_particles_time

    def update(self, physical_objects=()) -> None:
        """先回收死掉的粒子、让物体搅动烟，再推进各粒子。"""
        self.counter += 1
        self.particles = [
            p
            for p in self.particles
            if not p.slated_for_deletetion and not (p.resting and not p.turn_on_next_update)
        ]
        if self.object_wind > 0.0 and self.particles and physical_objects:
            self.check_phys_obj += 1
            obj = physical_objects[self.check_phys_obj % len(physical_objects)]
            self.physical_object_affect_smoke(obj, min(len(physical_objects), 16.0) * self.object_wind)
        for p in list(self.particles):
            p.update()

    def add_particle(self, emission_point: V2, emission_force: V2, life_time: float):
        if self.slated_for_deletetion or self.room is None:
            return None
        connect = self.counter < self.connect_particles_time
        self.counter = 0
        if (
            self.min_particle_distance > 0.0
            and self.particles
            and dist_less(emission_point, self.particles[-1].pos, self.min_particle_distance)
        ):
            return None
        p = self.create_particle()
        self.particles.append(p)
        p.reset(self, emission_point, emission_force, life_time)
        if connect and len(self.particles) > 2:
            p.next_particle = self.particles[-2]
        return p

    def create_particle(self) -> SmokeSystemParticle:
        raise NotImplementedError

    def physical_object_affect_smoke(self, obj, fac: float) -> None:
        chunks = obj.body_chunks
        if all(dist_less(c.pos, c.last_pos, 1.0) for c in chunks):
            return
        for ch in chunks:
            num = distance(ch.last_pos, ch.pos)
            if num <= 0.0:
                continue
            num2 = ch.rad * (1.0 + inverse_lerp(1.0, 250.0, num**1.5)) + 20.0 + 60.0 * ch.mass
            for p in self.particles:
                if not p.object_wind > 0.0 or not dist_less(chunks[0].pos, p.pos, num2 * 2.0 + num):
                    continue
                num3 = distance(p.pos, closest_point_on_line_segment(ch.last_pos, ch.pos, p.pos))
                if num3 < num2 * 2.0:
                    num4 = (
                        lerp_map(
                            abs(distance_to_line(p.pos, ch.last_pos, ch.pos)),
                            ch.rad,
                            num2 * 2.0,
                            1.0,
                            -0.5,
                            0.3,
                        )
                        * inverse_lerp(ch.rad, num2 * 2.0, num3) ** 0.3
                        * p.object_wind
                    )
                    p.vel = p.vel + clamp_magnitude(
                        (ch.pos - ch.last_pos) * (fac * num4 * num**0.85) / 140.0, 5.0
                    )
                    if num4 < 0.0:
                        p.vel = p.vel + clamp_magnitude(
                            dir_vec(p.pos, closest_point_on_line(ch.last_pos, ch.pos, p.pos))
                            * (abs(num4) * fac * num**0.75)
                            / 30.0,
                            5.0,
                        )


class CyanLizardSmoke(SmokeSystem):
    CyanLizardParticle = CyanLizardParticle

    def __init__(self, room, rng=None):
        super().__init__(room, 2, 0.0, rng)

    def create_particle(self) -> SmokeSystemParticle:
        return CyanLizardParticle()

    def emit_smoke(self, pos: V2, vel: V2, l_graphics, big: bool, max_life_time: float) -> None:
        p = self.add_particle(pos, vel, max_life_time * lerp(0.3, 1.0, self.rng.random()))
        if p is not None:
            p.lizard_graphics = l_graphics
            p.big = big

    def draw_list(self, ts: float) -> list[dict]:
        """当前所有可见粒子的 draw_data，按创建顺序（原版同层，后创建的画在上面）。"""
        out = []
        for p in self.particles:
            d = p.draw_data(ts)
            if d is not None:
                out.append(d)
        return out
