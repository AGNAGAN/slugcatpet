"""多个行为共用的动作：指光标、走位、啃食。"""
from __future__ import annotations

import math

from ... import tuning

WALL_MARGIN = 40.0
ARM_REACH_NEAR = 24.0
ARM_REACH_FAR = 48.0

EAT_INTERVAL = 15
EAT_APPROACH = 12
EAT_HOLD_POSE = 0.25
EAT_CHOMP_POSE = 1.0
EAT_STRIKE_POW = 3.0       # 举起 / 放下曲线指数，越大越快
EAT_PLATEAU = 0.34         # 嘴边停留占一次咀嚼的比例
EAT_PEAK_PHASE = 0.5       # 在脉冲峰值咬下
BITE_HEAD_NUDGE = 2.0


def eat_chomp_pulse(phase):
    """咀嚼脉冲 0→1→0。"""
    if phase <= 0.0 or phase >= 1.0:
        return 0.0
    u = phase / EAT_PEAK_PHASE if phase <= EAT_PEAK_PHASE else (1.0 - phase) / (1.0 - EAT_PEAK_PHASE)
    if u >= 1.0 - EAT_PLATEAU:
        return 1.0
    return 1.0 - (1.0 - u / (1.0 - EAT_PLATEAU)) ** EAT_STRIKE_POW


class Chew:
    __slots__ = ("counter", "bit", "approach")

    def __init__(self):
        self.reset()

    def reset(self):
        self.counter = 0
        self.bit = False
        self.approach = True


def chew_reset(fsm):
    fsm.chew.reset()


def carry_chew(fsm, b):
    f = b.carried_fruit
    c = fsm.chew
    fsm.gfx.look_at = (f.x, f.y)
    c.counter += 1
    if c.approach:
        b.eat_raise = EAT_HOLD_POSE * min(1.0, c.counter / EAT_APPROACH)
        if c.counter >= EAT_APPROACH:
            c.approach = False
            c.counter = 0
        return
    phase = min(1.0, c.counter / EAT_INTERVAL)
    b.eat_raise = EAT_HOLD_POSE + (EAT_CHOMP_POSE - EAT_HOLD_POSE) * math.sin(phase * math.pi)
    if c.counter >= EAT_INTERVAL // 2 and not c.bit:
        c.bit = True
        dx, dy = f.x - fsm.gfx.head.x, f.y - fsm.gfx.head.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            fsm.gfx.head.vx += dx / d * BITE_HEAD_NUDGE
            fsm.gfx.head.vy += dy / d * BITE_HEAD_NUDGE
        b.consume_carried()
    if c.counter >= EAT_INTERVAL:
        c.counter = 0
        c.bit = False


def pick_open_x(fsm, margin=120.0):
    b = fsm.body
    lo = 0.0 if b.walk_min is None else b.walk_min
    hi = fsm.WL if b.walk_max is None else b.walk_max
    if hi - lo > margin * 2.0:
        lo, hi = lo + margin, hi - margin
    return fsm.rng.uniform(lo, hi)


def pick_social_wander_x(lo, hi, self_x, others_x, sociability, rng, sigma, samples,
                         lo_thresh, hi_thresh, move_w, cross_w, stay_gain, stay_span):
    if not others_x or lo_thresh <= sociability <= hi_thresh:
        return rng.uniform(lo, hi)
    span = max(1.0, hi - lo)
    inv = -1.0 / (2.0 * sigma * sigma)
    avoid = sociability < lo_thresh
    sign = 1.0 if avoid else -1.0
    def density(x):
        return sum(math.exp(inv * (x - ox) ** 2) for ox in others_x)
    def crosses(x):
        a, b = (self_x, x) if self_x <= x else (x, self_x)
        return any(a < ox < b for ox in others_x)
    def cost(x):
        c = sign * density(x) + move_w * abs(x - self_x) / span
        if avoid and crosses(x):
            c += cross_w
        return c
    n = max(1, samples)
    step = span / n
    best = min((lo + step * (i + rng.random()) for i in range(n)), key=cost)
    if cost(best) >= sign * density(self_x) - stay_gain:
        return min(max(self_x + rng.uniform(-stay_span, stay_span), lo), hi)
    return best


def wander(fsm):
    b = fsm.body
    lo = max(b.walk_min, WALL_MARGIN)
    hi = min(b.walk_max, fsm.WL - WALL_MARGIN)
    if hi <= lo:
        lo, hi = WALL_MARGIN, fsm.WL - WALL_MARGIN
    others_x = fsm.social.others_x(fsm.win)
    x = pick_social_wander_x(lo, hi, b.chunk1.x, others_x,
                             fsm.traits.sociability, fsm.rng,
                             fsm.WL * tuning.SOCIAL_WANDER_SIGMA_FRAC,
                             tuning.SOCIAL_WANDER_SAMPLES,
                             tuning.SOCIAL_WANDER_LO, tuning.SOCIAL_WANDER_HI,
                             tuning.SOCIAL_WANDER_MOVE_W, tuning.SOCIAL_WANDER_CROSS_W,
                             tuning.SOCIAL_WANDER_STAY_GAIN,
                             fsm.WL * tuning.SOCIAL_WANDER_STAY_SPAN_FRAC)
    b.walk_to(x)


def point_at_cursor(fsm, cursor, enforce_side=False, cover=False):
    fsm._point_stopped = False
    if cursor is None:
        fsm._clear_hands()
        return
    b = fsm.body
    cx, cy = cursor
    spine_ang = fsm.gfx.body_axis()
    slx, sly = fsm.gfx._shoulder(-1.0, spine_ang)
    srx, sry = fsm.gfx._shoulder(+1.0, spine_ang)
    dl = math.hypot(cx - slx, cy - sly)
    dr = math.hypot(cx - srx, cy - sry)
    side = "l" if dl <= dr else "r"
    sx, sy = (slx, sly) if side == "l" else (srx, sry)
    sgn = 1 if cx >= b.chunk0.x else -1
    if enforce_side:
        if fsm.point_side == 0:
            fsm.point_side = sgn
        elif sgn != fsm.point_side:
            fsm._point_stopped = True
            fsm._clear_hands()
            return
    ty = max(cy, fsm.gfx.head.y - 6.0)
    tx = cx
    if cover and math.hypot(cx - sx, cy - sy) <= ARM_REACH_NEAR:
        tx, ty = cx, max(cy, fsm.gfx.head.y - 6.0)
    fsm.gfx.hand_aim[side] = (tx, ty)
    fsm.gfx.hand_aim["l" if side == "r" else "r"] = None


def point_if_near(fsm, cursor):
    if cursor is None:
        fsm._clear_hands()
        return
    d = math.hypot(cursor[0] - fsm.body.chunk0.x, cursor[1] - fsm.body.chunk0.y)
    if d > ARM_REACH_FAR:
        fsm._clear_hands()
    else:
        point_at_cursor(fsm, cursor, enforce_side=False, cover=(d <= ARM_REACH_NEAR))
