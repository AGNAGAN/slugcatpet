"""选落脚点：在走得到、不用挤过别的猫的杆上位置里随机挑，合群的偏向靠近别的猫。"""

from __future__ import annotations

import math

from ... import tuning


class Mark:
    """预约的落脚点（给别的猫看）。"""

    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x, self.y = x, y


def crowd_points(fsm):
    """别的猫的头和它们预约的落脚点。"""
    out = []
    for o in fsm.social.others(fsm.win):
        out.append((o.body.chunk0.x, o.body.chunk0.y))
        m = fsm.social.held(o, "perch")
        if m is not None:
            out.append((m.x, m.y))
    return out


def pick(fsm, cm, start, bar=None, exclude=None):
    """从 start 挑一个落脚点：(位置, 路线)；bar 给定时只在这根杆上挑；没有能去的 None。"""
    dist, came = cm.reach_costs(start, tuning.PERCH_COST_LIMIT)
    crowd = crowd_points(fsm)
    r2 = tuning.PERCH_CROWD_R**2
    cands = []
    rain = fsm.win.rain
    for s in dist:
        if s[0] == "F" or s == start or s == exclude or (bar is not None and s[1] != bar):
            continue
        hx, hy = cm.head(s)
        if rain.keeps_out(hx, hy):
            continue
        if any((hx - ox) ** 2 + (hy - oy) ** 2 < r2 for ox, oy in crowd):
            continue
        if crowd and _squeezes(cm, start, cm.path_to(came, start, s), crowd, r2):
            continue
        cands.append(s)
    if not cands:
        return None
    rng = fsm.rng
    spot = rng.choice(cands)
    lean = fsm.traits.sociability - 0.5
    if crowd and rng.random() < abs(lean) * 2.0:

        def spread(s):
            hx, hy = cm.head(s)
            return sum(math.hypot(hx - ox, hy - oy) for ox, oy in crowd)

        alt = rng.choice(cands)
        spot = min(spot, alt, key=spread) if lean > 0 else max(spot, alt, key=spread)
    return spot, cm.path_to(came, start, spot)


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
