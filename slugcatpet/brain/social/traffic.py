"""通行：把猫按通道排开，找出谁挡谁的路，决定谁让、怎么过。"""

from __future__ import annotations

import math

from ... import tuning
from ..state import CROWD

LEAD = 10  # 按对方速度提前这么多 tick 开始让
CONTACT = {"F": 24.0, "W": 26.0, "H": 22.0, "S": 22.0, "V": 40.0, "Z": 22.0}  # 通道上两只猫挨上的距离
WATER_BAND = 26.0  # 水里上下相差这么多以内才会挡路
GROUND_BAND = 40.0  # 脚离地这么近也算在地上
HOP_DIST = 44.0  # 离挡路的猫这么近时跨过去
HOP_HOLD = 6  # 跨越的持跳 tick
HOP_COOLDOWN = 20
SWIM_TURN = 0.35  # 想游方向的横向分量超过此值才算往一边游
PATIENCE = 60  # 杆上被挡停这么久还过不去就不走了
SHOVE_TICKS = 20  # 顶着杆尖上的猫往上挤这么久就把它顶下去
SHOVE_FALL_VX = 3.5  # 被顶下去时的横向速度
SHOVE_GHOST = 45  # 被顶下去后穿过别的猫的 tick，免得和杆上的猫撞翻
REST_TICKS = 10  # 被别的猫托着不动这么久就滑下来
REST_SPEED = 1.2
SLIP_VX = 2.5  # 滑下来时的横向速度
SLIP_GHOST = 10  # 滑下来时穿过别的猫的 tick
YIELD = ("lie", "swap", "clear", "stop")  # 由让路状态执行的指令


class Order:
    """让路指令：kind 见 YIELD，by 是对方，dir 是对方的去向。"""

    __slots__ = ("kind", "by", "dir")

    def __init__(self, kind, by, d):
        self.kind = kind
        self.by = by
        self.dir = d


class _Rec:
    __slots__ = ("pet", "lane", "s", "y", "d", "v", "goal", "can", "key", "giving")

    def __init__(self, pet, lane, s, y, d, v, goal, can):
        self.pet = pet
        self.lane = lane
        self.s = s
        self.y = y
        self.d = d
        self.v = v
        self.goal = goal
        self.can = can
        fsm = pet.behavior
        self.key = (fsm._cur().tier, pet.index)
        self.giving = fsm.state == "MakeWay"  # 正在让路：顺着对方走也还算挡着


def _sign(v):
    return 1 if v > 0 else (-1 if v < 0 else 0)


def _rec(pet):
    b = getattr(pet, "body", None)
    fsm = getattr(pet, "behavior", None)
    if b is None or fsm is None or fsm.grab.active:
        return None
    able = not b.dead and b.stun <= 0
    c0, c1 = b.chunk0, b.chunk1
    if b.zerog:
        pole = b.zerog_pole
        if pole is None:
            return None
        ax, ay = pole.bx - pole.ax, pole.by - pole.ay
        n = math.hypot(ax, ay) or 1.0
        ax, ay = ax / n, ay / n
        fx, fy = b.zerog_pole_intent
        d = _sign(round(fx * ax + fy * ay))
        v = abs(c0.vx * ax + c0.vy * ay)
        return _Rec(pet, ("Z", id(pole)), c0.x * ax + c0.y * ay, 0.0, d, v, None, False)
    if b.swimming:
        sx, _ = b._swim_dir()
        d = _sign(sx) if abs(sx) > SWIM_TURN else 0
        can = able and not (b.no_dive or b.swim_resting)
        return _Rec(pet, ("W",), c0.x, c0.y, d, abs(c0.vx), None, can)
    can = able and "MakeWay" in fsm._states and (fsm.state == "MakeWay" or not fsm.blocked(CROWD))
    if b.on_pole:
        anim = b.animation
        ix, iy = b.pole_input
        if anim in ("ClimbOnBeam", "GetUpToBeamTip", "BeamTip"):
            tip = anim != "ClimbOnBeam"
            d = 0 if anim == "BeamTip" else -iy
            return _Rec(pet, ("V", round(b.pole_x)), c0.y, 0.0, d, abs(c0.vy), None, can and not tip)
        if anim == "HangFromBeam":
            return _Rec(pet, ("H", round(b.pole_y)), c0.x, 0.0, ix, abs(c0.vx), None, can)
        if anim == "StandOnBeam":
            return _Rec(pet, ("S", round(b.pole_y)), c1.x, 0.0, ix, abs(c1.vx), None, can)
        return None
    grounded = b.on_floor()
    if not grounded and pet._HL - c1.y > GROUND_BAND:
        return None
    if not grounded:  # 贴地飞过的只占位，不叫别的猫让
        return _Rec(pet, ("F",), c1.x, 0.0, 0, abs(c1.vx), None, False)
    goal = b.walk_target_x if b.is_moving() else None
    d = _sign(goal - c1.x) if goal is not None else _sign(b.move_dir)
    can = can and (fsm.state == "MakeWay" or b.standing)
    return _Rec(pet, ("F",), c1.x, 0.0, d, abs(c1.vx), goal, can)


def _resting_on(pet, pets):
    """不动地停在别的猫身上（脚不着地、也不在杆上）：返回托着它的猫，没有 None。"""
    b = pet.body
    if b.on_floor() or b.on_pole or b.swimming or b.chunk1.vx**2 + b.chunk1.vy**2 > REST_SPEED**2:
        return None
    x, y = b.chunk1.x, b.chunk1.y
    for o in pets:
        ob = getattr(o, "body", None)
        if ob is None or o is pet:
            continue
        if any(abs(c.x - x) < CONTACT["F"] and 0.0 < c.y - y < GROUND_BAND for c in (ob.chunk0, ob.chunk1)):
            return o
    return None


def _slip_off(pet, under):
    """把停在别的猫身上的猫往外侧滑下去。"""
    b = pet.body
    if getattr(pet, "controlled", False) or pet.held is not None:
        return
    ub = under.body
    side = _sign(b.chunk1.x - (ub.chunk0.x + ub.chunk1.x) * 0.5) or (b.facing or 1)
    b.chunk0.vx += side * SLIP_VX
    b.chunk1.vx += side * SLIP_VX
    b.ghost = SLIP_GHOST


def _knock_off(pet):
    """把站在杆尖上的猫顶下去，往它偏的那侧掉。"""
    b = pet.body
    if getattr(pet, "controlled", False) or pet.held is not None or not b.on_pole:
        return False
    side = _sign(b.chunk0.x - b.pole_x) or (b.facing or 1)
    b.let_go_pole()
    b.chunk0.vx += side * SHOVE_FALL_VX
    b.chunk1.vx += side * SHOVE_FALL_VX * 0.4
    b.ghost = SHOVE_GHOST
    if pet.behavior is not None:
        pet.behavior.pole_lost()
    return True


class Traffic:
    def __init__(self, social):
        self.social = social
        self.orders = {}  # 猫 → Order
        self.tips = set()  # 有猫站着（或正爬上去）的杆尖所在通道
        self.ground = set()  # 在地面通道上的猫
        self.rest = {}  # 猫 → (被托着不动了几 tick, 托着它的猫)
        self.held = {}  # 猫 → 在杆上被挡停了几 tick
        self.shove = {}  # 猫 → 顶着杆尖上的猫往上挤了几 tick
        self._shoving = {}  # 本 tick 往上挤的猫 → 杆尖上的猫
        self._hop_cd = {}

    def update(self):
        self.orders.clear()
        self.tips.clear()
        self.ground.clear()
        pets = self.social.win.pets
        lanes = {}
        self._hop_cd = {p: n - 1 for p, n in self._hop_cd.items() if n > 1}
        for p in pets:
            b = getattr(p, "body", None)
            if b is not None:
                b.lane_hold = 0
            r = _rec(p)
            if r is not None:
                lanes.setdefault(r.lane, []).append(r)
                if r.lane[0] == "F":
                    self.ground.add(p)
                if r.lane[0] == "V" and p.body.animation != "ClimbOnBeam":
                    self.tips.add(r.lane)
        rest = {}
        for r in lanes.get(("F",), ()):
            under = _resting_on(r.pet, pets)
            if under is not None:
                rest[r.pet] = (self.rest.get(r.pet, (0, None))[0] + 1, under)
        self.rest = rest
        held = {}
        self._shoving = {}
        for recs in lanes.values():
            if len(recs) < 2:
                continue
            for a in recs:
                if a.d:
                    self._scan(a, recs, held)
        for p, (n, under) in rest.items():
            if n >= REST_TICKS:
                _slip_off(p, under)
        self.held = {p: self.held.get(p, 0) + 1 for p in held}
        self.shove = {p: self.shove.get(p, 0) + 1 for p in self._shoving}
        for p, top in self._shoving.items():
            if self.shove[p] >= SHOVE_TICKS:
                self.shove.pop(p)
                if _knock_off(top):
                    self.social.bonds.nudge(p, top, tuning.BOND_SHOVE)

    def _scan(self, a, recs, held):
        kind = a.lane[0]
        c = CONTACT[kind]
        reach = c + a.v * LEAD
        if a.goal is not None:
            reach = min(reach, (a.goal - a.s) * a.d)
        for b in recs:
            if b is a or (b.d == a.d and not b.giving) or (kind == "W" and abs(b.y - a.y) > WATER_BAND):
                continue
            rel = (b.s - a.s) * a.d
            if 0.0 < rel <= reach:
                self._meet(kind, a, b, rel, c, held)

    def _meet(self, kind, a, b, rel, c, held):
        """a 往 b 走、b 挡着：定谁让、怎么过。"""
        if b.d != -a.d:
            y = b if b.can else None
        else:  # 迎面：正在让路的不再掉头让
            y = min((r for r in (a, b) if r.can and not r.giving), key=lambda r: r.key, default=None)
        by = b if y is a else a
        # a 是过的一方；都让不了的迎面由优先级低的过
        passes = not a.giving and y is not a and (y is not None or b.d != -a.d or a.key < b.key)
        if kind == "F":
            if y is not None:
                self._order(y, "lie", by)
            if passes and rel <= HOP_DIST:
                self._hop(a.pet)
        elif kind == "W":
            if a.pet.body.swim_pass.busy or b.pet.body.swim_pass.busy:
                return  # 已经有一只在错开
            if y is None and a.can:
                y = a
            if y is not None:
                y.pet.body.swim_pass.request(True, by.s, by.pet.body.chunk0.vx)
            elif passes and rel <= HOP_DIST:
                a.pet.body.swim_pass.request(False, b.s, b.pet.body.chunk0.vx)
        elif kind == "Z":
            if rel <= c and not (b.d == -a.d and a.key < b.key):
                a.pet.body.lane_hold = a.d  # 迎面时优先级低的接着走
        else:
            if y is not None:
                self._order(y, "swap" if kind in ("H", "S") else "clear", by)
            if rel <= c:
                a.pet.body.lane_hold = -a.d if kind == "V" else a.d
                held[a.pet] = True
                if kind == "V" and a.d < 0 and b.pet.body.animation == "BeamTip":
                    self._shoving[a.pet] = b.pet
                if a.can and not a.giving and self.held.get(a.pet, 0) > PATIENCE:
                    self._order(a, "stop", b)

    def tip_free(self, pet):
        """我所在竖杆的杆尖空着。"""
        return ("V", round(pet.body.pole_x)) not in self.tips

    def _order(self, r, kind, by):
        if r.pet not in self.orders:
            self.orders[r.pet] = Order(kind, by.pet, by.d)

    def _hop(self, pet):
        b = pet.body
        if pet in self._hop_cd or not (b.standing and b.on_floor()):
            return
        b.request_jump("stand", hold_ticks=HOP_HOLD)
        self._hop_cd[pet] = HOP_COOLDOWN
