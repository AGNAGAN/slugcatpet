"""多个行为共用的动作：指光标、走位。"""

from __future__ import annotations

import math

from ... import tuning
from ...world.rain import SHELTER_MARGIN

WALL_MARGIN = 40.0
ARM_REACH_NEAR = 24.0
ARM_REACH_FAR = 48.0


def rain_blocks(fsm, *pts):
    """大雨时自己在遮挡下、而这些点有一处不该去；已经淋着雨就不管，交给躲雨。"""
    rain = fsm.win.rain
    if not rain.dangerous() or _wet(fsm):
        return False
    return any(rain.keeps_out(x, y) for x, y in pts)


def arc_blocked(fsm, x0, y0, pts, step=3):
    """大雨时自己在遮挡下、而从 (x0, y0) 起跳沿 pts（相对位移）飞的这段会出遮挡。"""
    rain = fsm.win.rain
    if not rain.dangerous() or _wet(fsm):
        return False
    r = fsm.body.chunk0.rad
    return any(rain.exposed(x0 + px, y0 + py - r) for px, py in pts[::step])


def _wet(fsm):
    b = fsm.body
    rain = fsm.win.rain
    return rain.touches(b.chunk0) or rain.touches(b.chunk1)


def open_span(fsm, margin=120.0):
    """空地范围：能走的地面两头各收 margin；大雨时限在脚下有遮挡的那段。"""
    b = fsm.body
    lo = 0.0 if b.walk_min is None else b.walk_min
    hi = fsm.WL if b.walk_max is None else b.walk_max
    if fsm.win.rain.dangerous():
        lo, hi = _dry_span(fsm, lo, hi) or (lo, hi)
    if hi - lo > margin * 2.0:
        lo, hi = lo + margin, hi - margin
    return lo, hi


def pick_open_x(fsm, margin=120.0):
    return fsm.rng.uniform(*open_span(fsm, margin))


def pick_social_wander_x(
    lo, hi, self_x, marks, gap, rng, sigma, samples, move_w, cross_w, noise, jitter, min_move
):
    """闲逛目标：marks 为 [(猫的位置 x, 想靠近多少)]。候选是想靠近的猫身边（隔 gap 站在靠我这侧）、原地附近和几个随机点，
    离我不到 min_move 的不要，取吸引最大的；都不行 None。"""

    def far(x):
        return abs(x - self_x) >= min_move

    if not marks:
        return next((x for x in (rng.uniform(lo, hi) for _ in range(samples)) if far(x)), None)
    span = max(1.0, hi - lo)
    inv = -1.0 / (2.0 * sigma * sigma)
    lazy = move_w * min(1.0, sum(abs(w) for _, w in marks))  # 没有想靠近或躲开的猫时不在乎走多远

    def score(x):
        a, b = (self_x, x) if self_x <= x else (x, self_x)
        pull = sum(w * math.exp(inv * (x - mx) ** 2) for mx, w in marks)
        crossed = sum(1 for mx, _ in marks if a < mx < b)
        return pull - lazy * abs(x - self_x) / span - cross_w * crossed + noise * rng.random()

    cands = [self_x + rng.choice((-1.0, 1.0)) * rng.uniform(min_move, max(min_move, jitter))]
    cands += [mx + math.copysign(gap, self_x - mx) for mx, w in marks if w > rng.random()]
    cands += [rng.uniform(lo, hi) for _ in range(samples)]
    return max((x for x in (min(max(x, lo), hi) for x in cands) if far(x)), key=score, default=None)


def wander(fsm):
    b = fsm.body
    lo = max(b.walk_min, WALL_MARGIN)
    hi = min(b.walk_max, fsm.WL - WALL_MARGIN)
    if hi <= lo:
        lo, hi = WALL_MARGIN, fsm.WL - WALL_MARGIN
    if fsm.win.rain.dangerous():
        span = _dry_span(fsm, lo, hi)
        if span is None:
            b.walk_to(_shelter_x(fsm, lo, hi), None)
            return
        lo, hi = span
    x = pick_social_wander_x(
        lo,
        hi,
        b.chunk1.x,
        fsm.social.wander_marks(fsm.win),
        fsm.social.floor_gap,
        fsm.rng,
        fsm.WL * tuning.SOCIAL_WANDER_SIGMA_FRAC,
        tuning.SOCIAL_WANDER_SAMPLES,
        tuning.SOCIAL_WANDER_MOVE_W,
        tuning.SOCIAL_WANDER_CROSS_W,
        tuning.SOCIAL_WANDER_NOISE,
        fsm.WL * tuning.SOCIAL_WANDER_JITTER_FRAC,
        tuning.MIN_MOVE,
    )
    t = None if x is None else b.reach(x, None)  # 闲逛去那附近能站下的地方就行；走不过去就不去
    if t is not None and abs(t - b.chunk1.x) >= tuning.MIN_MOVE:  # 被挪到别的猫边上后离得太近也不去
        b.walk_to(x, None)


def _dry_span(fsm, lo, hi):
    """大雨时闲逛的范围：自己脚下那段有遮挡的地面；不在遮挡下返回 None。"""
    x = fsm.body.chunk1.x
    for a, b in fsm.win.rain.floor_spans(lo, hi, SHELTER_MARGIN):
        if a <= x <= b:
            return a, b
    return None


def _shelter_x(fsm, lo, hi):
    """不在遮挡下时去最近的遮挡，没有遮挡就原地不动。"""
    x = fsm.body.chunk1.x
    near = fsm.win.rain.nearest_shelter_x(x, lo, hi, SHELTER_MARGIN)
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
