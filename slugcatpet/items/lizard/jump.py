"""青蜥蜴的跳跃模块：LizardJumpModule（JumpFinder 找落点、蓄力、起跳、空中、抓地）、JumpLight、ShockWave。

房间 = lizard.terrain（terrain.Terrain），寻路单元 PathingCell 是 lizard.pather 的只读视图。
JumpLight / ShockWave 在模块里自己推进，绘制端读 jump_module.lights / shock_waves 的 draw_data。
"""

from __future__ import annotations

import math
import random

from . import sfx
from .pather import FALLBACK_CELL, PathingCell
from .physics import Animation, solid_cache, tile_xy
from .rw import (
    EIGHT_DIRECTIONS,
    V2,
    deg_to_vec,
    dir_vec,
    dist_less,
    dot,
    int_clamp,
    inverse_lerp,
    lerp,
    lerp_map,
    perpendicular_vector,
    rnv,
    vlerp,
)

TILE = 20.0
_INF = math.inf


def _ray_tiles(ax: float, ay: float, bx: float, by: float) -> list[tuple[int, int]]:
    ax, ay, bx, by = ax / TILE, ay / TILE, bx / TILE, by / TILE
    dx, dy = abs(bx - ax), abs(by - ay)
    fax, fay = math.floor(ax), math.floor(ay)
    x, y = fax, fay
    dt_dx = 1.0 / dx if dx else _INF
    dt_dy = 1.0 / dy if dy else _INF
    n = 1
    if dx == 0.0:
        x_inc, t_h = 0, dt_dx
    elif bx > ax:
        x_inc = 1
        n += math.floor(bx) - x
        t_h = (fax + 1 - ax) * dt_dx
    else:
        x_inc = -1
        n += x - math.floor(bx)
        t_h = (ax - fax) * dt_dx
    if dy == 0.0:
        y_inc, t_v = 0, dt_dy
    elif by > ay:
        y_inc = 1
        n += math.floor(by) - y
        t_v = (fay + 1 - ay) * dt_dy
    else:
        y_inc = -1
        n += y - math.floor(by)
        t_v = (ay - fay) * dt_dy
    out = []
    while n > 0:
        out.append((x, y))
        if t_v < t_h:
            y += y_inc
            t_v += dt_dy
        else:
            x += x_inc
            t_h += dt_dx
        n -= 1
    return out


def ray_traced_tiles(a: V2, b: V2) -> list[tuple[int, int]]:
    """SharedPhysics.RayTracedTilesArray：线段 a→b 经过的格，按顺序。"""
    return _ray_tiles(a.x, a.y, b.x, b.y)


class _View:
    """某地形 + 某品种的格子数组：实心 / 离实心的格距 / 窄缝 / 杆 / 品种可达。下标 (tx+1) + (ty+1)*W，环外按实心。"""

    def __init__(self, terrain, breed):
        W, H, grid, _ = solid_cache(terrain)
        self.W, self.H = W, H
        self.solid = grid
        n = W * H
        self.narrow = bytearray(n)
        self.beam = bytearray(n)
        self.accessible = bytearray(n)
        self.midx = [0.0] * n
        self.midy = [0.0] * n
        for j in range(H):
            for i in range(W):
                t = (i - 1, j - 1)
                k = i + j * W
                m = terrain.middle_of(t)
                self.midx[k], self.midy[k] = m.x, m.y
                if terrain.narrow_space(t):
                    self.narrow[k] = 1
                if terrain.vertical_beam(t) or terrain.horizontal_beam(t):
                    self.beam[k] = 1
                if terrain.accessible(t, breed):
                    self.accessible[k] = 1
        # AImap.getTerrainProximity（公开接口），外环外按 -1
        prox = [0] * n
        for k in range(n):
            prox[k] = terrain.terrain_proximity((k % W - 1, k // W - 1))
        self.prox = prox

    def idx(self, t) -> int:
        i, j = t[0] + 1, t[1] + 1
        if i < 0 or j < 0 or i >= self.W or j >= self.H:
            return -1
        return i + j * self.W

    def is_solid(self, t) -> bool:
        k = self.idx(t)
        return k < 0 or self.solid[k] == 1


def _view(terrain, breed) -> _View:
    cache = terrain.__dict__.get("_jump_views")
    if cache is None:
        cache = terrain._jump_views = {}
    v = cache.get(breed.key)
    if v is None:
        v = cache[breed.key] = _View(terrain, breed)
    return v


def pathing_cell_at(pather, tile) -> PathingCell:
    """PathFinder.PathingCellAtWorldCoordinate：lizard.pather 的公开只读视图。"""
    return pather.cell(tile)


def path_weight_comparison(a: PathingCell | None, b: PathingCell | None) -> bool:
    """LizardJumpModule.PathWeightComparison：b 比 a 更靠近目的地。"""
    if a is None:
        return b is not None
    if b is None:
        return False
    if b.legality != 0:
        return False
    if b.generation == a.generation:
        return b.resistance < a.resistance
    return b.generation > a.generation


def _float_dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class JumpInstruction:
    """JumpFinder.JumpInstruction（值类型：赋值要 copy）。"""

    __slots__ = ("goal_cell", "tick", "start_pos", "init_vel", "power", "grab_when_landing")

    def __init__(self, start_pos: V2 | None = None, init_vel: V2 | None = None, power: float = 0.0):
        self.start_pos = start_pos if start_pos is not None else V2()
        self.init_vel = init_vel if init_vel is not None else V2()
        self.power = power
        self.goal_cell: PathingCell | None = None
        self.tick = 0
        self.grab_when_landing = False

    def copy(self) -> JumpInstruction:
        j = JumpInstruction(self.start_pos, self.init_vel, self.power)
        j.goal_cell = self.goal_cell
        j.tick = self.tick
        j.grab_when_landing = self.grab_when_landing
        return j

    def is_default(self) -> bool:
        """== default(JumpInstruction)。"""
        return (
            self.goal_cell is None
            and self.tick == 0
            and self.start_pos == V2()
            and self.init_vel == V2()
            and self.power == 0.0
            and not self.grab_when_landing
        )


class JumpFinder:
    """从 start_pos 这一格随机试射抛物线，记下落到可抓地形上、且比当前位置更靠近目的地的最好一次。"""

    def __init__(self, owner: LizardJumpModule, start_pos: tuple[int, int], chain_jump: bool):
        self.owner = owner
        self.slated_for_deletion = False
        self.start_pos = (int(start_pos[0]), int(start_pos[1]))
        self.fade = 0
        self.best_jump = JumpInstruction()
        self.current_jump = JumpInstruction()
        self.px = self.py = self.lpx = self.lpy = self.vx = self.vy = 0.0
        self.has_ventured_away_from_terrain = False
        self.landing_direction: V2 | None = None
        self.chain_jump = chain_jump
        self.start_cell = pathing_cell_at(owner.lizard.pather, self.start_pos)
        self.new_test()

    @property
    def room(self):
        return self.owner.room

    @property
    def beneficial_movement(self) -> bool:
        bj = self.best_jump
        o = self.owner
        if (
            not bj.is_default()
            and bj.goal_cell is not None
            and _float_dist(self.start_pos, bj.goal_cell.world_coordinate) > 5.0
            and o.dist_to_destination(bj.goal_cell.world_coordinate) > 3.0
            and not path_weight_comparison(bj.goal_cell, o.lizard_cell)
        ):
            return not path_weight_comparison(bj.goal_cell, self.start_cell)
        return False

    def update(self) -> None:
        o = self.owner
        if o.in_standard_run_mode:
            self.fade += 1
            if not path_weight_comparison(o.lizard_cell, self.start_cell):
                self.fade += 10
            if self.fade > 40:
                self.destroy()
        for _ in range(max(1, 100 // max(1, len(o.jump_finders))) + 1):
            self.iterate()
        if o.act_on_jump is not self:
            return
        goal = self.best_jump.goal_cell
        best = goal
        gx, gy = goal.world_coordinate
        for dx, dy in EIGHT_DIRECTIONS:
            c = pathing_cell_at(o.lizard.pather, (gx + dx, gy + dy))
            if path_weight_comparison(best, c):
                best = c
        if best != goal and best.world_coordinate is not None:
            T = self.room
            self.landing_direction = dir_vec(
                T.middle_of(goal.world_coordinate), T.middle_of(best.world_coordinate)
            )

    def iterate(self) -> None:
        o = self.owner
        v = o.view
        lx, ly = self.px, self.py
        px, py = lx + self.vx, ly + self.vy
        self.lpx, self.lpy, self.px, self.py = lx, ly, px, py
        self.vx, self.vy = self.vx * 0.999, self.vy * 0.999 - 0.9
        tiles = _ray_tiles(lx, ly, px, py)
        ex, ey = lx - px, ly - py
        m = math.hypot(ex, ey)
        perp_x, perp_y = (-ey / m, ex / m) if m > 1e-5 else (0.0, 0.0)
        W, H = v.W, v.H
        solid, prox, narrow, beam, acc = v.solid, v.prox, v.narrow, v.beam, v.accessible
        cj = self.current_jump
        w = lerp_map(cj.tick, 5.0, 20.0, 10.0, 20.0)
        sx, sy = self.start_pos
        up_of_start_solid = v.is_solid((sx, sy + 1))
        floor = math.floor

        def solid_at(x: float, y: float) -> bool:
            i, j = floor(x / TILE) + 1, floor(y / TILE) + 1
            return i < 0 or j < 0 or i >= W or j >= H or solid[i + j * W] == 1

        for t in tiles:
            tx, ty = t
            i, j = tx + 1, ty + 1
            if i < 0 or j < 0 or i >= W or j >= H:
                self.new_test()
                return
            k = i + j * W
            if solid[k] or ty < 0 or narrow[k]:
                self.new_test()
                return
            p = prox[k]
            if not self.has_ventured_away_from_terrain and p > 1 and not beam[k]:
                self.has_ventured_away_from_terrain = True
            if (
                self.has_ventured_away_from_terrain
                and acc[k]
                and (p == 1 or beam[k])
                and _float_dist(self.start_pos, t) > int_clamp(int(cj.init_vel.magnitude / 3.0), 5, 20)
                and o.dist_to_destination(t) > 3.0
            ):
                cell = pathing_cell_at(o.lizard.pather, t)
                if path_weight_comparison(self.best_jump.goal_cell, cell):
                    bj = self.best_jump = cj.copy()
                    bj.goal_cell = cell
                    gx, gy = cell.world_coordinate
                    d = dir_vec(V2(lx, ly), V2(px, py))
                    pv = perpendicular_vector(d)
                    bj.grab_when_landing = not solid_at(
                        v.midx[(gx + 1) + (gy + 1) * W] + pv.x * 15.0 + d.x * 20.0,
                        v.midy[(gx + 1) + (gy + 1) * W] + pv.y * 15.0 + d.y * 20.0,
                    )
            mx, my = v.midx[k], v.midy[k]
            if (
                (not up_of_start_solid and (j + 1 >= H or solid[k + W] == 1))
                or solid_at(mx + perp_x * w, my + perp_y * w)
                or solid_at(mx - perp_x * w, my - perp_y * w)
            ):
                self.new_test()
                return
        cj.tick += 1
        if cj.tick > 700:
            self.new_test()

    def new_test(self) -> None:
        o = self.owner
        L = o.lizard
        rng = L.rng
        num = rng.random() * L.ai.run_speed**0.5
        if o.proximity(self.start_pos) > 1:
            num *= 0.5
        if self.chain_jump:
            num *= 0.5
        num2 = lerp(14.0, 50.0, num)
        if L.grasps[0] is not None:
            num2 *= 0.75
        num2 *= lerp(1.0, max(0.0, min(1.0, L.health)), 0.5 + 0.5 * rng.random())
        ang = (45.0 * rng.random() ** 0.75 + 135.0 * rng.random() ** 2.0) * (
            -1.0 if rng.random() < 0.5 else 1.0
        )
        init_vel = deg_to_vec(ang) * num2
        start = self.room.middle_of(self.start_pos)
        self.current_jump = JumpInstruction(start, init_vel, num)
        self.px = self.lpx = start.x
        self.py = self.lpy = start.y
        self.vx, self.vy = init_vel.x, init_vel.y
        self.has_ventured_away_from_terrain = False
        if self.best_jump.is_default():
            self.best_jump = self.current_jump.copy()

    def destroy(self) -> None:
        self.slated_for_deletion = True


class JumpLight:
    """起跳时的一团光（CosmeticSprite）。原版构造函数不写 intensity 字段，所以它恒为 0，只影响 life_time。"""

    def __init__(self, pos: V2, lizard_graphics, intensity: float):
        self.life = 1.0
        self.last_life = 1.0
        self.life_time = lerp(4.0, 22.0, intensity**2.0)
        self.intensity = 0.0
        self.pos = pos
        self.last_pos = pos
        self.vel = V2()
        self.lizard = lizard_graphics
        self.slated_for_deletetion = False

    def update(self) -> None:
        self.last_life = self.life
        self.life -= 1.0 / self.life_time
        if self.last_life <= 0.0:
            self.slated_for_deletetion = True
        self.last_pos = self.pos
        self.pos = self.pos + self.vel

    def draw_data(self, ts: float) -> dict:
        """DrawSprites 的结果：三个圆（Futile_White，scale 1.0 = 16px）共用 pos；颜色是 lizard.effect_color。
        0 号用 LightSource 着色器、1/2 号 FlatLight；2 号无色（白）。"""
        p = vlerp(self.last_pos, self.pos, ts)
        num = lerp(self.last_life, self.life, ts)
        i = self.intensity
        num2 = lerp(20.0 + 10.0 * i, 40.0 + 30.0 * i, num) + lerp(50.0, 90.0, i) * math.sin(
            num**2.0 * math.pi
        )
        return {
            "x": p.x,
            "y": p.y,
            "scale": (num2 * 2.0 / 8.0, num2 / 8.0, num2 * lerp(0.4, 0.8, random.random()) / 8.0),
            "alpha": (
                inverse_lerp(0.0, 0.5, num) ** 0.5,
                num**2.0 * (0.4 + 0.4 * i),
                inverse_lerp(0.25, 1.0, num) ** 3.0 * i,
            ),
        }


class ShockWave:
    """起跳的冲击波环（CosmeticSprite，ShockWave 着色器）。"""

    def __init__(self, pos: V2, size: float, intensity: float, life_time: int):
        self.pos = pos
        self.last_pos = pos
        self.vel = V2()
        self.size = size
        self.intensity = intensity
        self.life_time = life_time
        self.life = 0.0
        self.last_life = 0.0
        self.slated_for_deletetion = False

    def update(self) -> None:
        self.last_pos = self.pos
        self.pos = self.pos + self.vel
        self.last_life = self.life
        self.life += 1.0 / self.life_time
        if self.last_life > 1.0:
            self.slated_for_deletetion = True

    def draw_data(self, ts: float) -> dict:
        """一个圆：scale 1.0 = 16px；color = (r, g, b) = (num^0.1, intensity, num)，ShockWave 着色器参数。"""
        p = vlerp(self.last_pos, self.pos, ts)
        num = min(1.0, lerp(self.last_life, self.life, ts))
        return {
            "x": p.x,
            "y": p.y,
            "scale": num**0.5 * self.size / 8.0,
            "color": (num**0.1, self.intensity, num),
        }


class LizardJumpModule:
    def __init__(self, lizard):
        self.lizard = lizard
        self.jump_finders: list[JumpFinder] = []
        self.act_on_jump: JumpFinder | None = None
        self.lizard_cell: PathingCell | None = None
        self.add_delay = 0
        self.jump_counter = 0
        self.spin = 0
        self.smoke = None
        self.charge_sound = None
        self.future_path: list[tuple[int, int]] = []
        self.lights: list[JumpLight] = []
        self.shock_waves: list[ShockWave] = []

    # 房间 = 地形

    @property
    def room(self):
        return self.lizard.terrain

    @property
    def view(self) -> _View:
        return _view(self.lizard.terrain, self.lizard.lizard_params)

    def proximity(self, tile) -> int:
        """AImap.getTerrainProximity。"""
        k = self.view.idx(tile)
        return -1 if k < 0 else self.view.prox[k]

    def dist_to_destination(self, tile) -> float:
        """pathFinder.GetDestination.Tile.FloatDist(tile)；没有目的地时当作很远。"""
        d = self.lizard.pather.destination
        return 1e9 if d is None else _float_dist(d, tile)

    def reset(self) -> None:
        """地形重建后丢掉旧的寻点和计划（寻路单元已换）。"""
        self.jump_finders.clear()
        self.act_on_jump = None
        self.lizard_cell = None

    @property
    def jump_to_point(self) -> V2:
        return self.room.middle_of(self.act_on_jump.best_jump.goal_cell.world_coordinate)

    @property
    def in_standard_run_mode(self) -> bool:
        a = self.lizard.animation
        return self.act_on_jump is None and a != Animation.PrepareToJump and a != Animation.Jumping

    @property
    def can_chain_jump(self) -> bool:
        return self.lizard.lizard_params.key == "cyan" and self.lizard.grasps[0] is None

    @property
    def no_run_behavior(self) -> bool:
        return (
            self.act_on_jump is not None
            and self.lizard.animation == Animation.Jumping
            and self.jump_counter < self.act_on_jump.best_jump.tick
        )

    # 每 tick

    def update(self) -> None:
        L = self.lizard
        if L.dead:
            return
        self._update_effects()
        cs = self.charge_sound
        if cs is not None:
            cs.alive = True
            cs.set_pos(L.body_chunks[0].pos)
            if L.consious and (L.animation == Animation.PrepareToJump or L.animation == Animation.Jumping):
                cs.volume = min(1.0, cs.volume + 1.0 / 9.0)
                cs.pitch = min(1.0, cs.pitch + 1.0 / 9.0)
            else:
                cs.volume = max(0.0, cs.volume - 1.0 / 9.0)
                cs.pitch = max(0.5, cs.pitch - 1.0 / 9.0)
                if cs.volume <= 0.0:
                    cs.alive = False
                    self.charge_sound = None
        if not L.consious and (L.animation == Animation.PrepareToJump or L.animation == Animation.Jumping):
            L.enter_animation(Animation.Standard, True)
        for i in range(len(self.jump_finders) - 1, -1, -1):
            if self.jump_finders[i].slated_for_deletion:
                del self.jump_finders[i]
            else:
                self.jump_finders[i].update()
        if L.animation == Animation.Jumping:
            self._jumping_update()
        elif self.in_standard_run_mode:
            self._running_update()
        a = self.act_on_jump
        if a is not None and L.animation != Animation.PrepareToJump and L.animation != Animation.Jumping:
            a.fade += 1
            if a.fade > 40:
                self.act_on_jump = None
        if self.smoke is not None and self.smoke.slated_for_deletetion:
            self.smoke = None

    def _update_effects(self) -> None:
        if self.smoke is not None:
            self.smoke.room = self.lizard.terrain
            self.smoke.update(self._physical_objects())
        for lst in (self.lights, self.shock_waves):
            for x in lst:
                x.update()
            lst[:] = [x for x in lst if not x.slated_for_deletetion]

    def _physical_objects(self) -> list:
        """烟雾被物体搅动要看的物体：房间里所有有身体节的东西（光标不算）。"""
        ctx = self.lizard.ctx
        objs = getattr(ctx, "creatures", None)
        if not objs:
            return [self.lizard]
        return [
            o for o in objs if getattr(o, "kind_key", None) != "cursor" and getattr(o, "body_chunks", None)
        ]

    def _jumping_update(self) -> None:
        L = self.lizard
        c = L.body_chunks
        gfx = L.graphics_module
        self.jump_counter += 1
        flag = False
        a = self.act_on_jump
        if a is None:
            flag = True
        else:
            bj = a.best_jump
            if self.smoke is not None and self.jump_counter < 70.0 * bj.power:
                self.smoke.emit_smoke(
                    c[1].pos,
                    c[1].vel + dir_vec(c[1].pos, c[2].pos) * 16.0,
                    gfx,
                    False,
                    (70.0 * bj.power - self.jump_counter) * 1.5,
                )
            if self.jump_counter > bj.tick + 5:
                v = self.view
                for ch in c:
                    k = v.idx(tile_xy(ch.pos))
                    if k >= 0 and v.accessible[k]:
                        c[0].vel = c[0].vel * 0.5
                        L.in_allowed_terrain_counter += 1
            else:
                L.in_allowed_terrain_counter = 0
                if self.jump_counter > bj.tick - 30 and a.landing_direction is not None:
                    c[0].vel = c[0].vel + a.landing_direction * 3.0
                    c[2].vel = c[2].vel - a.landing_direction * 3.0
                elif self.spin == 0:
                    k = lerp_map(self.jump_counter, 10.0, 60.0, 2.0, 0.0)
                    d = dir_vec(c[1].pos, self.jump_to_point)
                    c[0].vel = c[0].vel + d * k
                    c[2].vel = c[2].vel - d * k
                elif self.proximity(tile_xy(c[1].pos)) > 2:
                    normalized = (
                        perpendicular_vector(c[2].pos - c[1].pos) + perpendicular_vector(c[1].pos - c[0].pos)
                    ).normalized
                    vector = normalized * (self.spin * lerp_map(self.jump_counter, 20.0, 60.0, 3.0, 0.0))
                    c[0].vel = c[0].vel + vector
                    c[2].vel = c[2].vel - vector
                    gfx.head.vel = gfx.head.vel + normalized * (self.spin * 50.0)
                    n = len(gfx.tail)
                    for j in range(n):
                        gfx.tail[j].vel = gfx.tail[j].vel + normalized * (
                            self.spin * math.sin(inverse_lerp(0.0, n - 1, j) * math.pi) * 15.0
                        )
            for ch in c:
                if not dist_less(ch.pos, self.jump_to_point, 40.0):
                    continue
                if self.try_chain_jump(self.jump_to_point):
                    return
                if bj.grab_when_landing:
                    L.grip_point = self.jump_to_point
                flag = True
                break
        if not flag and self.jump_counter < a.best_jump.tick + 20:
            return
        L.in_allowed_terrain_counter = L.lizard_params.regain_footing_counter + 5
        if a is not None and a.best_jump.grab_when_landing:
            for ch in c:
                ch.vel = ch.vel * 0.5
        self.act_on_jump = None
        L.enter_animation(Animation.Standard, True)

    def _running_update(self) -> None:
        L = self.lizard
        T = self.room
        pf = L.pather
        tile = L.pos_tile
        for i in range(len(self.jump_finders) - 1, -1, -1):
            f = self.jump_finders[i]
            if not f.slated_for_deletion and tile == f.start_pos and f.beneficial_movement:
                self.initiate_jump(f, False)
        wc = tile
        self.future_path.clear()
        flag = False
        for _ in range(10):
            mc = pf.follow_path(wc, None, False)
            if mc is None:
                break
            wc = mc.destination_coord
            self.future_path.append(wc)
            for f in self.jump_finders:
                if f.start_pos == wc:
                    f.fade = 0
                    flag = True
        cell = pathing_cell_at(pf, tile)
        if cell is not FALLBACK_CELL:
            self.lizard_cell = cell
        if self.add_delay > 0:
            self.add_delay -= 1
        elif len(self.jump_finders) < (1 if flag else 4) and len(self.future_path) > 1:
            wc2 = self.future_path[L.rng.randrange(len(self.future_path))]
            if (
                _float_dist(wc2, tile) > 2.0
                and not T.narrow_space(wc2)
                and path_weight_comparison(self.lizard_cell, pathing_cell_at(pf, wc2))
            ):
                self.jump_finders.append(JumpFinder(self, wc2, False))

    def initiate_jump(self, jump: JumpFinder | None, chain_jump: bool) -> None:
        if jump is None or jump.best_jump.is_default() or jump.best_jump.goal_cell is None:
            return
        L = self.lizard
        self.act_on_jump = jump
        L.enter_animation(Animation.PrepareToJump, True)
        main = L.body_chunks[0]
        power = jump.best_jump.power
        if chain_jump:
            L.time_to_remain_in_animation = 10
        elif power > 0.75:
            L.time_to_remain_in_animation = 45
            self.charge_sound = sfx.play("Cyan_Lizard_Prepare_Powerful_Jump", main.pos, upkeep=True)
        elif power > 0.25:
            L.time_to_remain_in_animation = 30
            self.charge_sound = sfx.play("Cyan_Lizard_Prepare_Medium_Jump", main.pos, upkeep=True)
        else:
            L.time_to_remain_in_animation = 15
            self.charge_sound = sfx.play("Cyan_Lizard_Prepare_Small_Jump", main.pos, upkeep=True)
        goal = jump.best_jump.goal_cell.world_coordinate
        L.lounge_dir = dir_vec(main.pos, self.room.middle_of(goal))
        self.jump_counter = 0
        for f in self.jump_finders:
            f.destroy()
        if self.can_chain_jump and (self.act_on_jump.chain_jump or power > 0.25):
            self.jump_finders.append(JumpFinder(self, goal, True))

    def try_chain_jump(self, pos: V2) -> bool:
        if not self.can_chain_jump:
            return False
        L = self.lizard
        T = self.room
        c = L.body_chunks
        for f in self.jump_finders:
            if not f.chain_jump or not f.beneficial_movement:
                continue
            for ch in c:
                if dist_less(T.middle_of(f.start_pos), ch.pos, 40.0):
                    for k in c:
                        k.vel = V2()
                    L.in_allowed_terrain_counter = 1000
                    c[1].pos = T.middle_of(f.start_pos)
                    self.initiate_jump(f, True)
                    return True
        return False

    def jump(self) -> None:
        """Lizard.EnterAnimation(Jumping) 里调用：把身体摆到起跳点、给初速，放烟和光。"""
        a = self.act_on_jump
        if a is None or a.best_jump.is_default():
            return
        L = self.lizard
        T = self.room
        c = L.body_chunks
        gfx = L.graphics_module
        rng = L.rng
        bj = a.best_jump
        main = c[0]
        if bj.power > 0.75:
            sfx.play("Cyan_Lizard_Powerful_Jump", main.pos)
        elif bj.power > 0.25:
            sfx.play("Cyan_Lizard_Medium_Jump", main.pos)
        else:
            sfx.play("Cyan_Lizard_Small_Jump", main.pos)
        vector = T.middle_of(a.start_pos)
        n = bj.init_vel.normalized
        for i in range(len(c)):
            c[i].pos = vector + n * ((1 - i) * 8.0)
        shift = vector + bj.init_vel - c[1].pos
        for ch in c:
            ch.pos = ch.pos + shift
            ch.vel = bj.init_vel
        L.movement_animation = None
        L.in_allowed_terrain_counter = 0
        self.jump_counter = 0
        self.add_delay = 20
        L.grip_point = None
        if bj.tick > 25 and dot((c[1].pos - c[0].pos).normalized, n) < lerp(
            -0.9, -0.1, ((L.ai.excitement + L.ai.run_speed) / 2.0) ** 0.5
        ):
            self.spin = 1 if bj.init_vel.x >= 0.0 else -1
        else:
            self.spin = 0
        if self.smoke is None:
            from .smoke import CyanLizardSmoke

            self.smoke = CyanLizardSmoke(T, rng)
        for _ in range(7):
            self.smoke.emit_smoke(
                vector,
                -bj.init_vel * (rng.random() * 0.5) + rnv(rng) * lerp(6.0, 23.0, bj.power),
                gfx,
                True,
                lerp(30.0, 140.0, bj.power),
            )
        add_bubble = getattr(L, "add_lizard_bubble", None)
        if add_bubble is not None:
            for _ in range(int(bj.power * 10.0 * rng.random()) + 1):
                add_bubble(1.0, 0.0, bj.power * 10.0)
        self.lights.append(JumpLight(vector - n * 10.0, gfx, bj.power))
        self.shock_waves.append(
            ShockWave(vector - n * 15.0, lerp(40.0, 120.0, bj.power), 0.07, 6 + int(bj.power * 4.0))
        )
