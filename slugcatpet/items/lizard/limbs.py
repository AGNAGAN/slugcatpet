"""蜥蜴的图形肢体：BodyPart、GenericBodyPart、TailSegment、Limb、LizardLimb。

owner 是 LizardGraphics，owner.owner 是 Lizard；地形查询走 owner.owner.terrain。
"""

from __future__ import annotations

import math

from .physics import TILE, fdir, solid_cache, tile_xy
from .rw import (
    EIGHT_DIRECTIONS_AND_ZERO,
    V2,
    aim_from_one_vector_to_another,
    clamp,
    deg_to_vec,
    dir_vec,
    dist_less,
    dist_no_sqrt,
    distance,
    lerp,
    perpendicular_vector,
    rotate_around_origo,
    vlerp,
)

_FLOOR_NONE = -100000.0
# 掩码 -> 置位的邻格序号（按 EIGHT_DIRECTIONS_AND_ZERO 的顺序）
_MASK_BITS = [tuple(k for k in range(9) if (m >> k) & 1) for m in range(512)]


class BodyPart:
    def __init__(self, owner):
        self.owner = owner
        self.pos = V2()
        self.last_pos = V2()
        self.vel = V2()
        self.rad = 0.0
        self.surface_fric = 0.0
        self.air_friction = 0.0
        self.terrain_contact = False
        self.body_part_array_index = -1

    def update(self) -> None:
        pass

    def reset(self, reset_point: V2) -> None:
        self.pos = reset_point + deg_to_vec(self.owner.owner.rng.random() * 360.0)
        self.last_pos = self.pos
        self.vel = V2()

    def connect_to_point(
        self,
        pnt: V2,
        connection_rad: float,
        push: bool,
        elastic_movement: float,
        host_vel: V2,
        adapt_vel: float,
        exaggerate_vel: float,
    ) -> None:
        px, py = self.pos.x, self.pos.y
        vx, vy = self.vel.x, self.vel.y
        nx, ny = pnt.x, pnt.y
        hx, hy = host_vel.x, host_vel.y
        if elastic_movement > 0.0:
            ux, uy = fdir(px, py, nx, ny)
            k = math.hypot(px - nx, py - ny) * elastic_movement
            vx = vx + ux * k
            vy = vy + uy * k
        vx = vx + hx * exaggerate_vel
        vy = vy + hy * exaggerate_vel
        d = math.hypot(px - nx, py - ny)
        if push or not d < connection_rad:
            ux, uy = fdir(px, py, nx, ny)
            k = connection_rad - d
            ux = ux * k
            uy = uy * k
            px = px - ux
            py = py - uy
            vx = vx - ux
            vy = vy - uy
            self.pos = V2(px, py)
        vx = vx - hx
        vy = vy - hy
        vx = vx * (1.0 - adapt_vel)
        vy = vy * (1.0 - adapt_vel)
        self.vel = V2(vx + hx, vy + hy)

    def push_from_point(self, pnt: V2, push_rad: float, elasticity: float) -> None:
        if dist_less(self.pos, pnt, push_rad):
            d = distance(self.pos, pnt)
            v = dir_vec(self.pos, pnt) * ((push_rad - d) * elasticity)
            self.pos = self.pos - v
            self.vel = self.vel - v

    def push_out_of_terrain(self, terrain, base_point: V2) -> None:
        """只有实心格会推开身体部件；其余地形（斜坡、曲面）这里不存在。"""
        self.terrain_contact = False
        W, H, grid, masks = solid_cache(terrain)
        pos = self.pos
        fl = math.floor
        px, py = pos.x, pos.y
        tx0, ty0 = fl(px / TILE), fl(py / TILE)
        i0, j0 = tx0 + 1, ty0 + 1
        w1, h1 = W - 1, H - 1
        mask = masks[i0 + j0 * W] if 0 <= i0 <= w1 and 0 <= j0 <= h1 else 0x1FF
        if not mask:
            return
        rad = self.rad
        sf = self.surface_fric
        lx, ly = self.last_pos.x, self.last_pos.y
        vx, vy = self.vel.x, self.vel.y

        def S(tx, ty):
            i = tx + 1
            j = ty + 1
            i = 0 if i < 0 else (w1 if i > w1 else i)
            j = 0 if j < 0 else (h1 if j > h1 else j)
            return grid[i + j * W]

        offs = EIGHT_DIRECTIONS_AND_ZERO
        ks = _MASK_BITS[mask]
        n = 0
        while n < len(ks):
            k = ks[n]
            n += 1
            tx, ty = tx0 + offs[k][0], ty0 + offs[k][1]
            cx, cy = tx * TILE + TILE / 2, ty * TILE + TILE / 2
            in_y = cy - 10.0 <= py <= cy + 10.0
            in_x = cx - 10.0 <= px <= cx + 10.0
            num = 0.0
            num2 = 0.0
            if in_y:
                if lx < cx:
                    if px > cx - 10.0 - rad and not S(tx - 1, ty):
                        num = cx - 10.0 - rad
                elif px < cx + 10.0 + rad and not S(tx + 1, ty):
                    num = cx + 10.0 + rad
            if in_x:
                if ly < cy:
                    if py > cy - 10.0 - rad and not S(tx, ty - 1):
                        num2 = cy - 10.0 - rad
                elif py < cy + 10.0 + rad and not S(tx, ty + 1):
                    num2 = cy + 10.0 + rad
            if abs(px - num) < abs(py - num2) and num != 0.0:
                px = num
                vx = 0.0
                vy = vy * sf
            elif num2 != 0.0:
                py = num2
                vy = 0.0
                vx = vx * sf
            else:
                qx = cx - 10.0 if px < cx - 10.0 else (cx + 10.0 if px > cx + 10.0 else px)
                qy = cy - 10.0 if py < cy - 10.0 else (cy + 10.0 if py > cy + 10.0 else py)
                d2 = (px - qx) ** 2 + (py - qy) ** 2
                if not d2 < rad * rad:
                    continue
                d = math.sqrt(d2)
                ex, ey = qx - px, qy - py
                if ex == 0.0 and ey == 0.0:
                    ux, uy = 0.0, 1.0
                else:
                    m = math.hypot(ex, ey)
                    ux, uy = (ex / m, ey / m) if m > 1e-5 else (0.0, 0.0)
                kk = rad - d
                vx = vx * sf
                vy = vy * sf
                px = px - ux * kk
                py = py - uy * kk
                vx = vx - ux * kk
                vy = vy - uy * kk
            self.terrain_contact = True
            tx0, ty0 = fl(px / TILE), fl(py / TILE)
            i0, j0 = tx0 + 1, ty0 + 1
            mask = masks[i0 + j0 * W] if 0 <= i0 <= w1 and 0 <= j0 <= h1 else 0x1FF
            ks = tuple(b for b in _MASK_BITS[mask] if b > k)
            n = 0
        self.pos = V2(px, py)
        self.vel = V2(vx, vy)
        if S(fl(px / TILE), fl(py / TILE)):
            self._escape_solid(terrain.solid, base_point)

    def _escape_solid(self, solid, base_point: V2) -> None:
        """整个部件陷进实心格（高速甩进墙角）时，沿连接点方向退回到第一个空格；原版房间不会出现这种深度。"""
        p = self.pos
        for k in range(1, 9):
            q = vlerp(p, base_point, k / 8.0)
            if not solid(tile_xy(q)):
                self.pos = q
                self.vel = V2()
                return
        self.pos = base_point
        self.vel = V2()


class GenericBodyPart(BodyPart):
    def __init__(self, owner, rd: float, sf_fric: float, a_fric: float, con):
        super().__init__(owner)
        self.rad = rd
        self.connection = con
        self.surface_fric = sf_fric
        self.air_friction = a_fric
        self.reset(con.pos)

    def update(self) -> None:
        self.last_pos = pos = self.pos
        vel = self.vel
        self.pos = V2(pos.x + vel.x, pos.y + vel.y)
        self.vel = V2(vel.x * self.air_friction, vel.y * self.air_friction)
        self.push_out_of_terrain(self.owner.owner.terrain, self.connection.pos)


class TailSegment(BodyPart):
    def __init__(self, owner, rd, cn_rd, cn_seg, sf_fric, a_fric, affect_previous, pull_in_previous_position):
        super().__init__(owner)
        self.rad = rd
        self.connection_rad = cn_rd
        self.surface_fric = sf_fric
        self.air_friction = a_fric
        self.connected_segment: TailSegment | None = cn_seg
        self.affect_previous = affect_previous
        self.pull_in_previous_position = pull_in_previous_position
        self.connected_point: V2 | None = None
        self.stretched = 0.0
        self.reset(owner.owner.body_chunks[1].pos)

    @property
    def stretched_rad(self) -> float:
        return self.rad * self.stretched

    def update(self) -> None:
        self.last_pos = pos = self.pos
        vel = self.vel
        af = self.air_friction
        px, py = pos.x + vel.x, pos.y + vel.y
        vx, vy = vel.x * af, vel.y * af
        self.stretched = 1.0
        seg = self.connected_segment
        crad = self.connection_rad
        if seg is not None:
            sp = seg.pos
            d = math.hypot(px - sp.x, py - sp.y)
            if not d < crad:
                ux, uy = fdir(px, py, sp.x, sp.y)
                k2 = (crad - d) * (1.0 - self.affect_previous)
                k3 = (crad - d) * self.affect_previous
                px = px - ux * k2
                py = py - uy * k2
                vx = vx - ux * k2
                vy = vy - uy * k2
                if self.pull_in_previous_position:
                    seg.pos = V2(sp.x + ux * k3, sp.y + uy * k3)
                seg.vel = V2(seg.vel.x + ux * k3, seg.vel.y + uy * k3)
                self.stretched = clamp((crad / (d * 0.5) + 2.0) / 3.0, 0.2, 1.0)
            base = seg.pos
        elif self.connected_point is not None:
            cp = self.connected_point
            d = math.hypot(px - cp.x, py - cp.y)
            if not d < crad:
                ux, uy = fdir(px, py, cp.x, cp.y)
                k = crad - d
                ux = ux * k
                uy = uy * k
                px = px - ux
                py = py - uy
                vx = vx - ux
                vy = vy - uy
                self.stretched = clamp((crad / (d * 0.5) + 2.0) / 3.0, 0.2, 1.0)
            base = cp
        else:
            base = None
        self.pos = V2(px, py)
        self.vel = V2(vx, vy)
        if base is not None:
            self.push_out_of_terrain(self.owner.owner.terrain, base)


class Mode:
    """Limb.Mode。"""

    HuntRelativePosition = "HuntRelativePosition"
    HuntAbsolutePosition = "HuntAbsolutePosition"
    Retracted = "Retracted"
    Dangle = "Dangle"


class Limb(BodyPart):
    def __init__(self, owner, connection, num, rad, sf_fric, a_fric, default_hunt_speed, default_quickness):
        super().__init__(owner)
        self.rad = rad
        self.connection = connection
        self.surface_fric = sf_fric
        self.air_friction = a_fric
        self.limb_number = num
        self.mode = Mode.HuntRelativePosition
        self.default_hunt_speed = default_hunt_speed
        self.hunt_speed = default_hunt_speed
        self.default_quickness = default_quickness
        self.quickness = default_quickness
        self.relative_hunt_pos = V2()
        self.reached_snap_position = False
        self.retract = False
        self.push_out_of_terrain_enabled = True
        self.reset(connection.pos)
        self.absolute_hunt_pos = self.pos

    @property
    def over_lapping_hunt_pos(self) -> bool:
        if self.reached_snap_position:
            return True
        return dist_less(self.pos, self.absolute_hunt_pos, self.rad + 1.0)

    def update(self) -> None:
        self.last_pos = self.pos
        conn = self.connection
        if self.retract and self.mode != Mode.Retracted:
            self.mode = Mode.HuntAbsolutePosition
            self.absolute_hunt_pos = conn.pos
            if dist_less(self.absolute_hunt_pos, self.pos, self.hunt_speed):
                self.mode = Mode.Retracted
        if self.mode == Mode.HuntRelativePosition:
            self.absolute_hunt_pos = conn.pos + rotate_around_origo(
                self.relative_hunt_pos, aim_from_one_vector_to_another(conn.rotation_chunk.pos, conn.pos)
            )
        if self.mode == Mode.HuntRelativePosition or self.mode == Mode.HuntAbsolutePosition:
            ah = self.absolute_hunt_pos
            pos = self.pos
            if math.hypot(ah.x - pos.x, ah.y - pos.y) < self.hunt_speed:
                self.vel = V2(ah.x - pos.x, ah.y - pos.y)
                self.reached_snap_position = True
            else:
                ux, uy = fdir(pos.x, pos.y, ah.x, ah.y)
                t = clamp(self.quickness, 0.0, 1.0)
                vel = self.vel
                tx = ux * self.hunt_speed
                ty = uy * self.hunt_speed
                self.vel = V2(vel.x + (tx - vel.x) * t, vel.y + (ty - vel.y) * t)
                self.reached_snap_position = False
        elif self.mode == Mode.Retracted:
            self.vel = conn.vel
            self.pos = conn.pos
            self.reached_snap_position = True
        elif self.mode == Mode.Dangle:
            self.reached_snap_position = False
        self.quickness = self.default_quickness
        self.hunt_speed = self.default_hunt_speed
        if self.mode != Mode.Retracted:
            pos, vel = self.pos, self.vel
            self.pos = V2(pos.x + vel.x, pos.y + vel.y)
            if self.mode == Mode.HuntRelativePosition:
                self.pos = self.pos + conn.vel
            self.vel = V2(vel.x * self.air_friction, vel.y * self.air_friction)
            if self.push_out_of_terrain_enabled:
                self.push_out_of_terrain(self.owner.owner.terrain, conn.pos)

    def find_grip(
        self,
        terrain,
        attached_pos: V2,
        search_from_pos: V2,
        maximum_radius_from_attached_pos: float,
        goal_pos: V2,
        forbidden_x_dirs: int,
        forbidden_y_dirs: int,
    ) -> None:
        """实心格的边、横杆、竖杆上找离 goal_pos 最近、且在 attached_pos 够得着的抓点。"""
        mr = maximum_radius_from_attached_pos
        if not dist_less(attached_pos, search_from_pos, mr):
            search_from_pos = attached_pos + dir_vec(attached_pos, search_from_pos) * (mr - 1.0)
        if not dist_less(attached_pos, goal_pos, mr):
            goal_pos = attached_pos + dir_vec(attached_pos, goal_pos) * mr
        tx0, ty0 = tile_xy(search_from_pos)
        best = V2(_FLOOR_NONE, _FLOOR_NONE)
        best_d = dist_no_sqrt(goal_pos, best)
        solid = terrain.solid
        gx, gy = goal_pos.x, goal_pos.y
        for dx, dy in EIGHT_DIRECTIONS_AND_ZERO:
            if dx == forbidden_x_dirs or dy == forbidden_y_dirs:
                continue
            t = (tx0 + dx, ty0 + dy)
            is_solid = solid(t)
            hb = terrain.horizontal_beam(t)
            vb = terrain.vertical_beam(t)
            if not (is_solid or hb or vb):
                continue
            mid = terrain.middle_of(t)
            vx3 = clamp(gx, mid.x - 10.0, mid.x + 10.0)
            vy3 = clamp(gy, mid.y - 10.0, mid.y + 10.0)
            if is_solid:
                if dx != 0 and not solid((t[0] - dx, t[1])):
                    vx3 = mid.x - dx * 10.0
                if dy != 0 and not solid((t[0], t[1] - dy)):
                    vy3 = mid.y - dy * 10.0
                d = (gx - vx3) ** 2 + (gy - vy3) ** 2
                if d < best_d and dist_less(attached_pos, V2(vx3, vy3), mr):
                    best = V2(vx3, vy3)
                    best_d = d
            if hb:
                vx3 = clamp(gx, mid.x - 10.0, mid.x + 10.0)
                d = (gx - vx3) ** 2 + (gy - mid.y) ** 2
                if d < best_d and dist_less(attached_pos, V2(vx3, mid.y), mr):
                    best = V2(vx3, mid.y)
                    best_d = d
            if vb:
                vy3 = clamp(gy, mid.y - 10.0, mid.y + 10.0)
                d = (gx - mid.x) ** 2 + (gy - vy3) ** 2
                if d < best_d and dist_less(attached_pos, V2(mid.x, vy3), mr):
                    best = V2(mid.x, vy3)
                    best_d = d
        if best.x != _FLOOR_NONE and best.y != _FLOOR_NONE:
            self.mode = Mode.HuntAbsolutePosition
            self.absolute_hunt_pos = best
            self.grabbed_terrain()

    def grabbed_terrain(self) -> None:
        pass


class LizardLimb(Limb):
    def __init__(
        self, owner, connection_chunk, num, rad, sf_fric, a_fric, hunt_speed, quickness, other_limb_in_pair
    ):
        super().__init__(owner, connection_chunk, num, rad, sf_fric, a_fric, hunt_speed, quickness)
        self.other_limb_in_pair: LizardLimb | None = other_limb_in_pair
        self.mode = Mode.Retracted
        self.reaching_for_terrain = False
        self.grip_counter = 0
        self.currently_disabled = False
        self.grab_pos = V2()
        self.flip = 0.0
        self.extra_long_step = False
        self.joint_dist = 25.0 * ((owner.lizard.lizard_params.body_size_fac + 1.0) / 2.0)

    @property
    def health(self) -> float:
        if not self.owner.lizard.consious:
            return 0.0
        return self.owner.lizard.limb_health[self.limb_number]

    @property
    def step_length(self) -> float:
        return lerp(-0.5, 0.5, self.owner.lizard.lizard_params.step_length * self.health)

    def reset(self, reset_point: V2) -> None:
        self.retract = True
        super().reset(reset_point)

    def update(self) -> None:
        gfx = self.owner
        lizard = gfx.lizard
        p = lizard.lizard_params
        rng = lizard.rng
        health = self.health
        conn = self.connection
        if (not self.currently_disabled and rng.random() > health and rng.random() < 0.02) or lizard.stunned:
            self.currently_disabled = True
        elif (self.currently_disabled and rng.random() < health and rng.random() < 0.02) or health == 1.0:
            self.currently_disabled = False
        self.hunt_speed = p.limb_speed * lerp(0.5, 1.0, health)
        self.quickness = lerp(0.1, p.limb_quickness, health)
        if self.currently_disabled:
            self.mode = Mode.Dangle
            self.vel = V2(self.vel.x, self.vel.y - 0.9)
            self.retract = False
            self.grip_counter = 0
            self.reaching_for_terrain = False
        else:
            if self.mode == Mode.HuntAbsolutePosition:
                self.hunt_speed = self.default_hunt_speed + conn.vel.magnitude
            cp = conn.pos
            cpx, cpy = cp.x, cp.y
            rp = conn.rotation_chunk.pos
            ax, ay = fdir(rp.x, rp.y, cpx, cpy)
            if conn.index == 2:
                ax = ax * -1.0
                ay = ay * -1.0
            aim = lizard.limbs_aim_for
            bx, by = fdir(cpx, cpy, aim.x, aim.y)
            ax = ax + (bx - ax) * 0.4
            ay = ay + (by - ay) * 0.4
            m = math.hypot(ax, ay)
            if m > 1e-5:
                ax, ay = ax / m, ay / m
            else:
                ax, ay = 0.0, 0.0
            m = math.hypot(ax, ay)
            nx, ny = (ax / m, ay / m) if m > 1e-5 else (0.0, 0.0)
            l1x, l1y = cpx - ny, cpy + nx
            pos = self.pos
            num = ((cpy - l1y) * pos.x - (cpx - l1x) * pos.y + cpx * l1y - cpy * l1x) / math.sqrt(
                (cpy - l1y) ** 2 + (cpx - l1x) ** 2
            )
            a = V2(ax, ay)
            if not self.reaching_for_terrain:
                self.mode = Mode.HuntAbsolutePosition
                t = clamp(p.lift_feet, 0.0, 1.0)
                k = self.joint_dist + 1.0
                self.absolute_hunt_pos = V2(
                    pos.x + (cpx - pos.x) * t + ax * k, pos.y + (cpy - pos.y) * t + ay * k
                )
                if self.extra_long_step:
                    if self.other_limb_in_pair.currently_disabled:
                        self.extra_long_step = False
                    if self.other_limb_in_pair.grip_counter > p.limb_grip_delay:
                        self.extra_long_step = False
                if not self.extra_long_step and num < self.joint_dist * (
                    0.0 - lerp(-0.5, 0.5, p.step_length * health)
                ):
                    self.reaching_for_terrain = True
            else:
                if not self.over_lapping_hunt_pos:
                    a = a + perpendicular_vector(a) * ((6.0 - 12.0 * (self.limb_number % 2)) * 0.2)
                    a = V2(a.x, a.y - 0.3 * p.feet_down)
                    a = V2(
                        a.x
                        + (-1.0 if self.limb_number % 2 == 0 else 1.0) * p.leg_pair_displacement * self.flip,
                        a.y,
                    )
                    self.find_grip(
                        lizard.terrain, conn.pos, conn.pos, self.joint_dist - 1.0, conn.pos + a * 50.0, 2, 2
                    )
                else:
                    if (
                        num > self.joint_dist * -0.5 * (p.step_length + 0.1)
                        and not dist_less(self.pos, conn.pos, self.joint_dist - 1.0)
                        and not dist_less(self.absolute_hunt_pos, conn.pos, self.joint_dist)
                    ):
                        self.extra_long_step = (
                            self.other_limb_in_pair is not None
                            and p.smoothen_leg_movement
                            and self.other_limb_in_pair.grip_counter < 1
                        )
                        self.reaching_for_terrain = False
                    if lizard.ai.run_speed > 0.1 and p.smoothen_leg_movement:
                        flag = True
                        for other in gfx.limbs:
                            if other.grip_counter > self.grip_counter or other.grip_counter == 0:
                                flag = False
                                break
                        if flag:
                            self.reaching_for_terrain = False
                if self.mode == Mode.Dangle:
                    self.reaching_for_terrain = False
        if self.mode == Mode.Dangle:
            off = rotate_around_origo(
                V2(30.0 - 60.0 * (self.limb_number % 2), 10.0),
                aim_from_one_vector_to_another(conn.rotation_chunk.pos, conn.pos),
            )
            self.vel = self.vel + dir_vec(self.pos, conn.pos + off) * 0.6
        if self.retract and self.reached_snap_position:
            self.mode = Mode.HuntAbsolutePosition
            self.reaching_for_terrain = False
            self.retract = False
        other = self.other_limb_in_pair
        if other is not None and dist_less(self.pos, other.pos, self.rad * 3.0):
            d = distance(self.pos, other.pos)
            v = dir_vec(self.pos, other.pos) * ((self.rad * 3.0 - d) * 0.5)
            self.vel = self.vel - v
            other.vel = other.vel + v
        super().update()
        self.connect_to_point(conn.pos, self.joint_dist, False, 0.0, conn.vel, 0.0, 0.0)
        if (
            self.mode == Mode.HuntAbsolutePosition
            and self.reaching_for_terrain
            and (self.reached_snap_position or (self.over_lapping_hunt_pos and self.terrain_contact))
        ):
            self.grip_counter += 1
        else:
            self.grip_counter = 0

    def grabbed_terrain(self) -> None:
        self.grab_pos = self.absolute_hunt_pos
        self.reaching_for_terrain = True
