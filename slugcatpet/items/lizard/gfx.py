"""LizardGraphics 的模拟部分：个体差异、肢体 / 尾巴 / 头的构造与每 tick 更新。

绘制（贴图、颜色、脊线位置）在 draw.py，读这里的字段。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .limbs import GenericBodyPart, LizardLimb, TailSegment
from .physics import Animation, fdir, vslerp
from .rw import (
    V2,
    aim_from_one_vector_to_another,
    clamp,
    clamped_random_variation,
    color_lerp,
    deg_to_vec,
    dir_vec,
    dist_less,
    distance,
    hsl2rgb,
    inverse_lerp,
    lerp,
    move_towards,
    rnv,
    sign,
    vlerp,
)


def _normalized(x: float, y: float) -> tuple[float, float]:
    m = math.hypot(x, y)
    return (x / m, y / m) if m > 1e-5 else (0.0, 0.0)


@dataclass
class IndividualVariations:
    head_size: float
    fatness: float
    tail_length: float
    tail_fatness: float
    tail_color: float


class CreatureLooker:
    """视线目标的挑选。tracker 为空时只剩"随机看向某处"。"""

    def __init__(
        self, looking_at_creatures, tracker, creature, chance_to_look_at_nothing, frames_between_focus_change
    ):
        self.looking_at_creatures = looking_at_creatures
        self.tracker = tracker
        self.creature = creature
        self.chance_to_look_at_nothing = chance_to_look_at_nothing
        self.frames_between_focus_change = frames_between_focus_change
        self.look_creature = None
        self.look_focus_delay = 0

    def update(self) -> None:
        rng = self.creature.rng
        if self.look_focus_delay > 0:
            self.look_focus_delay -= 1
        forced = self.looking_at_creatures.forced_look_creature()
        if forced is not None:
            self.look_creature = forced
        elif self.look_focus_delay < 1 and rng.random() < 1.0 / self.frames_between_focus_change:
            self.look_focus_delay = self.frames_between_focus_change
            if rng.random() > self.chance_to_look_at_nothing:
                self.reevaluate_look_object(None, 0.0)
                return
            self.look_creature = None
            self.looking_at_creatures.look_at_nothing()

    def reevaluate_look_object(self, favor_this_creature, bonus: float) -> None:
        rng = self.creature.rng
        ai = self.creature.ai
        self.look_creature = None
        best = 0.0
        flag = rng.random() < 0.5 and favor_this_creature is None
        for i in range(self.tracker.creatures_count):
            rep = self.tracker.get_rep(i)
            rel = ai.creature_relationship(rep)
            body_size = rep.represented_creature.body_size
            score = 1.0 + lerp(body_size, 1.0, 0.5) * rel.intensity * rep.estimated_chance_of_finding * lerp(
                rep.represented_creature.scaryness, 1.0, 0.7
            )
            if flag:
                score += rng.random()
            realized = rep.represented_creature.realized_creature
            if rep.visual_contact and realized is not None:
                score *= 1.0 + realized.main_body_chunk.vel.magnitude
            gx, gy = rep.best_guess_for_position().tile
            cx, cy = self.creature.pos_tile
            score /= lerp(math.hypot(gx - cx, gy - cy), 1.0, 0.6)
            if rep is favor_this_creature:
                score *= bonus
            if rel.type == "Ignores":
                score /= 2.0
            score = self.looking_at_creatures.creature_interest_bonus(rep, score)
            for g in self.creature.grasps:
                if g is not None and g.grabbed is realized:
                    score = -3.4e38
                    break
            if score > best:
                best = score
                self.look_creature = rep

    def look_at_nothing(self) -> None:
        self.look_focus_delay = self.frames_between_focus_change
        self.look_creature = None
        self.looking_at_creatures.look_at_nothing()


WHITE_PICKUP = (1.0, 1.0, 1.0)


class LizardGraphics:
    """lizard 的图形模块。draw_positions[i][0] 是本 tick、[i][1] 是上一 tick 的三节身体位置。"""

    def __init__(self, lizard, rng: random.Random):
        self.lizard = lizard
        self.owner = lizard
        p = lizard.lizard_params
        self.i_vars = self.generate_ivars(rng)
        self.limbs: list[LizardLimb] = []
        self.legs_grabbing = 0
        self.front_legs_grabbing = 0
        self.hind_legs_grabbing = 0
        self.no_grip_counter = 0
        self.front_bob = 0.0
        self.hind_bob = 0.0
        self.depth_rotation = 0.0
        self.last_depth_rotation = 0.0
        self.head_depth_rotation = 0.0
        self.last_head_depth_rotation = 0.0
        self.white_flicker = 0
        self.flicker = 0
        self.flicker_color = 0.0
        self.show_dominance = 0.0
        self.head_color_setter = 0.0
        # 白蜥蜴伪装：amount 0 现形 .. 1 完全伪装；-1 为还没取过色
        self.white_camo_amount = -1.0
        self.white_camo_drag = 1.0
        self.white_camo_color = WHITE_PICKUP
        self.white_pickup_color = WHITE_PICKUP
        self.white_glitch_fit = 0
        self.white_dominance_hue = 0.0
        self.look_pos = V2()
        self.voice_visualization = 0.0
        self.last_voice_visualization = 0.0
        self.voice_visualization_intensity = 0.0
        self.last_voice_visualization_intensity = 0.0
        self.every_second_draw = False
        self._stunned_last_update = False
        self._rotate_while_stunned = False

        for i in range(4):
            num = 2 if i >= 2 else 0
            self.limbs.append(
                LizardLimb(
                    self,
                    lizard.body_chunks[num],
                    i,
                    2.5,
                    0.7,
                    0.99,
                    p.limb_speed,
                    p.limb_quickness,
                    self.limbs[i - 1] if i % 2 == 1 else None,
                )
            )
        self.tail: list[TailSegment] = []
        for j in range(p.tail_segments):
            num2 = 8.0 * p.body_size_fac
            num2 *= (p.tail_segments - j) / p.tail_segments
            num3 = ((8.0 if j > 0 else 16.0) + num2) / 2.0
            num3 *= p.tail_length_factor * self.i_vars.tail_length
            self.tail.append(
                TailSegment(self, num2, num3, self.tail[j - 1] if j > 0 else None, 0.85, 1.0, 0.4, False)
            )
        if p.key == "cyan":
            n = len(self.tail)
            for k, seg in enumerate(self.tail):
                t = inverse_lerp(0.0, n - 1, k)
                seg.rad += math.sin((t**0.7) * math.pi) * 2.5
                seg.rad *= 1.0 - math.sin(inverse_lerp(0.0, 0.4, t) * math.pi) * 0.5
        self.tail_length = sum(t.connection_rad for t in self.tail)
        self.head = GenericBodyPart(self, 6.0 * p.head_size, 0.5, 0.99, lizard.body_chunks[0])
        self.head_connection_rad = 11.0 * p.head_size
        self.tongue: list[GenericBodyPart] = (
            [GenericBodyPart(self, 1.0, 1.0, 0.9, lizard.body_chunks[0]) for _ in range(p.tongue_segments)]
            if lizard.tongue is not None
            else []
        )
        self.body_length = self.head_connection_rad * 0.5 + sum(
            c.distance for c in lizard.body_chunk_connections
        )
        self.draw_positions = [[V2(), V2()] for _ in lizard.body_chunks]
        self.body_parts = [*self.limbs, *self.tail, self.head]
        for i, bp in enumerate(self.body_parts):
            bp.body_part_array_index = i

        try:
            from .cosmetics import build_cosmetics
        except ImportError:
            self.cosmetics = []
        else:
            self.cosmetics = build_cosmetics(self, rng)
        self.blink = rng.random()
        self.last_blink = self.blink
        self.breath = rng.random()
        self.last_breath = self.breath
        self.tail_direction = deg_to_vec(rng.random() * 360.0) * rng.random()
        self.creature_looker = CreatureLooker(
            self, lizard.ai.tracker, lizard, 0.3, p.frames_between_look_focus_change
        )

    def generate_ivars(self, rng: random.Random) -> IndividualVariations:
        key = self.lizard.lizard_params.key
        head_size = clamped_random_variation(rng, 0.5, 0.07, 0.5) * 2.0
        if rng.random() < 0.5:
            head_size = 1.0
        num = clamped_random_variation(rng, 0.5, 0.12, 0.5) * 2.0
        num2 = clamped_random_variation(rng, 0.5, 0.2, 0.3) * 2.0
        num3 = clamped_random_variation(rng, 0.45, 0.1, 0.3) * 2.0
        tail_color = 0.0
        if key != "white" and rng.random() > 0.5:
            tail_color = rng.random()
        if key == "red":
            num = min(1.0, num)
            num3 = min(1.0, num3)
        return IndividualVariations(head_size, num, num2, num3, tail_color)

    # 供 draw 与 cosmetics 使用

    @property
    def effect_color(self):
        return self.lizard.effect_color

    @property
    def body_and_tail_length(self) -> float:
        return self.body_length + self.tail_length

    @property
    def bubble_intensity(self) -> float:
        return self.lizard.bubble_intensity * 0.5 + self.voice_visualization_intensity

    def body_chunk_display_rad(self, index: int) -> float:
        return self.lizard.body_chunks[index].rad * (1.0 / self.lizard.lizard_params.body_rad_fac)

    def head_rotation(self, time_stacker: float) -> float:
        dp = self.draw_positions
        num = aim_from_one_vector_to_another(
            vlerp(dp[0][1], dp[0][0], time_stacker), vlerp(self.head.last_pos, self.head.pos, time_stacker)
        )
        num2 = lerp(self.last_head_depth_rotation, self.head_depth_rotation, time_stacker)
        num3 = clamp(lerp(self.lizard.last_jaw_open, self.lizard.jaw_open, time_stacker), 0.0, 1.0)
        p = self.lizard.lizard_params
        return num + p.jaw_open_angle * (1.0 - p.jaw_open_lower_jaw_fac) * num3 * num2

    # ILookingAtCreatures

    def creature_interest_bonus(self, crit, score: float) -> float:
        L = self.lizard
        c0, c1 = L.body_chunks[0].pos, L.body_chunks[1].pos
        gx, gy = crit.best_guess_for_position().tile
        target = L.terrain.middle_of((gx, gy))
        value = (c0 - c1).normalized
        t = (target - c1).normalized
        v = value.x * t.x + value.y * t.y
        return score * lerp(clamp(v, 0.1, 1.0), 1.0, 0.5)

    def forced_look_creature(self):
        return self.lizard.ai.focus_creature

    def look_at_nothing(self) -> None:
        dp = self.draw_positions
        rng = self.lizard.rng
        self.look_pos = (
            dp[0][0]
            + dir_vec(dp[1][0], dp[0][0]) * 100.0
            + deg_to_vec(rng.random() * 360.0) * (100.0 * rng.random())
        )

    # 事件

    def stun(self, st: int) -> None:
        self.flicker = max(3, min(15, st // 3))

    def terrain_impact(self, chunk: int, direction: tuple[int, int], speed: float) -> None:
        """撞击地形的图形反应（LizardBubble 粒子）不移植，留作钩子。"""

    def white_flicker_start(self, fl: int) -> None:
        """LizardGraphics.WhiteFlicker。"""
        if fl > self.white_flicker:
            self.white_flicker = fl
        self.every_second_draw = False

    def push_out_of(self, pos: V2, rad: float) -> None:
        for bp in self.body_parts:
            if dist_less(bp.pos, pos, rad + bp.rad):
                d = distance(bp.pos, pos)
                v = dir_vec(bp.pos, pos)
                bp.pos = bp.pos - v * (rad + bp.rad - d)
                bp.vel = bp.vel - v * (rad + bp.rad - d)

    def reset(self) -> None:
        L = self.lizard
        for i, c in enumerate(L.body_chunks):
            self.draw_positions[i][0] = c.pos
            self.draw_positions[i][1] = c.pos
        for t in self.tail:
            t.reset(L.body_chunks[1].pos)
        for limb in self.limbs:
            limb.reset(L.body_chunks[1].pos)
        for c in self.cosmetics:
            c.reset()
        self.head.reset(L.body_chunks[0].pos)

    @property
    def camouflaged(self) -> float:
        return 1.0 if self.white_camo_amount == -1.0 else self.white_camo_amount

    def _white_camo_update(self, rng) -> None:
        """LizardGraphics.Update 的白蜥蜴段。原版 whitePickUpColor 取身后的屏幕像素；桌面上取不到背景，
        恒为 WHITE_PICKUP，伪装改由绘制时按 camouflaged 整体变透明来表现。"""
        L = self.lizard
        if self.white_camo_amount == -1.0:
            self.white_camo_color = self.white_pickup_color
            self.white_camo_amount = 1.0
        h = L.health
        if h < 0.6 and rng.random() * 1.5 < h and rng.random() < 1.0 / (10.0 if L.stunned else 40.0):
            self.white_glitch_fit = int(lerp(5.0, 40.0, (1.0 - h) * rng.random()))
        if self.white_glitch_fit == 0 and L.stunned and rng.random() < 0.05:
            self.white_glitch_fit = 2
        if self.white_glitch_fit > 0:
            self.white_glitch_fit -= 1
            f = 1.0 - h
            if rng.random() < 0.2:
                self.white_camo_drag = 1.0
            if rng.random() < 0.2:
                self.white_camo_amount = 1.0
            if rng.random() < 0.5:
                rnd = (rng.random(), rng.random(), rng.random())
                self.white_camo_color = color_lerp(
                    self.white_camo_color, rnd, (f**0.2) * (rng.random() ** 0.1)
                )
            if rng.random() < 1.0 / 3.0:
                self.white_pickup_color = (rng.random(), rng.random(), rng.random())
        elif self.show_dominance > 0.0:
            sd = self.show_dominance
            self.white_dominance_hue += rng.random() * sd**2 * 0.2
            if self.white_dominance_hue > 1.0:
                self.white_dominance_hue -= 1.0
            self.white_camo_color = color_lerp(
                self.white_camo_color,
                hsl2rgb(self.white_dominance_hue, 1.0, 0.5),
                inverse_lerp(0.5, 1.0, sd**0.5) * rng.random(),
            )
            self.white_camo_amount = lerp(
                self.white_camo_amount, 1.0 - math.sin(inverse_lerp(0.0, 1.1, sd**0.5) * math.pi), 0.1
            )
        else:
            if L.animation in (Animation.ShootTongue, Animation.PrepareToLounge, Animation.Lounge):
                self.white_camo_drag = 0.0
            elif rng.random() < 0.1:
                self.white_camo_drag = lerp(
                    self.white_camo_drag, inverse_lerp(0.65, 0.4, L.ai.run_speed), rng.random()
                )
            self.white_camo_amount = clamp(
                lerp(self.white_camo_amount, self.white_camo_drag, 0.1 * rng.random()), 0.15, 1.0
            )
            self.white_camo_color = color_lerp(self.white_camo_color, self.white_pickup_color, 0.1)
            self.white_pickup_color = WHITE_PICKUP

    def sucked_into_shortcut(self, hole: V2) -> None:
        """LizardGraphics.SuckedIntoShortCut：尾巴和腿每 tick 往洞口收 1/6。"""
        for part in (*self.tail, *self.limbs):
            part.last_pos = part.pos
            part.vel = part.vel * 0.5
            part.pos = (part.pos * 5.0 + hole) / 6.0

    # 每 tick

    def update(self) -> None:
        L = self.lizard
        p = L.lizard_params
        rng = L.rng
        dp = self.draw_positions
        chunks = L.body_chunks
        self.show_dominance = clamp(self.show_dominance - 1.0 / lerp(60.0, 120.0, rng.random()), 0.0, 1.0)
        if p.key == "white":
            self._white_camo_update(rng)
        for c in self.cosmetics:
            c.update()
        if self.white_flicker > 0:
            self.white_flicker -= 1

        looker = self.creature_looker
        looker.update()
        if L.animation == Animation.PreySpotted or L.animation == Animation.PreyReSpotted:
            looker.reevaluate_look_object(L.ai.prey_tracker.most_attractive_prey, 10.0)
        lc = looker.look_creature
        if lc is not None:
            speed = lerp(100.0, 20.0, p.neck_stiffness)
            if lc.visual_contact:
                self.look_pos = move_towards(
                    self.look_pos, lc.represented_creature.realized_creature.main_body_chunk.pos, speed
                )
            else:
                self.look_pos = move_towards(
                    self.look_pos, L.terrain.middle_of(lc.best_guess_for_position().tile), speed
                )

        if L.animation == Animation.PrepareToLounge:
            self.head_color_setter = clamp(
                self.head_color_setter - 1.0 / (p.pre_lounge_crouch / 2.0), -1.0, 1.0
            )
        elif L.animation == Animation.Lounge:
            self.head_color_setter = 1.0
        else:
            self.head_color_setter = lerp(self.head_color_setter, 0.0, 0.2)
        if L.post_lounge_stun > 0:
            self.head_color_setter = lerp(self.head_color_setter, -1.0, 0.8)

        if L.stunned and not self._stunned_last_update:
            self._rotate_while_stunned = True
        self._stunned_last_update = L.stunned
        for i, c in enumerate(chunks):
            dp[i][1] = dp[i][0]
            dp[i][0] = c.pos
        num6 = (4.0 + 7.0 / p.walk_bob) / 2.0
        self.front_bob = (self.front_bob * num6 + (self.front_legs_grabbing - 1)) / (num6 + 1.0)
        self.hind_bob = (self.hind_bob * num6 + (self.hind_legs_grabbing - 1)) / (num6 + 1.0)
        dp[0][0] = V2(dp[0][0].x, dp[0][0].y + self.front_bob * p.walk_bob)
        dp[1][0] = V2(dp[1][0].x, dp[1][0].y + self.front_bob + self.hind_bob * p.walk_bob * 0.5)
        dp[2][0] = V2(dp[2][0].x, dp[2][0].y + self.hind_bob * p.walk_bob)
        if L.animation == Animation.ShootTongue:
            k = 2.0 if L.time_in_animation < L.time_to_remain_in_animation // 2 - 2 else -1.0
            k *= L.time_in_animation / p.tongue_warm_up * 10.0
            dp[0][0] = dp[0][0] + dir_vec(dp[0][0], chunks[2].pos) * k
            dp[2][0] = dp[2][0] + dir_vec(dp[2][0], chunks[0].pos) * k

        if self.flicker > 0:
            self.flicker -= 1
            self.blink = rng.random()
            self.last_blink = rng.random()
        else:
            self.last_blink = self.blink
            if not L.consious:
                self.blink = lerp(self.blink - math.floor(self.blink), 0.25, 0.02)
            else:
                self.blink += (
                    lerp(0.0025, 0.07, max(L.ai.excitement, self.show_dominance)) + rng.random() * 0.001
                )

        self.last_breath = self.breath
        if not L.dead:
            self.breath += 0.0125
        if L.consious and rng.random() < 0.05:
            self.tail_direction = deg_to_vec(rng.random() * 360.0) * rng.random()

        num8 = 0.0
        self.legs_grabbing = 0
        self.front_legs_grabbing = 0
        self.hind_legs_grabbing = 0
        flag = True
        nl = len(self.limbs)
        for i, limb in enumerate(self.limbs):
            limb.update()
            if limb.grip_counter >= p.limb_grip_delay:
                self.legs_grabbing += 1
                if i < 2:
                    self.front_legs_grabbing += 1
                elif i >= nl - 2:
                    self.hind_legs_grabbing += 1
            if limb.grip_counter > 0:
                flag = False
            lp = limb.pos
            l2 = limb.connection.pos
            l1 = limb.connection.rotation_chunk.pos
            den = (l2.y - l1.y) ** 2 + (l2.x - l1.x) ** 2
            # 两节重合时原版是 0/0 = NaN，后面的比较都为假；这里按 0 处理
            num11 = (
                ((l2.y - l1.y) * lp.x - (l2.x - l1.x) * lp.y + l2.x * l1.y - l2.y * l1.x) / math.sqrt(den)
                if den > 0.0
                else 0.0
            )
            num11 *= 1.0 if i > 1 else -1.0
            if abs(num11) > 10.0:
                num8 += sign(num11)
            limb.flip = lerp(limb.flip, 1.0 if num11 < 0.0 else -1.0, 0.3)
        num8 = clamp(num8, -1.0, 1.0)
        self.last_depth_rotation = self.depth_rotation
        if not L.stunned or self._rotate_while_stunned:
            self.depth_rotation = lerp(self.depth_rotation, num8, 0.1)
        self.last_head_depth_rotation = self.head_depth_rotation
        head = self.head
        d0 = dp[0][0]
        fx, fy = _normalized(self.look_pos.x - d0.x, self.look_pos.y - d0.y)
        hx, hy = _normalized(head.pos.x - d0.x, head.pos.y - d0.y)
        f2 = inverse_lerp(0.0, 0.6, abs(fx * hx + fy * hy))
        self.head_depth_rotation = lerp(self.head_depth_rotation, self.depth_rotation * f2, 0.5)
        if flag:
            self.no_grip_counter += 1
        else:
            self.no_grip_counter = 0

        self.tail[0].connected_point = dp[2][0]
        stiffness = lerp(p.tail_stiffness, 900.0, self.show_dominance)
        for i in range(len(self.tail) - 1, -1, -1):
            self._update_tail_segment(i, stiffness)

        head.update()
        grasp = L.grasps[0]
        if grasp is not None and getattr(grasp.grabbed, "is_creature", False):
            head.pos = grasp.grabbed.body_chunks[grasp.chunk_grabbed].pos
        elif L.consious:
            d1 = dp[1][0]
            vector6 = V2(*fdir(d0.x, d0.y, self.look_pos.x, self.look_pos.y))
            if L.upcoming_connections:
                dest = L.terrain.middle_of(L.upcoming_connections[-1].destination_coord)
                vector6 = vslerp(
                    vector6, V2(*fdir(d0.x, d0.y, dest.x, dest.y)), 0.15 + p.neck_stiffness * 0.15
                )
            fwd = V2(*fdir(d1.x, d1.y, d0.x, d0.y))
            num14 = vector6.x * fwd.x + vector6.y * fwd.y
            num14 = clamp(-num14, 0.0, 1.0)
            num14 = 1.0 - num14
            num14 = num14**3
            num14 = 1.0 - num14
            num14 *= 1.0 - p.neck_stiffness
            if num14 > 0.0:
                vector6 = vslerp(vector6, fwd, num14)
            head.vel = head.vel + vector6 * lerp(6.0, 2.0, p.neck_stiffness)
        if L.tongue is not None and L.tongue.out:
            head.vel = dir_vec(d0, L.tongue.pos) * 5.0
        ex, ey = fdir(dp[1][0].x, dp[1][0].y, d0.x, d0.y)
        head.connect_to_point(
            V2(d0.x + ex * (12.0 * p.head_size), d0.y + ey * (12.0 * p.head_size)),
            self.head_connection_rad,
            False,
            0.2,
            chunks[0].vel,
            0.5,
            0.1,
        )
        if L.bubble > 0:
            head.pos = head.pos + deg_to_vec(rng.random() * 360.0) * (5.0 * self.bubble_intensity)
        if L.tongue is not None:
            L.tongue.update_graphics(self)
        if self.voice_visualization > 0.2:
            k = 8.0 * inverse_lerp(0.2, 1.0, self.voice_visualization) ** 0.5
            for i in range(3):
                dp[i][0] = dp[i][0] + rnv(rng) * (k / (1 + i))

    def _update_tail_segment(self, i: int, stiffness: float) -> None:
        L = self.lizard
        dp = self.draw_positions
        tail = self.tail
        seg = tail[i]
        seg.update()
        n1 = len(tail) - 1
        vel = seg.vel
        seg.vel = V2(vel.x, vel.y - 0.9 * ((i / n1) ** 3 if n1 > 0 else 0.0))
        lim = 15.0 * (i + 1)
        d2 = dp[2][0]
        sp = seg.pos
        if not math.hypot(sp.x - d2.x, sp.y - d2.y) < lim:
            ux, uy = fdir(d2.x, d2.y, sp.x, sp.y)
            c2 = L.body_chunks[2].pos
            sp = seg.pos = V2(c2.x + ux * lim, c2.y + uy * lim)
        d1 = dp[1][0]
        a = d1
        if i == 1:
            a = d2
        elif i > 1:
            a = tail[i - 2].pos
        ax = a.x + (d1.x - a.x) * 0.2
        ay = a.y + (d1.y - a.y) * 0.2
        d = math.hypot(ax - sp.x, ay - sp.y)
        vel = seg.vel
        vx, vy = vel.x, vel.y
        if d > 0.0:
            ux, uy = fdir(ax, ay, sp.x, sp.y)
            k = stiffness * L.lizard_params.tail_stiffness_decline**i
            vx = vx + (ux * k) / d
            vy = vy + (uy * k) / d
        if i == 0:
            td = self.tail_direction
            vx = vx + td.x
            vy = vy + td.y
        seg.vel = V2(vx, vy)
        if self.show_dominance > 0.0:
            rng = L.rng
            seg.vel = seg.vel + deg_to_vec(rng.random() * 360.0) * (self.show_dominance * rng.random() * 2.0)
