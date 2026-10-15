"""重压撞击：落地震动、从高处砸下 / 翻滚 / 滑铲撞到猫和活物（y↓）。"""

from __future__ import annotations

import math

from ...items.base import HIT_SLAM, creatures

COOLDOWN = 20
CONTACT_PAD = 2.0
SLAM_FALL_VY = 10.0  # 下落快于此值才算砸
SLAM_SPEED = 25.0  # 或速度大于此值
ROLL_STUN = 120
SLIDE_STUN, SLIDE_FORCE = 50, 0.25
STUN_CAP, STUN_MIN = 240, 25
HIT_PUSH, HIT_PUSH_MAX = 0.4, 12.0
BOUNCE_MAX_SPEED = 40.0


def height_force(h):
    """按下落高度分档的砸击力度。"""
    base = 4.0
    if h < 100.0:
        return base * 0.5
    if h < 200.0:
        return base
    if h < 320.0:
        return base * 2.0
    if h < 600.0:
        return base * 3.0
    return base * 5.0


def slam_stun(speed):
    n = min(STUN_CAP, int(120 * math.floor(speed / 7.0)))
    return 0 if n < STUN_MIN else n


class HeavyImpact:
    """一只猫的撞击状态：上次着地高度、下落速度、冷却。"""

    def __init__(self, p):
        self.p = p
        self.ground_y = None
        self.airborne = False
        self.fall_vy = 0.0
        self.cooldown = 0

    def pre_step(self, pet):
        b = pet.body
        c1 = b.chunk1
        if b.on_floor() or b.on_pole or b.suspended or b.swimming:
            self.ground_y = c1.y
        grounded = b.on_floor()
        self.airborne = not grounded
        self.fall_vy = max(b.chunk0.vy, b.chunk1.vy) if not grounded else 0.0
        if self.cooldown > 0:
            self.cooldown -= 1

    def post_step(self, pet):
        b = pet.body
        if b.dead or b.stun > 0 or b.hover or b.zerog or b.swimming:
            return
        if self.airborne and b.on_floor():
            self._land(pet)
        if self.cooldown > 0 or b.on_pole or b._held_chunk() is not None:
            return
        anim = b.animation
        if anim == "Roll" and b._ctrl_on:
            self._hit(pet, ROLL_STUN, 1.0, roll=True)
        elif anim == "BellySlide" and b._ctrl_on:
            self._hit(pet, SLIDE_STUN, SLIDE_FORCE, slide=True)
        elif not b.on_floor():
            v = _slow_chunk_vel(b)
            if v[1] > SLAM_FALL_VY or math.hypot(*v) > SLAM_SPEED:
                c0 = b.chunk0
                speed = math.hypot(c0.vx, c0.vy)
                self._hit(pet, slam_stun(speed), height_force(self._height(b)))

    def _height(self, b):
        return 0.0 if self.ground_y is None else max(0.0, b.chunk1.y - self.ground_y)

    def _land(self, pet):
        p = self.p
        if p.land_shake <= 0.0 or self.fall_vy < p.land_shake_speed:
            return
        b = pet.body
        k = self.fall_vy * height_force(self._height(b)) * b.chunk0.mass * 0.1 * p.land_shake
        pet.window._shake_impact(b.chunk1, (0, 1), self.fall_vy, 0.0, 0.0, k)

    def _hit(self, pet, stun, force, roll=False, slide=False):
        b = pet.body
        cats = [o for o in pet.window.pets if o is not pet and _touching(b, o.body)] if self.p.slam else []
        flies = [f for f in creatures(pet.window) if _fly_touching(b, f)]
        if not cats and not flies:
            return
        c0, c1 = b.chunk0, b.chunk1
        vx, vy = c0.vx, c0.vy
        push_x = vx * (5.0 if roll else 1.0)
        for o in cats:
            if stun > 0 and not o.body.dead:
                o.behavior.apply_stun(stun, blame=False)
            _push(o.body, push_x, vy)
        for f in flies:
            f.struck(HIT_SLAM)
            f.vx += vx * HIT_PUSH
            f.vy += vy * HIT_PUSH
        scale = 5.0 if roll else force
        pet.window._shake_impact(c0, (0, 1), math.hypot(vx, vy), 0.0, *_shake(b, vx, vy, scale))
        self.cooldown = COOLDOWN
        if roll:
            b.animation = None
            b._ctrl_roll_direction = 0
        if not cats:
            for c in (c0, c1):
                c.vx *= 0.9
                c.vy *= 0.9
        elif math.hypot(vx, vy) < BOUNCE_MAX_SPEED:
            c0.vx, c0.vy = vx * -0.5, vy * -0.5
            c1.vx, c1.vy = c0.vx, c0.vy
        else:
            c0.vx *= 0.9
            c0.vy *= 0.9
        if slide:
            c0.vx /= 3.0
            b._ctrl_roll_counter = 99


def _slow_chunk_vel(b):
    c0, c1 = b.chunk0, b.chunk1
    if math.hypot(c1.vx, c1.vy) < math.hypot(c0.vx, c0.vy):
        return c1.vx, c1.vy
    return c0.vx, c0.vy


def _touching(a, o):
    if o.dead or o.hover:
        return False
    for ca in a.collision_chunks():
        for co in o.collision_chunks():
            if math.hypot(co.x - ca.x, co.y - ca.y) < ca.rad + co.rad + CONTACT_PAD:
                return True
    return False


def _fly_touching(a, f):
    if f.dead or f.state != "free" or f.held_by_hand is not None:
        return False
    return any(math.hypot(f.x - c.x, f.y - c.y) < c.rad + f.rad + CONTACT_PAD for c in a.collision_chunks())


def _push(o, vx, vy):
    for c in o.collision_chunks():
        if c.pinned:
            continue
        c.vx += max(-HIT_PUSH_MAX, min(HIT_PUSH_MAX, vx * HIT_PUSH))
        c.vy += max(-HIT_PUSH_MAX, min(HIT_PUSH_MAX, vy * HIT_PUSH))


def _shake(b, vx, vy, scale):
    k = scale * b.chunk0.mass * 0.1
    return vx * k, vy * k
