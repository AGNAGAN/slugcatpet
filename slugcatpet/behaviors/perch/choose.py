"""选落脚点：在走得到、不用挤过别的猫、杆底走得过去的杆上位置里随机挑，偏向靠近想亲近的猫、远离想躲的猫。"""

from __future__ import annotations

import math

from ... import tuning
from ...planning.climb_reach import keepout_for
from ...planning.climbmoves import GRAB_V_REACH


class Mark:
    """预约的落脚点（给别的猫看）。"""

    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


def crowd_points(fsm):
    """别的猫的头和它们预约的落脚点。"""
    return [(x, y) for x, y, _ in crowd_pull(fsm)]


def crowd_pull(fsm):
    """crowd_points 各点再带上我想靠近那只猫多少：[(x, y, w)]。"""
    out = []
    for o in fsm.social.others(fsm.win):
        w = fsm.social.pull(fsm.win, o)
        out.append((o.body.chunk0.x, o.body.chunk0.y, w))
        m = fsm.social.held(o, "perch")
        if m is not None:
            out.append((m.x, m.y, w))
    return out


def pick(fsm, cm, start, bar=None, exclude=None):
    """从 start 挑一个落脚点：(位置, 路线)；bar 给定时只在这根杆上挑；没有能去的 None。"""
    dist, came = cm.reach_costs(start, tuning.PERCH_COST_LIMIT, keepout=keepout_for(fsm.win))
    pulls = crowd_pull(fsm)
    crowd = [(x, y) for x, y, _ in pulls]
    r2 = tuning.PERCH_CROWD_R**2
    cands = []
    rain = fsm.win.rain
    sx, sy = cm.head(start)
    for s in dist:
        if s[0] == "F" or s == start or s == exclude or (bar is not None and s[1] != bar):
            continue
        hx, hy = cm.head(s)
        if math.hypot(hx - sx, hy - sy) < tuning.MIN_MOVE or rain.keeps_out(hx, hy):
            continue
        if any((hx - ox) ** 2 + (hy - oy) ** 2 < r2 for ox, oy in crowd):
            continue
        path = cm.path_to(came, start, s)
        if crowd and _squeezes(cm, start, path, crowd, r2):
            continue
        if _base_blocked(fsm, cm, path):
            continue
        cands.append(s)
    if not cands:
        return None
    rng = fsm.rng
    spot = rng.choice(cands)
    if pulls and rng.random() < max(abs(w) for _, _, w in pulls):

        def spread(s):
            hx, hy = cm.head(s)
            return sum(w * math.hypot(hx - ox, hy - oy) for ox, oy, w in pulls)

        alt = rng.choice(cands)
        spot = min(spot, alt, key=spread)
    return spot, cm.path_to(came, start, spot)


def _base_blocked(fsm, cm, path):
    """路线要从地面抓的杆，杆底走不到（被别的猫占着或路上过不去）。"""
    return any(
        act[0] == "grab_v" and fsm.body.reach(cm.bars[act[1]].x, GRAB_V_REACH) is None for _, act in path
    )


def _squeezes(cm, start, path, crowd, r2):
    """路线沿杆走时要从别的猫身边挤过去。"""
    prev = start
    for s, _ in path:
        if s[0] != "F" and s[:2] == prev[:2]:
            ax, ay = cm.head(prev)
            bx, by = cm.head(s)
            dx, dy = bx - ax, by - ay
            n = dx * dx + dy * dy
            for ox, oy in crowd:
                t = ((ox - ax) * dx + (oy - ay) * dy) / n if n > 0.0 else 0.0
                if t > 0.0:
                    t = min(t, 1.0)
                    if (ax + dx * t - ox) ** 2 + (ay + dy * t - oy) ** 2 < r2:
                        return True
        prev = s
    return False
