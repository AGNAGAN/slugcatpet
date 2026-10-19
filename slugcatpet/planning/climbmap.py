"""杆网寻路：杆和地面上的位置按物理弧线连成图，A* 找够着目标的路线。

位置是 (类, 杆序号, 坐标)，类为 F 地上、V 爬竖杆、T 站杆尖、H 吊横杆、S 站横杆。
"""

from __future__ import annotations

import bisect
import heapq
import math

from .. import tuning
from ..items.base import CLIMBABLE
from .jump_arc import get_arc, get_drop_arc, get_free_jump_arc, get_pole_jump_arc

STEP = 20.0  # 杆上采样间距
CONN = 17.0  # 头到脚
STAND_HOVER = 5.0  # 站在横杆上时脚离杆
TIP_HOVER = 10.0  # 站在杆尖上时臀高出杆顶
BEAM_MARGIN = 8.0  # 横杆两端留出
V_TOL = 10.0  # 头离竖杆这么近能抓住
H_TOL = 6.0  # 横向超出横杆端这么多也算抓住
TOUCH_R = 16.0  # 在杆上时头到目标这么近就够得着
TOUCH_FLY_MARGIN = 5.0  # 跳起来够时少算这么多，留执行偏差
SIDE_OFF = 5.0  # 爬竖杆时头偏到杆的一侧
CATCH_MIN_T = 3  # 起跳后这么多 tick 内不抓
EDGE_PAD = 8.0  # 弧线离窗口边这么近算撞墙
LAND_H = 20.0  # 落地时头离地
SAFE_FALL = 0.8  # 落地速度不到摔晕速度的这么多才肯跳下去

CLIMB_UP = 2.0  # 竖杆上爬速度（× 爬杆系数）
CLIMB_DOWN = 4.4  # 下滑速度
SHIMMY = 1.5  # 吊着挪动速度（× 爬杆系数）
BEAM_WALK = 2.1
T_GRAB = 10.0
T_LETGO = 8.0
T_TIP_UP = 15.0
T_TIP_DOWN = 10.0
T_PULLUP = 24.0
T_SWING = 16.0
T_CROSS = 8.0
T_REACH_UP = 14.0
T_SETUP = 8.0
T_SETTLE = 6.0
JUMP_K = 1.25  # 跳跃比稳当的移动多算的风险
JUMP_PAD = 12.0
REACH_UP_MIN, REACH_UP_MAX = 18.0, 46.0  # 站在横杆上能直接抓到的上方横杆高度差
H_SPEED = 7.0  # 启发式用的最快移动速度
H_WEIGHT = 1.3  # 启发式加权
MAX_EXPAND = 6000

JUMP_HOLDS = (0, 3, 6)
MOVE_DIRS = (0, 1, -1)


class Bar:
    """一根能爬的杆。"""

    __slots__ = ("obj", "vertical", "x0", "x1", "y0", "y1", "grounded", "samples", "lo", "hi")

    def __init__(self, obj, HL):
        self.obj = obj
        ax, ay, bx, by = obj.ax, obj.ay, obj.bx, obj.by
        self.vertical = obj.kind == "vertical"
        self.x0, self.x1 = min(ax, bx), max(ax, bx)
        self.y0, self.y1 = min(ay, by), max(ay, by)
        self.grounded = bool(getattr(obj, "grounded", False))
        if self.vertical:
            self.lo = self.y0  # 头最高到杆顶
            self.hi = max(self.lo, self.y1 - CONN) if self.grounded else self.y1
        else:
            self.lo = self.x0 + BEAM_MARGIN
            self.hi = max(self.lo, self.x1 - BEAM_MARGIN)
        self.samples = _samples(self.lo, self.hi)

    @property
    def x(self):
        return self.x0

    @property
    def y(self):
        return self.y0

    def snap(self, v):
        """杆上离 v 最近的采样点。"""
        s = self.samples
        i = bisect.bisect_left(s, v)
        if i <= 0:
            return s[0]
        if i >= len(s):
            return s[-1]
        return s[i] if s[i] - v < v - s[i - 1] else s[i - 1]


def _samples(lo, hi):
    n = max(1, int(math.ceil((hi - lo) / STEP)))
    return [lo + (hi - lo) * k / n for k in range(n + 1)]


class ArcTable:
    """一条弧的查表：求穿过某条横线或竖线的时刻。"""

    __slots__ = ("xs", "ys", "runs_x", "runs_y", "min_x", "max_x", "min_y", "n", "box")

    def __init__(self, points):
        self.xs = [0.0] + [p[0] for p in points]
        self.ys = [0.0] + [p[1] for p in points]
        self.n = len(self.xs)
        self.runs_x = _runs(self.xs)
        self.runs_y = _runs(self.ys)
        mnx, mxx, mny = [], [], []
        a = b = c = 0.0
        for x, y in zip(self.xs, self.ys):
            a, b, c = min(a, x), max(b, x), min(c, y)
            mnx.append(a)
            mxx.append(b)
            mny.append(c)
        self.min_x, self.max_x, self.min_y = mnx, mxx, mny
        self.box = (min(self.xs), max(self.xs), min(self.ys), max(self.ys))  # 整条弧的范围

    def cross(self, along_x, v):
        """穿过 v 的所有时刻 [(t, 另一坐标)]。"""
        vals, other = (self.xs, self.ys) if along_x else (self.ys, self.xs)
        out = []
        for i0, i1, keys, sign in self.runs_x if along_x else self.runs_y:
            lo, hi = (vals[i0], vals[i1]) if sign > 0 else (vals[i1], vals[i0])
            if not (lo <= v <= hi) or i0 == i1:
                continue
            j = bisect.bisect_left(keys, v * sign) + i0
            j = min(max(j, i0 + 1), i1)
            a, b = vals[j - 1], vals[j]
            f = 0.0 if b == a else (v - a) / (b - a)
            out.append((j - 1 + f, other[j - 1] + (other[j] - other[j - 1]) * f))
        out.sort()
        return out

    def inside(self, t, hx, hy, WL):
        """从 (hx, hy) 起跳到时刻 t 为止没碰到窗口边。"""
        k = min(self.n - 1, int(math.ceil(t)))
        return (
            hx + self.min_x[k] >= EDGE_PAD
            and hx + self.max_x[k] <= WL - EDGE_PAD
            and hy + self.min_y[k] >= 0.0
        )

    def vy_at(self, t):
        """时刻 t 的竖直速度。"""
        i = min(self.n - 1, max(1, int(math.ceil(t))))
        return self.ys[i] - self.ys[i - 1]

    def at(self, t):
        i = min(self.n - 2, int(t))
        f = t - i
        return self.xs[i] + (self.xs[i + 1] - self.xs[i]) * f, self.ys[i] + (self.ys[i + 1] - self.ys[i]) * f


def _runs(vals):
    """拆成单调段。"""
    out = []
    n = len(vals)
    i0 = 0
    while i0 < n - 1:
        sign = 1 if vals[i0 + 1] >= vals[i0] else -1
        i1 = i0 + 1
        while i1 + 1 < n and (vals[i1 + 1] - vals[i1]) * sign >= 0:
            i1 += 1
        out.append((i0, i1, [vals[k] * sign for k in range(i0, i1 + 1)], sign))
        i0 = i1
    return out


_tables: dict = {}


def _table(arc):
    t = _tables.get(id(arc))
    if t is None or t[0] is not arc:
        t = (arc, ArcTable(arc.points))
        _tables[id(arc)] = t
    return t[1]


class ClimbMap:
    """一个世界状态下的杆网，出边按需算。"""

    def __init__(self, pet, bars):
        self.pet = pet
        self.stats = pet.cat.stats
        self.WL, self.HL = pet._WL, pet._HL
        self.bars = bars
        self.floor_h = get_arc(self.stats, 0, 0).takeoff_h
        self.up = CLIMB_UP * self.stats.pole_fac
        self.shimmy = SHIMMY * self.stats.pole_fac
        self.walk = BEAM_WALK * self.stats.runspeed_fac
        lo, hi = _walk_band(pet)
        self.walk_lo, self.walk_hi = lo, hi
        self._out = {}
        self._floor_jumps = None
        self._todo = None
        self._floor_reach = None
        self._env = {}

    def warm(self, n):
        """预先算最多 n 个位置的出边，返回算了几个。"""
        if self._todo is None:
            todo = [("F", -1, round(lx)) for lx, _, _, _ in self.floor_jumps()]
            for i, b in enumerate(self.bars):
                kinds = ("V",) if b.vertical else ("H", "S")
                todo += [(k, i, v) for k in kinds for v in b.samples]
                if b.vertical and b.grounded:
                    todo.append(("T", i, 0.0))
            self._todo = todo
        done = 0
        while done < n and self._todo:
            self.edges(self._todo.pop())
            done += 1
        if not self._todo and self._floor_reach is None and done < n:
            self.floor_reach()
        return done

    @property
    def ready(self):
        """整张图都算好了。"""
        return self._todo is not None and not self._todo and self._floor_reach is not None

    # 位置

    def head(self, spot):
        """这个位置上头的坐标。"""
        k, i, v = spot
        if k == "F":
            return v, self.HL - self.floor_h
        b = self.bars[i]
        if k == "V":
            return b.x, v
        if k == "T":
            return b.x, b.y0 - TIP_HOVER - CONN
        if k == "H":
            return v, b.y
        return v, b.y - STAND_HOVER - CONN

    # 出边

    def edges(self, spot):
        e = self._out.get(spot)
        if e is None:
            e = self._out[spot] = self._make_edges(spot)
        return e

    def _make_edges(self, spot):
        k, i, v = spot
        out = []
        if k == "F":
            self._floor_edges(v, out)
            return out
        b = self.bars[i]
        if k == "V":
            s = b.samples
            j = s.index(v)
            if j > 0:
                out.append((("V", i, s[j - 1]), (v - s[j - 1]) / self.up, ("climb", i, s[j - 1])))
            if j + 1 < len(s):
                out.append((("V", i, s[j + 1]), (s[j + 1] - v) / CLIMB_DOWN, ("climb", i, s[j + 1])))
            if j == 0 and b.grounded:
                out.append((("T", i, 0.0), T_TIP_UP, ("tip_up", i)))
            if j == len(s) - 1 and b.grounded:
                out.append((("F", -1, round(b.x)), T_LETGO, ("step_off", i)))
            self._crossings_from_v(i, b, v, out)
            for d in (1, -1):
                self._flight(spot, ("polejump", d), get_pole_jump_arc(self.stats, d), i, out)
            self._flight(spot, ("drop", 0), get_drop_arc(self.stats, 0), i, out)
            self._drop_to_floor(spot, i, out)
        elif k == "T":
            out.append((("V", i, b.samples[0]), T_TIP_DOWN, ("tip_down", i)))
            self._stand_jumps(spot, i, out)
            self._drop_to_floor(spot, i, out)
        elif k == "H":
            self._along(spot, b, i, self.shimmy, "shimmy", out)
            out.append((("S", i, v), T_PULLUP, ("pullup", i, v)))
            for j, o in enumerate(self.bars):
                if o.vertical and o.lo <= b.y <= o.hi and abs(o.x - v) < STEP:
                    out.append((("V", j, o.snap(b.y)), T_CROSS, ("hang_to_v", j, o.snap(b.y))))
            for md in MOVE_DIRS:
                self._flight(spot, ("drop", md), get_drop_arc(self.stats, md), i, out)
            self._drop_to_floor(spot, i, out)
        else:
            self._along(spot, b, i, self.walk, "beamwalk", out)
            out.append((("H", i, v), T_SWING, ("swing_under", i, v)))
            for j, o in enumerate(self.bars):
                if j == i:
                    continue
                if not o.vertical and o.lo <= v <= o.hi and REACH_UP_MIN <= b.y - o.y <= REACH_UP_MAX:
                    out.append((("H", j, o.snap(v)), T_REACH_UP, ("reach_up", j, o.snap(v))))
                hy = b.y - STAND_HOVER - CONN
                if o.vertical and abs(o.x - v) < STEP and o.lo <= hy <= o.hi:
                    out.append((("V", j, o.snap(hy)), T_CROSS, ("stand_to_v", j, o.snap(hy))))
            self._stand_jumps(spot, i, out)
            self._drop_to_floor(spot, i, out)
        return out

    def _along(self, spot, b, i, speed, act, out):
        k, _, v = spot
        s = b.samples
        j = s.index(v)
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(s):
                out.append(((k, i, s[jj]), abs(s[jj] - v) / speed, (act, i, s[jj])))

    def _crossings_from_v(self, i, b, y, out):
        """竖杆和横杆相交处转杆。"""
        for j, o in enumerate(self.bars):
            if o.vertical or not (o.x0 - 1.0 <= b.x <= o.x1 + 1.0):
                continue
            if abs(o.y - y) < STEP * 0.5:
                out.append((("H", j, o.snap(b.x)), T_CROSS, ("v_to_hang", j, o.snap(b.x))))
            if abs((o.y - STAND_HOVER - CONN) - y) < STEP * 0.5:
                out.append((("S", j, o.snap(b.x)), T_CROSS, ("v_to_stand", j, o.snap(b.x))))

    def _stand_jumps(self, spot, i, out):
        for h in JUMP_HOLDS:
            for md in MOVE_DIRS:
                self._flight(spot, ("standjump", h, md), get_free_jump_arc(self.stats, h, md), i, out)

    def _drop_to_floor(self, spot, i, out):
        """松手落到地上。"""
        hx, hy = self.head(spot)
        tab = _table(get_drop_arc(self.stats, 0))
        c = tab.cross(False, self.HL - LAND_H - hy)
        if not c:
            return
        t, dx = c[0]
        x = hx + dx
        if tab.inside(t, hx, hy, self.WL) and self._safe_landing(tab, t):
            out.append((("F", -1, round(x)), T_SETUP + t + T_SETTLE, ("fall", ("drop", 0), None)))

    def _safe_landing(self, tab, t):
        """落地不会摔晕。"""
        return tab.vy_at(t) < self.stats.fall_stun_speed * SAFE_FALL

    # 飞行

    def _first_catch(self, tab, hx, hy, skip):
        best = None
        bx0, bx1, by0, by1 = tab.box
        bx0, bx1, by0, by1 = hx + bx0 - V_TOL, hx + bx1 + V_TOL, hy + by0 - 1.0, hy + by1 + 1.0
        for j, b in enumerate(self.bars):
            if j == skip or b.x1 + H_TOL < bx0 or b.x0 - H_TOL > bx1 or b.y1 < by0 or b.y0 > by1:
                continue
            if b.vertical:
                for t, dy in tab.cross(True, b.x - hx):
                    y = hy + dy
                    if t >= CATCH_MIN_T and b.y0 <= y <= b.y1:
                        if best is None or t < best[0]:
                            best = (t, ("V", j, b.snap(min(max(y, b.lo), b.hi))))
                        break
                if abs(b.x - hx) <= V_TOL:
                    for edge in (b.y1, b.y0):
                        for t, dx in tab.cross(False, edge - hy):
                            if t >= CATCH_MIN_T and abs(hx + dx - b.x) <= V_TOL:
                                if best is None or t < best[0]:
                                    best = (t, ("V", j, b.snap(min(max(edge, b.lo), b.hi))))
                                break
            else:
                for t, dx in tab.cross(False, b.y - hy):
                    x = hx + dx
                    if t >= CATCH_MIN_T and b.x0 - H_TOL <= x <= b.x1 + H_TOL:
                        if best is None or t < best[0]:
                            best = (t, ("H", j, b.snap(x)))
                        break
        return best

    def _flight(self, spot, launch, arc, skip, out):
        """从 spot 起跳或松手后抓到的第一根杆或落地点。"""
        hx, hy = self.head(spot)
        tab = _table(arc)
        hit = self._first_catch(tab, hx, hy, skip)
        if hit is not None:
            t, dst = hit
            if tab.inside(t, hx, hy, self.WL):
                out.append((dst, (T_SETUP + t + T_SETTLE) * JUMP_K + JUMP_PAD, ("fly", launch, dst)))
            return
        if launch[0] == "drop":
            return  # 落地的松手由 _drop_to_floor 给
        c = tab.cross(False, self.HL - LAND_H - hy)
        if c:
            t, dx = c[-1]
            if tab.inside(t, hx, hy, self.WL) and self._safe_landing(tab, t):
                dst = ("F", -1, round(hx + dx))
                out.append((dst, (T_SETUP + t + T_SETTLE) * JUMP_K + JUMP_PAD, ("fly", launch, None)))

    # 地面

    def floor_jumps(self):
        """从地上跳起抓杆：[(起跳 x, 起跳方式, 抓到的位置, 耗时)]。"""
        if self._floor_jumps is not None:
            return self._floor_jumps
        out = []
        fy = self.HL - self.floor_h
        for h in JUMP_HOLDS:
            for md in MOVE_DIRS:
                arc = get_arc(self.stats, h, md)
                tab = _table(arc)
                for j, b in enumerate(self.bars):
                    if b.vertical and b.grounded:
                        continue
                    for lx in self._floor_launches(tab, b, fy, md):
                        if not (self.walk_lo <= lx <= self.walk_hi):
                            continue
                        hit = self._first_catch(tab, lx, fy, -1)
                        if hit is None or not tab.inside(hit[0], lx, fy, self.WL):
                            continue
                        cost = (T_SETUP + hit[0] + T_SETTLE) * JUMP_K + JUMP_PAD
                        out.append((round(lx), ("floorjump", h, md), hit[1], cost))
        self._floor_jumps = out
        return out

    def _floor_launches(self, tab, b, fy, md):
        """这条弧能抓到杆 b 的起跳 x。"""
        if b.vertical:
            if md == 0:
                return [b.x]
            c = tab.cross(False, b.y1 - fy)
            return [b.x - dx for t, dx in c[:1]]
        c = tab.cross(False, b.y - fy)
        if not c:
            return []
        dx = c[0][1]
        picks = {b.lo, (b.lo + b.hi) * 0.5, b.hi}
        return [x - dx for x in picks]

    def _floor_edges(self, x, out):
        for j, b in enumerate(self.bars):
            if b.vertical and b.grounded:
                cost = abs(b.x - x) / tuning.PLAN_WALK_SPEED + T_GRAB
                out.append((("V", j, b.samples[-1]), cost, ("grab_v", j)))
        for lx, launch, dst, cost in self.floor_jumps():
            walk = abs(lx - x) / tuning.PLAN_WALK_SPEED
            out.append((dst, walk + cost, ("floor_fly", lx, launch, dst)))

    # 目标

    def touch(self, spot, gx, gy):
        """从 spot 够到 (gx, gy) 的最省办法：(耗时, 动作)；够不着 None。"""
        k = spot[0]
        hx, hy = self.head(spot)
        if k == "F":
            return None
        best = self._touch_here(spot, gx, gy)
        if not self._in_envelope(k, gx - hx, gy - hy):
            return best
        launches = self._launches(k)
        r = tuning.GRAB_REACH - TOUCH_FLY_MARGIN
        r2 = r * r
        for launch, arc in launches:
            tab = _table(arc)
            ex, ey = gx - hx, gy - hy
            x0, x1, y0, y1 = tab.box
            if not (x0 - r <= ex <= x1 + r and y0 - r <= ey <= y1 + r):
                continue
            for t in range(1, tab.n):
                dx, dy = ex - tab.xs[t], ey - tab.ys[t]
                if dx * dx + dy * dy <= r2:
                    if tab.inside(t, hx, hy, self.WL):
                        c = (T_SETUP + t) * JUMP_K
                        if best is None or c < best[0]:
                            best = (c, ("touchfly", launch))
                    break
        return best

    def _launches(self, k):
        if k in ("T", "S"):
            return [
                (("standjump", h, md), get_free_jump_arc(self.stats, h, md))
                for h in JUMP_HOLDS
                for md in MOVE_DIRS
            ]
        if k == "V":
            out = [(("polejump", d), get_pole_jump_arc(self.stats, d)) for d in (1, -1)]
            return out + [(("drop", 0), get_drop_arc(self.stats, 0))]
        return [(("drop", md), get_drop_arc(self.stats, md)) for md in MOVE_DIRS]

    def _in_envelope(self, k, ex, ey):
        """目标落在这类位置的起跳弧范围里。"""
        box = self._env.get(k)
        if box is None:
            boxes = [_table(a).box for _, a in self._launches(k)]
            r = tuning.GRAB_REACH
            box = self._env[k] = (
                min(b[0] for b in boxes) - r,
                max(b[1] for b in boxes) + r,
                min(b[2] for b in boxes) - r,
                max(b[3] for b in boxes) + r,
            )
        return box[0] <= ex <= box[1] and box[2] <= ey <= box[3]

    def floor_reach(self):
        """从地上出发能到的所有杆上位置。"""
        if self._floor_reach is None:
            start = ("F", -1, round((self.walk_lo + self.walk_hi) * 0.5))
            seen = {start}
            todo = [start]
            while todo:
                for dst, _, _ in self.edges(todo.pop()):
                    if dst not in seen:
                        seen.add(dst)
                        todo.append(dst)
            self._floor_reach = [s for s in seen if s[0] != "F"]
        return self._floor_reach

    def _maybe_touchable(self, gx, gy):
        """从地上出发有没有可能够到 (gx, gy)。"""
        for s in self.floor_reach():
            hx, hy = self.head(s)
            if math.hypot(gx - hx, gy - hy) <= TOUCH_R + STEP or self._in_envelope(s[0], gx - hx, gy - hy):
                return True
        return False

    def reach_gap(self, k, b, gx, gy):
        """在这根杆上离目标最近时还差多远。"""
        if k == "T":
            hx, hy = b.x, b.y0 - TIP_HOVER - CONN
            return math.hypot(gx - hx, gy - hy)
        if k == "V":
            c = min(max(gy, b.lo), b.hi)
            return math.hypot(gx - (b.x + math.copysign(SIDE_OFF, gx - b.x)), gy - c)
        c = min(max(gx, b.lo), b.hi)
        hy = b.y if k == "H" else b.y - STAND_HOVER - CONN
        return math.hypot(gx - c, gy - hy)

    def _touch_here(self, spot, gx, gy):
        """在这根杆上挪到最近处就够得着：(耗时, 动作)。"""
        k, i, v = spot
        b = self.bars[i]
        if k == "T":
            hx, hy = self.head(spot)
            return (0.0, ("reach",)) if math.hypot(gx - hx, gy - hy) <= TOUCH_R else None
        if k == "V":
            c = min(max(gy, b.lo), b.hi)
            d = math.hypot(gx - (b.x + math.copysign(SIDE_OFF, gx - b.x)), gy - c)
            speed = self.up
        else:
            c = min(max(gx, b.lo), b.hi)
            hy = b.y if k == "H" else b.y - STAND_HOVER - CONN
            d = math.hypot(gx - c, gy - hy)
            speed = self.shimmy if k == "H" else self.walk
        if d > TOUCH_R or abs(c - v) > STEP * 0.5 + 1.0:
            return None
        return abs(c - v) / speed, ("reach",)

    def _wet(self, rain, spot):
        """大雨时这个位置露天。"""
        return rain.keeps_out(*self.head(spot))

    def reach_costs(self, start, limit, target=None, rain=None):
        """耗时 limit 内能到的位置：({位置: 耗时}, {位置: (上一位置, 动作)})；到 target 就停；给了 rain 时大雨里不经过露天的位置。"""
        dist = {start: 0.0}
        came = {}
        heap = [(0.0, start)]
        any_floor = target is not None and target[0] == "F" and target[2] is None
        n = 0
        while heap and n < MAX_EXPAND:
            g, s = heapq.heappop(heap)
            if g > dist.get(s, math.inf):
                continue
            if target is not None and s != start and (s == target or (any_floor and s[0] == "F")):
                break
            n += 1
            for dst, cost, act in self.edges(s):
                ng = g + cost
                if ng <= limit and ng < dist.get(dst, math.inf):
                    if rain is not None and self._wet(rain, dst):
                        continue
                    dist[dst] = ng
                    came[dst] = (s, act)
                    heapq.heappush(heap, (ng, dst))
        return dist, came

    @staticmethod
    def path_to(came, start, target):
        """reach_costs 记下的路线：[(位置, 动作)]；到不了 None。"""
        if target != start and target not in came:
            return None
        path = []
        s = target
        while s != start:
            prev, act = came[s]
            path.append((s, act))
            s = prev
        path.reverse()
        return path

    def route_to(self, start, target, limit=math.inf):
        """到 target 的路线；到不了 None。"""
        dist, came = self.reach_costs(start, limit, target)
        if target[0] == "F" and target[2] is None:
            floors = [s for s in dist if s[0] == "F" and s != start]
            if not floors:
                return None
            target = min(floors, key=lambda s: dist[s])
        return self.path_to(came, start, target)

    def search(self, start, gx, gy, rain=None):
        """A*：够着 (gx, gy) 的路线和总耗时；找不到 None；给了 rain 时大雨里不经过露天的位置。"""
        if start is None:
            return None
        if start[0] == "F" and not self._maybe_touchable(gx, gy):
            return None
        h0 = H_WEIGHT / H_SPEED

        def hcost(s):
            x, y = self.head(s)
            return max(0.0, math.hypot(gx - x, gy - y) - TOUCH_R) * h0

        openq = [(hcost(start), 0.0, start)]
        best_g = {start: 0.0}
        came = {}
        goal = None
        n = 0
        while openq and n < MAX_EXPAND:
            f, g, s = heapq.heappop(openq)
            if g > best_g.get(s, math.inf):
                continue
            if s == ("goal",):
                goal = g
                break
            n += 1
            tc = self.touch(s, gx, gy)
            if tc is not None:
                ng = g + tc[0]
                if ng < best_g.get(("goal",), math.inf):
                    best_g[("goal",)] = ng
                    came[("goal",)] = (s, tc[1])
                    heapq.heappush(openq, (ng, ng, ("goal",)))
            for dst, cost, act in self.edges(s):
                ng = g + cost
                if ng < best_g.get(dst, math.inf):
                    if rain is not None and self._wet(rain, dst):
                        continue
                    best_g[dst] = ng
                    came[dst] = (s, act)
                    heapq.heappush(openq, (ng + hcost(dst), ng, dst))
        if goal is None:
            return None
        path = []
        s = ("goal",)
        while s != start:
            prev, act = came[s]
            path.append((s, act))
            s = prev
        path.reverse()
        return path, goal


def _walk_band(pet):
    b = pet.body
    lo = 0.0 if getattr(b, "walk_min", None) is None else b.walk_min
    hi = pet._WL if getattr(b, "walk_max", None) is None else b.walk_max
    return lo, hi


def bars_of(pet):
    items = getattr(pet, "items_affording", None)
    objs = items(CLIMBABLE) if items is not None else getattr(pet, "poles", ())
    return [Bar(o, pet._HL) for o in objs]


def map_for(pet):
    """这只猫眼下的杆网。"""
    gv = (
        getattr(pet, "geometry_version", 0),
        pet._WL,
        pet.cat.stats,
    )
    cm = getattr(pet, "_climb_map", None)
    if cm is None or cm[0] != gv:
        cm = (gv, ClimbMap(pet, bars_of(pet)))
        pet._climb_map = cm
    return cm[1]


def locate(cm, pet):
    """猫眼下在哪个位置；定不下来时 None。"""
    b = pet.body
    anim = b.animation
    c0, c1 = b.chunk0, b.chunk1
    if b.on_pole:
        px = getattr(b, "pole_x", c0.x)
        if anim in ("ClimbOnBeam", "BeamTip"):
            y = c0.y if anim == "ClimbOnBeam" else c1.y
            best = None
            for j, o in enumerate(cm.bars):
                if not o.vertical or abs(o.x - (px if anim == "ClimbOnBeam" else c1.x)) >= 3.0:
                    continue
                d = abs(o.y0 - y) if anim == "BeamTip" else max(0.0, o.y0 - y, y - o.y1)
                if d <= V_TOL and (best is None or d < best[0]):
                    best = (d, j, o)
            if best is None:
                return None
            _, j, o = best
            return ("V", j, o.snap(c0.y)) if anim == "ClimbOnBeam" else ("T", j, 0.0)
        for j, o in enumerate(cm.bars):
            if not o.vertical and o.x0 - H_TOL <= px <= o.x1 + H_TOL:
                if anim in ("HangFromBeam", "GetUpOnBeam") and abs(o.y - getattr(b, "pole_y", c0.y)) < 3.0:
                    return ("H", j, o.snap(px))
                if anim == "StandOnBeam" and abs(o.y - STAND_HOVER - c1.y) < 4.0:
                    return ("S", j, o.snap(c1.x))
        return None
    if b.on_floor() and not b.swimming:
        return ("F", -1, round(c1.x))
    return None
