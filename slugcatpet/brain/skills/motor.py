"""多个行为共用的动作：指光标、走位。"""

from __future__ import annotations

import math

from ... import tuning
from ...world.rain import SHELTER_MARGIN

WALL_MARGIN = 40.0
ARM_REACH_NEAR = 24.0
ARM_REACH_FAR = 48.0


def pick_open_x(fsm, margin=120.0):
    b = fsm.body
    lo = 0.0 if b.walk_min is None else b.walk_min
    hi = fsm.WL if b.walk_max is None else b.walk_max
    if hi - lo > margin * 2.0:
        lo, hi = lo + margin, hi - margin
    return fsm.rng.uniform(lo, hi)


def pick_social_wander_x(
    lo,
    hi,
    self_x,
    others_x,
    sociability,
    rng,
    sigma,
    samples,
    lo_thresh,
    hi_thresh,
    move_w,
    cross_w,
    stay_gain,
    stay_span,
):
    if not others_x:
        return rng.uniform(lo, hi)
    span = max(1.0, hi - lo)
    inv = -1.0 / (2.0 * sigma * sigma)
    sign = 1.0 if sociability < lo_thresh else (-1.0 if sociability > hi_thresh else 0.0)

    def density(x):
        return sum(math.exp(inv * (x - ox) ** 2) for ox in others_x)

    def crossed(x):
        a, b = (self_x, x) if self_x <= x else (x, self_x)
        return sum(1 for ox in others_x if a < ox < b)

    def cost(x):
        return sign * density(x) + move_w * abs(x - self_x) / span + cross_w * crossed(x)

    n = max(1, samples)
    step = span / n
    xs = [lo + step * (i + rng.random()) for i in range(n)]
    if sign == 0.0:
        return min(xs, key=lambda x: cross_w * crossed(x) + rng.random())
    best = min(xs, key=cost)
    if cost(best) >= sign * density(self_x) - stay_gain:
        return min(max(self_x + rng.uniform(-stay_span, stay_span), lo), hi)
    return best


def wander(fsm):
    b = fsm.body
    lo = max(b.walk_min, WALL_MARGIN)
    hi = min(b.walk_max, fsm.WL - WALL_MARGIN)
    if hi <= lo:
        lo, hi = WALL_MARGIN, fsm.WL - WALL_MARGIN
    if fsm.win.rain.dangerous():
        b.walk_to(_dry_x(fsm, lo, hi))
        return
    others_x = fsm.social.others_x(fsm.win)
    x = pick_social_wander_x(
        lo,
        hi,
        b.chunk1.x,
        others_x,
        fsm.traits.sociability,
        fsm.rng,
        fsm.WL * tuning.SOCIAL_WANDER_SIGMA_FRAC,
        tuning.SOCIAL_WANDER_SAMPLES,
        tuning.SOCIAL_WANDER_LO,
        tuning.SOCIAL_WANDER_HI,
        tuning.SOCIAL_WANDER_MOVE_W,
        tuning.SOCIAL_WANDER_CROSS_W,
        tuning.SOCIAL_WANDER_STAY_GAIN,
        fsm.WL * tuning.SOCIAL_WANDER_STAY_SPAN_FRAC,
    )
    b.walk_to(x)


def _dry_x(fsm, lo, hi):
    """大雨时的闲逛目标：只在有遮挡的地面上，没有遮挡就原地不动。"""
    rain = fsm.win.rain
    x = fsm.body.chunk1.x
    spans = rain.floor_spans(lo, hi, SHELTER_MARGIN)
    for a, b in spans:
        if a <= x <= b:
            return fsm.rng.uniform(a, b)
    near = rain.nearest_shelter_x(x, lo, hi, SHELTER_MARGIN)
    return x if near is None else near


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
