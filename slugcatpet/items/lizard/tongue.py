"""青蜥蜴的舌头：LizardTongue 状态机（出舌、粘物体 / 地形、拉扯、收回）与舌头图形节的更新。

被粘的对象 attached 是任何有 owner 的身体节（蛋虫的 _ChunkView、另一只蜥蜴的 BodyChunk）；
目标候选取 lizard.ctx.creatures。
"""

from __future__ import annotations

import math

from . import sfx
from .physics import tile_xy, visual_contact, vslerp
from .rw import V2, clamp, deg_to_vec, dir_vec, dist_less, distance, dot, inverse_lerp, lerp, vlerp


class State:
    Hidden = "Hidden"
    LashingOut = "LashingOut"
    Attatched = "Attatched"
    AttachedInSmallObject = "AttachedInSmallObject"
    Retracting = "Retracting"
    StuckInTerrain = "StuckInTerrain"


# range, elasticRange, lashOutSpeed, reelInSpeed, chunkDrag, terrainDrag, dragElasticity,
# emptyElasticity, involuntaryReleaseChance, voluntaryReleaseChance
_PARAMS = {
    "white": (540.0, 0.1, 30.0, 0.0033333334, 0.0, 0.0, 0.05, 0.01, 0.000125, 0.05),
    "blue": (190.0, 0.0, 26.0, 0.0, 0.04, 0.04, 0.0, 0.07, 0.0033333334, 1.0),
    "cyan": (140.0, 0.55, 16.0, 0.002, 0.01, 0.01, 0.1, 0.8, 0.005, 0.02),
}


def circles_collision_time(
    x1: float, y1: float, x2: float, y2: float, vx1: float, vy1: float, r1: float, r2: float
) -> float:
    """Custom.CirclesCollisionTime：半径 r1 的圆从 (x1,y1) 以 (vx1,vy1) 运动、撞上静止的 (x2,y2,r2) 的时刻（0..1 为本步内）。"""
    n1 = n2 = 0.001
    a = -x1 * vx1 - y1 * vy1 + vx1 * x2 + vy1 * y2 + x1 * n1 - x2 * n1 + y1 * n2 - y2 * n2
    c = vx1**2 + vy1**2 - 2.0 * vx1 * n1 + n1**2 - 2.0 * vy1 * n2 + n2**2
    d = x1**2 + y1**2 - r1**2 - 2.0 * x1 * x2 + x2**2 - 2.0 * y1 * y2 + y2**2 - 2.0 * r1 * r2 - r2**2
    disc = (-2.0 * a) ** 2 - 4.0 * c * d
    if disc < 0.0 or c == 0.0:
        return math.nan
    return (2.0 * a - math.sqrt(disc)) / (2.0 * c)


def trace_projectile_against_body_chunks(lizard, last_pos: V2, pos: V2, rad: float):
    """SharedPhysics.TraceProjectileAgainstBodyChunks（collisionLayer -1，无 appendage）：
    返回线段扫过的最先碰到的身体节，没有则 None。"""
    best_t = 3.4e38
    best = None
    for obj in getattr(lizard.ctx, "creatures", ()):
        if obj is lizard or getattr(obj, "kind_key", None) == "cursor":
            continue
        if getattr(obj, "gone", False) or not getattr(obj, "collidable", True):
            continue
        if any(g.grabber is lizard for g in obj.grabbed_by):
            continue
        for ch in obj.body_chunks:
            t = circles_collision_time(
                last_pos.x,
                last_pos.y,
                ch.pos.x,
                ch.pos.y,
                pos.x - last_pos.x,
                pos.y - last_pos.y,
                rad,
                ch.rad,
            )
            if 0.0 < t < 1.0 and t < best_t:
                best_t = t
                best = ch
    return best


class LizardTongue:
    State = State

    def __init__(self, lizard):
        self.lizard = lizard
        self.state = State.Hidden
        self.attach_terrain_chance = 0.5
        self.pull_at_chunk_ratio = 1.0
        self.detatch_min_distance_terrain = 20.0
        self.detatch_min_distance_creature = 20.0
        self.tot_r_extra_limit = 40.0
        (
            self.range,
            self.elastic_range,
            self.lash_out_speed,
            self.reel_in_speed,
            self.chunk_drag,
            self.terrain_drag,
            self.drag_elasticity,
            self.empty_elasticity,
            self.involuntary_release_chance,
            self.voluntary_release_chance,
        ) = _PARAMS[lizard.lizard_params.key]
        self.blue = lizard.lizard_params.key == "blue"
        self.base_drag_only = self.blue
        self.tot_r = self.range * 1.1
        self.graph_pos = [V2(), V2()]
        self.last_pos = V2()
        self.pos = V2()
        self.vel = V2()
        self.dist = 0.0
        self.reel_in = 0.0
        self.attached = None
        self.stuck_counter = 0
        self.delay = 0
        self.bite_inanimate = False

    # 派生量

    @property
    def tot_range(self) -> float:
        return self.tot_r * self.reel_in

    @property
    def el_range(self) -> float:
        return self.tot_r * self.elastic_range * self.reel_in * self.reel_in

    @property
    def out(self) -> bool:
        return self.state != State.Hidden

    @property
    def ready(self) -> bool:
        return self.delay < 1

    def _drag(self, base: float) -> float:
        if self.base_drag_only:
            return base * self.dist
        return max(
            base * self.dist,
            (self.drag_elasticity if self.dist < self.tot_range else 1.0)
            * (self.dist - self.el_range)
            * inverse_lerp(self.el_range, self.tot_range, self.dist),
        )

    @property
    def chunk_drag_now(self) -> float:
        return self._drag(self.chunk_drag)

    @property
    def terrain_drag_now(self) -> float:
        return self._drag(self.terrain_drag)

    @property
    def stretched(self) -> float:
        return inverse_lerp(0.0, self.el_range, self.dist)

    @property
    def super_stretched(self) -> float:
        return inverse_lerp(self.el_range, self.tot_range, self.dist)

    @property
    def combined_stretched(self) -> float:
        return inverse_lerp(0.0, self.tot_r, self.dist)

    @property
    def stuck_to_something(self) -> bool:
        return self.state == State.Attatched or self.state == State.StuckInTerrain

    # 每 tick

    def update(self) -> None:
        L = self.lizard
        c = L.body_chunks
        main = c[0]
        rng = L.rng
        T = L.terrain
        self.graph_pos[1] = self.graph_pos[0]
        if not L.consious and self.state != State.Hidden:
            self.state = State.Retracting
        if self.out:
            if self.state != State.Retracting and not visual_contact(T, main.pos, self.pos):
                self.state = State.Retracting
            self.dist = distance(self.pos, main.pos)
            main.vel = main.vel + dir_vec(main.pos, self.pos) * 4.0
            c[1].vel = c[1].vel - dir_vec(main.pos, self.pos) * 4.0
            if self.stuck_to_something and (
                self.reel_in < 0.0
                or dot(dir_vec(main.pos, self.pos), dir_vec(c[1].pos, main.pos)) < -0.5
                or self.dist > self.tot_r + self.tot_r_extra_limit
            ):
                self.retract()
            if self.state == State.StuckInTerrain and self.dist < self.detatch_min_distance_terrain:
                self.retract()
            if self.state == State.Attatched and self.dist < self.detatch_min_distance_creature:
                self.retract()
            if self.stuck_to_something:
                self.stuck_counter += 1
                if L.ai.do_i_want_to_hold_this_with_my_tongue(self.attached):
                    if rng.random() < self.involuntary_release_chance and self.dist > self.elastic_range:
                        self.retract()
                elif rng.random() < self.voluntary_release_chance:
                    self.retract()
                if self.blue and (
                    (L.jaw_open < 0.1 and rng.random() < 0.125)
                    or rng.random() < inverse_lerp(20.0, 120.0, self.stuck_counter)
                ):
                    self.retract()
            else:
                self.stuck_counter = 0
        st = self.state
        if st == State.Hidden:
            if self.delay > 0:
                self.delay -= 1
            self.last_pos = main.last_pos
            self.pos = main.pos
            self.graph_pos[0] = self.pos
            self.vel = V2()
        elif st == State.LashingOut:
            self._lashing_out()
        elif st == State.Attatched:
            self._attached()
        elif st == State.Retracting or st == State.AttachedInSmallObject:
            self._retracting()
        elif st == State.StuckInTerrain:
            self.graph_pos[0] = self.pos
            self.vel = V2()
            v = dir_vec(main.pos, self.pos)
            d = self.terrain_drag_now
            main.vel = main.vel + v * d
            main.pos = main.pos + v * d
            self.reel_in -= self.reel_in_speed

    def _lashing_out(self) -> None:
        L = self.lizard
        c = L.body_chunks
        main = c[0]
        T = L.terrain
        rng = L.rng
        self.last_pos = self.pos
        self.pos = self.pos + self.vel
        self.vel = V2(self.vel.x, self.vel.y - 0.1)
        self.graph_pos[0] = self.pos
        if not dist_less(self.pos, main.pos, self.tot_range):
            k = self.dist - self.tot_range
            self.vel = self.vel + dir_vec(self.pos, main.pos) * k
            self.pos = self.pos + dir_vec(self.pos, main.pos) * k
        elif not dist_less(self.pos, main.pos, self.el_range):
            self.vel = self.vel + dir_vec(self.pos, main.pos) * (
                (self.dist - self.el_range) * self.empty_elasticity
            )
        rhs = dir_vec(c[1].pos, main.pos)
        self.attached = trace_projectile_against_body_chunks(L, self.last_pos, self.pos, 3.0)
        a = self.attached
        if a is not None:
            if a.owner.total_mass < 0.2:
                self.state = State.AttachedInSmallObject
                a.pos = self.pos
                for g in reversed(list(a.owner.grabbed_by)):
                    self.bite_inanimate = True
                    gm = g.grabber.body_chunks[0]
                    gm.vel = gm.vel + dir_vec(gm.pos, main.pos) * 1.8 / gm.mass
                    g.grabber.release_grasp(g.grasp_used)
            else:
                self._impact()
                self.state = State.Attatched
                a.vel = a.vel + self.vel * (0.15 / a.mass)
            sfx.play("Lizard_Tongue_Attatch_NPC", self.pos)
        elif T.solid(tile_xy(self.pos)):
            v2 = self.last_pos
            t = 0.0
            while t < 1.0 and not T.solid(tile_xy(vlerp(self.last_pos, self.pos, t))):
                v2 = vlerp(self.last_pos, self.pos, t)
                t += 0.05
            self.pos = v2
            sfx.play("Lizard_Tongue_Attatch_Terrain", v2)
            self.state = (
                State.StuckInTerrain if rng.random() < self.attach_terrain_chance else State.Retracting
            )
            self._impact()
            self.vel = V2()
        elif dot(self.vel.normalized, rhs) < 0.0:
            self.state = State.Retracting
        L.jaw_open = clamp(L.jaw_open + 0.4, 0.0, 1.0)

    def _attached(self) -> None:
        L = self.lizard
        main = L.body_chunks[0]
        a = self.attached
        if a is None or getattr(a.owner, "gone", False) or not getattr(a.owner, "collidable", True):
            self.retract()
            return
        self.pos = a.pos
        self.vel = a.vel
        self.last_pos = a.last_pos
        self.graph_pos[0] = self.pos + dir_vec(self.pos, main.pos) * max(a.rad - 7.5, 0.0)
        self.reel_in -= self.reel_in_speed
        if L.rng.random() < 0.5 and not dist_less(
            main.pos, self.pos, lerp(self.el_range, self.tot_range, 0.75)
        ):
            self.reel_in = min(self.reel_in + 0.01, 1.0)
        self._pull_at_chunk()
        f = getattr(a.owner, "pulled_by_tongue", None)
        if f is not None:
            f()

    def _retracting(self) -> None:
        L = self.lizard
        c = L.body_chunks
        main = c[0]
        self.last_pos = self.pos
        self.pos = self.pos + self.vel
        self.graph_pos[0] = self.pos
        v4 = main.pos + dir_vec(c[1].pos, main.pos) * (self.dist * 0.5)
        self.vel = vlerp(self.vel, dir_vec(self.pos, v4) * ((distance(self.pos, v4) + 5.0) * 0.5), 0.5)
        if self.state == State.AttachedInSmallObject:
            if self.attached is None:
                self.state = State.Retracting
            else:
                self.attached.pos = self.pos
                self.attached.vel = self.vel
        if not dist_less(self.pos, main.pos, 10.0):
            return
        sfx.play("Lizard_Tongue_Go_Back_In_Mouth", main.pos)
        self.state = State.Hidden
        if self.attached is not None:
            if self.bite_inanimate:
                grab = getattr(L, "grab_inanimate", None)
                if grab is not None:
                    grab(self.attached)
            self.attached = None

    def lash_out(self, target: V2) -> None:
        L = self.lizard
        c = L.body_chunks
        main = c[0]
        rng = L.rng
        target = V2(target.x, target.y + distance(main.pos, target) * 0.05)
        lhs = dir_vec(c[1].pos, main.pos)
        vector = dir_vec(main.pos, target)
        if not dot(lhs, vector) > 0.3:
            return
        num = lerp(inverse_lerp(self.el_range * 0.5, self.tot_r, distance(main.pos, target)), 1.0, 0.75)
        self.vel = vector * (self.lash_out_speed * num)
        self.state = State.LashingOut
        self.reel_in = 1.0
        self.delay = 20
        self.bite_inanimate = False
        L.jaw_open = 1.0
        c[1].vel = c[1].vel - vector * (5.0 if self.blue else self.lash_out_speed)
        gfx = L.graphics_module
        n = len(gfx.tongue)
        for i in range(n):
            v2 = self.vel + deg_to_vec(rng.random() * 360.0) * (
                rng.random() * self.lash_out_speed * num * 0.75
            )
            self._water_drip(main.pos, v2 * (0.5 * rng.random()))
            if self.blue:
                gfx.tongue[i].vel = c[0].vel
            else:
                gfx.tongue[i].vel = vslerp(
                    v2, dir_vec(main.pos, gfx.head.pos) * (self.lash_out_speed * num), i / n
                )
        sfx.play("Blue_Lizard_Tongue_Shoot_Out" if self.blue else "White_Lizard_Tongue_Shoot_Out", main.pos)

    def retract(self) -> None:
        if self.state == State.StuckInTerrain or self.attached is not None:
            sfx.play("Lizard_Tongue_Detatch_NPC_Or_Terrain", self.pos)
        self.state = State.Retracting
        self.attached = None

    def _pull_at_chunk(self) -> None:
        main = self.lizard.body_chunks[0]
        a = self.attached
        v = dir_vec(main.pos, a.pos)
        num = main.mass / (main.mass + a.mass)
        d = self.chunk_drag_now
        v2 = v * (d * (1.0 - num))
        main.vel = main.vel + v2
        main.pos = main.pos + v2
        v3 = v * (d * num * self.pull_at_chunk_ratio)
        a.vel = a.vel - v3
        a.pos = a.pos - v3

    def _impact(self) -> None:
        L = self.lizard
        rng = L.rng
        for _ in range(3):
            self._water_drip(
                self.pos,
                (-self.vel + deg_to_vec(rng.random() * 360.0) * (self.vel.magnitude * rng.random()))
                * rng.random(),
            )
        for part in L.graphics_module.tongue:
            part.pos = part.pos + deg_to_vec(rng.random() * 360.0) * (rng.random() * 0.5 * self.vel.magnitude)
            part.vel = part.vel + deg_to_vec(rng.random() * 360.0) * (rng.random() * 0.5 * self.vel.magnitude)

    def _water_drip(self, pos: V2, vel: V2) -> None:
        """WaterDrip 小水滴：宿主有 add_water_drip 才生成。"""
        f = getattr(self.lizard, "add_water_drip", None)
        if f is not None:
            f(pos, vel)

    def update_graphics(self, gfx) -> None:
        """LizardGraphics.Update 里舌头图形节的那一段：不在外面时贴着舌根，在外面时按舌头状态拉伸。"""
        L = self.lizard
        main = L.body_chunks[0]
        dp = gfx.draw_positions
        tg = gfx.tongue
        n = len(tg)
        for i in range(n):
            part = tg[i]
            if not self.out:
                part.pos = self.pos
                part.last_pos = self.last_pos
                part.vel = V2()
                continue
            part.update()
            if L.rng.random() < 0.01 and part.vel.magnitude > 10.0:
                self._water_drip(part.pos, part.vel * L.rng.random())
            f = i / (n - 1)
            g = abs(i - (n - 1) / 2.0) / ((n - 1) / 2.0)
            f3 = 1.0 if self.state == State.Retracting else g
            v7 = dp[0][0] + vslerp(
                dir_vec(dp[0][0], self.graph_pos[0]),
                dir_vec(dp[1][0], dp[0][0]),
                (1.0 - f) ** (1.0 + self.stretched**2.0 * 10.0) * 0.5,
            ) * (distance(dp[0][0], self.graph_pos[0]) * f)
            part.pos = vlerp(part.pos, v7, max(self.stretched * 0.05 + self.super_stretched * 0.2, f3**3.0))
            part.vel = part.vel + (v7 - part.pos) * (self.stretched * 0.2 + self.super_stretched * 0.3)
            cs = self.combined_stretched
            if L.lizard_params.key == "white":
                part.rad = (2.0 + 0.75 * (1.0 - cs) + lerp(8.0, 1.0, g) * (1.0 - cs**0.5)) / (
                    1.0 + f * 0.5 + (self.super_stretched + 0.5) * 3.0 * (1.0 - g)
                )
            else:
                part.rad = (2.0 + lerp(3.0, 1.0, g) * (1.0 - cs**0.5)) / (
                    1.0 + f * 0.5 + (self.super_stretched + 0.5) * 0.5 * (1.0 - g)
                )
            part.push_out_of_terrain(L.terrain, main.pos)
