"""地上过路的规划：从一排停住的猫跟前起步，找一串走（可退后助跑）、跳（可走着跳、可踩趴着的猫背）的动作落到这排后面，
每一跳按弧线逐点查两节身子碰不碰到猫，挑代价最小的。规划只读 snapshot 取整后的样子，样子就是缓存的键，
所以「这排能不能过」和照着走的动作是同一份答案。"""

from __future__ import annotations

import heapq
import math
from collections import namedtuple

from ...core.chunkphys import GRAVITY
from ...core.stride import HOP, STAND, TO, WAIT, WALK
from ...planning.jump_arc import get_arc, get_walk_hop_arc
from .space import FLOOR, POLE, TOUCH_TOL, extent, lie_extent, stand_half

GEARS = (3, 6)  # 起跳的持跳档
STEP = 6.0  # 地上候选位置的间隔，也是一跳至少要往前进的距离
WALK_V = 3.5  # 估算走路耗时用的速度
BACK_COST = 2.0  # 往后退的耗时倍数
BRAKE = 3.0  # 走着停下再起跳多花的耗时
TURN = 20.0  # 回头一次的代价
HOP_COST = 6.0
STEP_ON = 60.0  # 踩到趴着的猫背上一次的代价
STEP_ON_HEAD = 200.0  # 踩到站着的猫头上一次的代价：别的走法都不行才用
YIELD_COST = 25.0  # 叫一只猫让的代价
YIELD_WAIT = 15.0  # 等它让好的耗时
MAX_COST = 300.0  # 过一排的代价超过这么多（比如要接连踩三只猫）就当过不去
CLEAR = 3.0  # 跳过猫时两节身子和它至少留这么远
HEADROOM = 12.0  # 站着的猫头顶往上这么高也算它占的
SKIP = 2  # 起跳头几 tick 还贴着地，不查碰撞
TAKEOFF_SLOP = 4.0  # 执行到起跳点的精度：一跳在前后差这么多时也要照样往前、落得稳
ANCHOR_GAP = 8.0  # 在一排跟前站定起步时离它这么远
RUNUP_TICKS = 3  # 从站定起走这么多 tick 才接近走路速度
EXTEND = 60  # 从猫背上往下跳时弧线往下续这么多 tick
KEY_STEP = 4.0  # 样子里的位置按这么粗取整：停着的猫被挤动一点不重算（CLEAR、TAKEOFF_SLOP 盖得住这点差）

# 路上的一只停住的猫：身子的圆（站着的最后一个是头顶留空）、左右范围、趴平没有；alt 是叫它让开的 (指令, 方向, 让开后的 Ob 或 None)
Ob = namedtuple("Ob", "circles lo hi lying alt")
# 走法：steps 交给身体执行（core/stride.py），到第一跳为止；yields 是 [(要让的猫, 指令, 方向)]
Plan = namedtuple("Plan", "steps yields cost")
_PROFILES = {}  # (弧, 往下续没有) → 臀、头位移和横向范围


def gait(stats):
    """(走路速度, 从站定起走到接近它要走过的距离)：走路速度取走着起跳第一 tick 的位移。"""
    v = abs(get_walk_hop_arc(stats, GEARS[0], 1).hips[0][0])
    return v, v * RUNUP_TICKS


def lead(body, d):
    """走着过来时离一排多远起就得照走法走：跳得到它再加一段助跑。"""
    return _reach(body, d) + gait(body.stats)[1]


def near_edge(row, d):
    return min(o.lo for o in row) if d > 0 else max(o.hi for o in row)


def anchor(space, me, d, row, walking=False):
    """起步处：站定的隔 ANCHOR_GAP，走着过来的从 lead 远处起；身后的猫或走路范围的边挡着就贴着它；夹得站不下 None。"""
    b, (lo, hi) = me.body, space.band(me)
    half, near = stand_half(b), near_edge(row, d)
    x = min(max(near - d * (lead(b, d) if walking else (half + ANCHOR_GAP)), lo), hi)
    for o in space.parked(me):
        back = extent(o, d)[d > 0] + d * (half + CLEAR)
        if o not in row and ((o.lo + o.hi) * 0.5 - near) * d < 0.0 and (back - x) * d > 0.0:
            x = back
    return x if (near - d * half - x) * d >= 0.0 else None


def _reach(body, d):
    """离这排多远以内才可能跳过去。"""
    return get_walk_hop_arc(body.stats, GEARS[-1], d).points[-1][0] * d + 20.0


def snapshot(space, me, d, row, glo, ghi, walking=False, under=None):
    """规划看到的样子：(键, 起步处, 范围里停住的猫)。起步处见 anchor，踩在这排猫背上或夹着站不下时是现在的位置；
    范围是这排前后跳得到、加上助跑的地方；落脚段里别人预约的地方不能落。都按 KEY_STEP 取整。"""
    b = me.body
    on = under if under in [m.pet for m in row] else None
    x0 = anchor(space, me, d, row, walking) if on is None else None
    x0 = b.chunk1.x if x0 is None else x0
    near = near_edge(row, d)
    lo, hi = sorted((near - d * (lead(b, d) + 20.0), near_edge(row, -d) + d * (_reach(b, d) + 20.0)))
    occs = [o for o in space.parked(me) if (e := extent(o, d))[1] > lo and e[0] < hi]
    occs.sort(key=lambda o: o.lo)
    obs = tuple(space.memo(("ob", o.pet, d, o in row), lambda o=o: _ob(space, o, d, o in row)) for o in occs)
    ends = tuple(_q(min(max(v, lo), hi)) for v in (x0, near, glo, ghi, *space.band(me)))
    on = next((i for i, o in enumerate(occs) if o.pet is on), None)
    pad = stand_half(b) - TOUCH_TOL
    booked = tuple((_q(a - pad), _q(c + pad)) for a, c in space.booked(me) if a - pad < ghi and c + pad > glo)
    return (obs, ends, on, d, walking, booked, _q(b.H), id(b.stats)), x0, occs


def _q(v):
    return round(v / KEY_STEP) * KEY_STEP


def _ob(space, o, d, ask):
    """一只停住的猫在规划里的样子：地上的按变完的样子（站直或趴平），占的范围按 space.extent；这排里（ask）叫得动的
    带上让开后的样子：地上站着的朝 d 趴下（不伸到对方脚下，趴得下才算），低处杆上的挪走。"""
    b = o.pet.body
    c0, c1 = b.chunk0, b.chunk1
    if o.pose == FLOOR and b.standing:
        circles, flat = _standing(b, c1.x, c0.x), False
    elif o.pose == FLOOR:
        circles, flat = _lying(b, c1.x, b.facing or 1), True
    else:
        flat = b.lying_flat()
        head = [] if flat else [(c0.x, min(c0.y, c1.y) - HEADROOM, c0.rad)]
        circles = [(c.x, c.y, c.rad) for c in (c0, c1)] + head
    alt, ask = None, ask and o.can
    if ask and o.pose == POLE and o.lane is not None and o.lane[0] in ("V", "H"):
        alt = ("clear", -1, None) if o.lane[0] == "V" else ("swap", d, None)
    elif ask and o.pose == FLOOR and not o.lying and o.d in (0, -d):
        lo, hi = lie_extent(b, o.x, d)
        if space.free(o.pet, lo, hi, parked=True):
            alt = ("lie", d, _shape(_lying(b, o.x, d), lo, hi, True, None))
    return _shape(circles, *extent(o, d), flat, alt)


def _shape(circles, lo, hi, flat, alt):
    return Ob(tuple((_q(x), _q(y), r) for x, y, r in circles), _q(lo), _q(hi), flat, alt)


def _standing(b, x, hx):
    """臀在 x、头在 hx 站着时两节身子的圆（头按站直的高度），头顶再加一圈留空。"""
    r0, r1 = b.chunk0.rad, b.chunk1.rad
    top = b.H - r1 - b.conn_rest
    return [(x, b.H - r1, r1), (hx, top, r0), (hx, top - HEADROOM, r0)]


def _lying(b, x, d):
    """臀在 x、朝 d 趴平时两节身子的圆。"""
    return [(x, b.H - b.chunk1.rad, b.chunk1.rad), (x + d * b.conn_rest, b.H - b.chunk0.rad, b.chunk0.rad)]


def _top(o):
    return min(cy - r for _, cy, r in o.circles[:2])


def plan(key, body):
    """按 snapshot 的样子规划：Plan（yields 里是第几只猫）或 None。叫猫让开整体算一种走法，比不叫的省才用。"""
    obs, ends, on, d, walking, booked = key[:6]
    ctx = _Ctx(body, d, ends, on, walking, booked)
    best = ctx.search(obs, ())
    if walking or (best is not None and best.cost <= YIELD_COST + YIELD_WAIT + HOP_COST):
        return best
    swapped, yields = list(obs), []
    for i, o in enumerate(obs):
        after = o.alt and o.alt[2]
        clash = after and any(_overlap(after, swapped[j]) for j, *_ in yields)  # 趴下的两两不能压着
        if o.alt is not None and i != on and not clash:  # 踩着的不叫
            swapped[i] = after
            yields.append((i, *o.alt[:2]))
    alt = ctx.search(swapped, yields) if yields else None
    return alt if alt is not None and (best is None or alt.cost < best.cost) else best


class _Ctx:
    """一次规划的场面：谁、往哪、从哪起、落到哪段、能走的范围。"""

    def __init__(self, body, d, ends, on, walking, booked):
        self.body, self.d, self.on, self.walking, self.booked = body, d, on, walking, booked
        self.x0, self.near, self.glo, self.ghi, self.blo, self.bhi = ends
        self.reach = _reach(body, d)
        self.cruise, self.runup = gait(body.stats)
        self.half = stand_half(body)
        arcs = {(w, g): (get_walk_hop_arc if w else get_arc)(body.stats, g, d) for w in (0, 1) for g in GEARS}
        self.land = {k: abs(a.hips[-1][0]) for k, a in arcs.items()}  # 平地上一跳落多远
        self.least = min(len(a.hips) for a in arcs.values()) - SKIP  # 一跳最少要的 tick

    def search(self, obs, yields):
        """Dijkstra，找到的路上有落不稳的跳就换掉它重找；返回 Plan 或 None。要让的只留第一跳跨过、落到的（往后的落地后再叫）。"""
        self.obs, flights = obs, {}
        live = [(i, o) for i, o in enumerate(obs) if o is not None]
        while (res := self._dijkstra(live, flights)) is not None:
            bad = [h[0] for h in res[2] if not self._steady(live, *h)]
            if not bad:
                break
            flights.update(dict.fromkeys(bad))
        if res is None:
            return None
        steps, cost, _ = res
        take = steps[-2][1] if len(steps) > 1 and steps[-2][0] == TO else self.x0
        a, c = sorted((take, steps[-1][3]))
        a, c = a - self.half, c + self.half
        ys = [y for y in yields if obs[y[0]] is None or (obs[y[0]].hi > a and obs[y[0]].lo < c)]
        if ys:
            steps, cost = [(WAIT,), *steps], cost + YIELD_COST * len(ys) + YIELD_WAIT
        return Plan(steps, ys, cost)

    def _dijkstra(self, live, flights):
        """一跳先按它最少的代价进堆，轮到它时才算弧线、按实际落点和代价放回；够不着这排的跳不算。"""
        d = self.d
        start = ("c", self.on, _cell(self.x0)) if self.on is not None else ("f", _cell(self.x0), self.walking)
        pos, dist, came = {start: self.x0}, {start: 0.0}, {}
        heap = [(0.0, 0, start, None)]
        tie = 0
        while heap:
            g, _, node, hop = heapq.heappop(heap)
            if g > MAX_COST:
                return None
            if hop is not None:
                res = self._hop(*hop, live, flights)
                if res is not None:
                    src, (cost, nxt, nx, edge, info) = hop[0], res
                    ng = dist[src] + cost
                    if ng < dist.get(nxt, math.inf):
                        dist[nxt], pos[nxt], came[nxt] = ng, nx, (src, edge, ng, info)
                        tie += 1
                        heapq.heappush(heap, (ng, tie, nxt, None))
                continue
            if g > dist.get(node, math.inf):
                continue
            x = pos[node]
            if node[0] == "f" and self.glo <= x <= self.ghi and node is not start and self._free(x):
                return _steps(came, node, self.x0)
            if (x - self.ghi) * d > 0.0:
                continue  # 跳过了落脚段：只能往前跳，回不来
            fwd = node in came and came[node][1][0] == TO and (x - pos[came[node][0]]) * d > 0.0
            for k, mv, cost in () if node[0] != "f" or fwd else self._walks(node, x, live):
                nxt = ("f", _cell(k), mv)
                if g + cost < dist.get(nxt, math.inf):
                    dist[nxt], pos[nxt], came[nxt] = g + cost, k, (node, (TO, k), g + cost, None)
                    tie += 1
                    heapq.heappush(heap, (g + cost, tie, nxt, None))
            for gear in GEARS:
                if node[0] == "c" or (self.near - x) * d <= self.land[node[2], gear]:
                    tie += 1
                    heapq.heappush(heap, (g + HOP_COST + self.least, tie, None, (node, x, gear)))
        return None

    def _free(self, x):
        return not any(a < x < c for a, c in self.booked)

    def _hop(self, node, x, gear, live, flights):
        """从 node（地上 x 或猫背上）用这档起跳：(代价, 落点节点, 落点 x, 边, 复核稳不稳要的信息)；撞猫或没往前进 None。"""
        d, body = self.d, self.body
        if node[0] == "f":
            walk, ob, hip0 = node[2], None, body.H - body.chunk1.rad
        else:
            walk, ob = False, node[1]
            hip0 = _top(self.obs[ob]) - body.chunk1.rad
        arc = get_walk_hop_arc(body.stats, gear, d) if walk else get_arc(body.stats, gear, d)
        key = (node[0], node[1] if ob is not None else walk, round(x, 1), gear)
        if key not in flights:
            flights[key] = self._fly(x, hip0, arc, live, ob)
        res = flights[key]
        if res is None or (res[1] - x) * d < STEP:
            return None
        kind, lx, ticks, hit = res
        lying = hit is not None and self.obs[hit].lying
        cost = ticks + HOP_COST + ((STEP_ON if lying else STEP_ON_HEAD) if kind == "c" else 0.0)
        nxt = ("f", _cell(lx), True) if kind == "f" else ("c", hit, _cell(lx))
        edge = (HOP, gear, d, lx, "floor" if kind == "f" else "cat", WALK if walk else STAND)
        return cost, nxt, lx, edge, (key, x, hip0, arc, ob, walk, res)

    def _walks(self, node, x, live):
        """从地上 x 往前后走到起跳窗口（跳得到这排再加一段助跑）里的各格：[(x, 到时是不是走路速度, 代价)]。"""
        d = self.d
        lo, hi = _clear(x, self.half, live)
        s0, s1 = sorted((self.near, self.near - d * (self.reach + self.runup)))
        k = max(s0, lo, self.blo)
        while k <= min(s1, hi, self.bhi):
            dx = k - x
            if abs(dx) >= STEP * 0.5:
                fwd = dx * d > 0.0
                cost = abs(dx) / WALK_V * (1.0 if fwd else BACK_COST) + (0.0 if fwd else TURN)
                if fwd and (dx * d >= self.runup or node[2]):
                    yield k, True, cost
                yield k, False, cost + BRAKE
            k += STEP

    def _steady(self, live, key, x, hip0, arc, ob, walk, res):
        """起跳点差出执行误差（站定跳前后 TAKEOFF_SLOP，走着跳往前一 tick 的路）也照样往前、落在地上或同一处猫背上。"""
        lo, hi = _clear(x, self.half, live) if ob is None else (-math.inf, math.inf)
        if walk and not lo <= x + self.d * self.cruise <= hi:
            return False
        for dx in (0.0, self.d * self.cruise) if walk else (-TAKEOFF_SLOP, TAKEOFF_SLOP):
            if lo <= x + dx <= hi:
                alt = self._fly(x + dx, hip0, arc, live, ob)
                if alt is None or (alt[1] - x - dx) * self.d < STEP:
                    return False
                if not (alt[0] == "f" or self.obs[alt[3]].lying or (alt[0] == res[0] and alt[3] == res[3])):
                    return False
        return True

    def _fly(self, x0, hip_y0, arc, live, standing_on):
        """臀从 (x0, hip_y0) 起沿弧飞：落地 ("f", x, tick, None)、落到趴着的猫背上或往下落到站着的猫头上
        ("c", x, tick, 第几只)，碰到猫 None。起跳时挨着的猫（地上起跳只算身后的）头几 tick 不算碰。"""
        body = self.body
        r0, r1 = body.chunk0.rad, body.chunk1.rad
        hips, heads, xmin, xmax = _profile(arc, standing_on is not None)
        hy0 = hip_y0 - body.conn_rest
        pad = max(r0, r1) + CLEAR
        near = [(i, o) for i, o in live if o.hi > x0 + xmin - pad and o.lo < x0 + xmax + pad]
        back = [(i, o) for i, o in near if standing_on is not None or (o.lo + o.hi - 2.0 * x0) * self.d < 0.0]
        touching = {i for i, o in back if _touches(o, x0, hip_y0, hy0, r0, r1)} | {standing_on}
        for k in range(min(len(hips), len(heads))):
            px, py = hips[k]
            x, hip = x0 + px, hip_y0 + py
            qx, qy = heads[k]
            hx, head = x0 + qx, hy0 + qy
            if k >= SKIP and hip + r1 >= body.H:
                return "f", x, k + 1, None
            left, right = min(x, hx) - pad, max(x, hx) + pad
            for i, o in near:
                if o.hi < left or o.lo > right or (i in touching and k < SKIP + 4):
                    continue
                for cx, cy, cr in o.circles:
                    if k >= SKIP and (hx - cx) ** 2 + (head - cy) ** 2 < (r0 + cr + CLEAR) ** 2:
                        return None
                    if (x - cx) ** 2 + (hip - cy) ** 2 < (r1 + cr + CLEAR) ** 2:
                        if k < SKIP:
                            continue
                        falling = k > 0 and py > hips[k - 1][1]
                        if hip < cy and i != standing_on and (o.lying or (falling and cy < _top(o) + cr)):
                            return "c", x, k + 1, i
                        return None
        if standing_on is None and hips:
            return "f", x0 + hips[-1][0], len(hips), None  # 弧线本来就停在落地那一刻
        return None


def _overlap(a, b):
    return b is not None and a.lo + TOUCH_TOL < b.hi and b.lo < a.hi - TOUCH_TOL


def _touches(o, x, hip, head, r0, r1):
    return any(
        (x - cx) ** 2 + (hip - cy) ** 2 < (r1 + cr + CLEAR) ** 2
        or (x - cx) ** 2 + (head - cy) ** 2 < (r0 + cr + CLEAR) ** 2
        for cx, cy, cr in o.circles
    )


def _profile(arc, down):
    """弧线的臀、头位移和横向范围；down 时末尾往下续（从高处往下跳）。按弧缓存。"""
    k = (id(arc), down)
    if k not in _PROFILES:
        hips, heads = (_extend(arc.hips), _extend(arc.points)) if down else (arc.hips, arc.points)
        xs = [px for px, _ in hips] + [qx for qx, _ in heads]
        _PROFILES[k] = hips, heads, min(xs), max(xs)
    return _PROFILES[k]


def _extend(pts):
    """弧线末尾按最后的速度加重力往下续。"""
    pts = list(pts)
    if len(pts) >= 2:
        vx, vy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        px, py = pts[-1]
        for _ in range(EXTEND):
            vy += GRAVITY
            px, py = px + vx, py + vy
            pts.append((px, py))
    return pts


def _cell(x):
    return round(x / STEP)


def _clear(x, half, live):
    """从 x 起在地上能走到的范围：左右各到第一只猫跟前；已经贴着的那侧就不往那边走。"""
    lo, hi = -math.inf, math.inf
    for _, o in live:
        if (o.lo + o.hi) * 0.5 < x:
            lo = max(lo, min(o.hi + half + CLEAR, x))
        else:
            hi = min(hi, max(o.lo - half - CLEAR, x))
    return lo, hi


def _steps(came, node, x0):
    """路线上的边串成步骤，到第一跳为止；同方向连着走的并成一步。返回 (步骤, 代价, 路上每一跳的复核信息)。"""
    cost = came[node][2]
    edges = []
    while node in came:
        node, *e = came[node]
        edges.append(e)
    out = []
    for e, _, _ in reversed(edges):
        if e[0] == TO and out and out[-1][0] == TO:
            prev = out[-2][1] if len(out) >= 2 and out[-2][0] == TO else x0
            if (e[1] - out[-1][1]) * (out[-1][1] - prev) > 0.0:
                out[-1] = e
                continue
        out.append(e)
        if e[0] == HOP:
            break
    return out, cost, [info for _, _, info in edges if info is not None]
