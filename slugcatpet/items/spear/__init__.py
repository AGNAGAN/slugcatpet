"""矛：能扔、能扎进墙当短杆；猫扔出的矛扎中光标会带着它飞到墙上钉住，开了友伤会扎伤别的猫。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainterPath, QPainterPathStroker

from ...core.units import clampf, lerp
from ...core.vecmath import _ang_from_up, _seg_dist
from ...rendering.primitives import blit
from ..base import CARRYABLE, CLIMBABLE, THROWABLE, ItemKind
from ..state import ItemState
from .model import BODY, HALF_LEN, SURE_STICK, STICK_CHANCE, STICK_MIN_SPEED, STICK_RANGE, THROW_SPEED
from .model import TIP_PIVOT, WALL, Spear

SPEAR_COLOR = (40, 42, 47)
SPRITE = "SmallSpear"
CAT_TRACE_PAD = 5.0  # 猫扔出的矛命中判定加宽
CURSOR_PAD = 8.0
CURSOR_PIN_TICKS = 120  # 光标被钉在墙上的时长
CURSOR_RIDE_MAX = 600  # 带着光标飞的看门狗上限
STAB_STUN_K = 30.0  # 晕的帧数 = 伤害 × 此值 + STAB_STUN_BONUS
STAB_STUN_BONUS = 20.0
STAB_PUSH_MAX = 10.0
LETHAL = 1.0  # 一下伤害到此即死
PIN_DAMAGE = 0.9  # 伤害高过此值、贴着墙时把那一节钉在墙上
TILE = 20.0
FLY_SLOTS = 5
FLY_SPAN = 15.0  # 串在矛上的小东西沿矛身排开的半宽
STOP_MASS = 0.6  # 一路穿过的小东西总质量超过此值就停下
FRUIT_RELEASE = (30, 50)  # 被打中的吊果过多久掉
FLING_HIT_SPEED = 8.0
FIRST_TRACE_DOT = 0.3  # 出手首帧只打投掷方向前方的东西
WALL_SPARKS = 7
CLASH_SPARKS = 3


class SpearKind(ItemKind):
    key = "spear"
    store = "spears"
    cap = 6
    affords = frozenset({THROWABLE, CARRYABLE, CLIMBABLE})
    varies = True
    collides = True
    grab_pad = 7.0
    grab_rank = 2
    grab_states = (ItemState.FREE, ItemState.STUCK)
    dead_state = ItemState.GONE

    def affords_now(self, s, use):
        if use == CLIMBABLE:
            return s.mode == WALL
        if use == THROWABLE:
            return s.mode not in (WALL, BODY)
        return True

    def make(self, win, lx, ly, seed):
        return Spear(lx, ly, seed=seed)

    def drop(self, win, s):
        for pet in win.pets:
            pet.body.release(s)
        ride = _ride(win)
        if ride is not None and ride[0] is s:
            _end_ride(win)
        s.impaled = []
        if s.mode == WALL:
            win.geometry_changed()
        s.state = ItemState.GONE

    def grab_dist(self, s, cx, cy):
        ax, ay, bx, by = _shaft(s)
        return _seg_dist(cx, cy, ax, ay, bx, by)

    def hit(self, s, cx, cy):
        if s.state not in self.grab_states:
            return None
        return self.grab_dist(s, cx, cy) - s.rad

    def draw_mark(self, p, s, rad):
        ax, ay, bx, by = _shaft(s)
        band = QPainterPath()
        band.moveTo(ax, ay)
        band.lineTo(bx, by)
        outline = QPainterPathStroker()
        outline.setWidth(12.0)
        p.drawPath(outline.createStroke(band))

    def on_grab(self, s):
        if s.mode in (WALL, BODY):
            s.pull_out()
        s.fling = False

    def on_release(self, win, s):
        if s.state == ItemState.MOUSE:
            s.state = ItemState.FREE
            s.on_flung()

    def floor_shift(self, win, old, new):
        for s in win.spears:
            s.shift_floor(old, new)

    def tick(self, win):
        spears = win.spears
        if not spears:
            return
        WL, HL = win._WL, win._HL
        for s in spears:
            if s.mode in (WALL, BODY) and s.state != ItemState.STUCK:
                s.pull_out()  # 被猫或光标拿走
            s.step(WL, HL)
        for s in spears:
            if s.mode == BODY:
                _follow_body(win, s)
            elif s.flying():
                _strike(win, s)
            elif s.fling and s.state == ItemState.FREE:
                _fling_hit(win, s)
        for s in spears:
            if s.wall_hit:
                if s.flying():
                    _wall_hit(win, s)
                else:
                    s.wall_hit = False
        _clash(win)
        _carry_impaled(win)
        _ride_tick(win)
        if any(s.geom_dirty for s in spears):
            for s in spears:
                s.geom_dirty = False
            win.geometry_changed()
        win.spears = [s for s in spears if s.state != ItemState.GONE]

    def draw_under(self, win, p):
        for s in win.spears:
            if s.state == ItemState.STUCK:
                _draw(win, p, s)

    def draw(self, win, p):
        for s in win.spears:
            if s.state not in (ItemState.STUCK, ItemState.GONE) and not (
                s.behind and s.state == ItemState.CARRIED
            ):
                _draw(win, p, s)

    def draw_behind(self, win, p):
        for s in win.spears:
            if s.behind and s.state == ItemState.CARRIED:
                _draw(win, p, s)

    def draw_hint(self, win, p, cx, cy):
        p.save()
        p.setOpacity(0.5)
        blit(p, win.atlas, SPRITE, cx, cy, 90.0, 1.0, 1.0, SPEAR_COLOR)
        p.restore()

    def paint_icon(self, p, r, atlas):
        from ...ui.widgets.iconkit import ICON_GREY, pen

        cx, cy = r.center().x(), r.center().y()
        h = r.height()
        if atlas is not None and atlas.find_atlas(SPRITE) is not None:
            k = h * 1.15 / (HALF_LEN * 2.0)
            blit(p, atlas, SPRITE, cx, cy, 45.0, k, k, QColor(*ICON_GREY.getRgb()))
            return
        p.setPen(pen(ICON_GREY, max(1.6, h * 0.08)))
        d = h * 0.4
        p.drawLine(QPointF(cx - d, cy + d), QPointF(cx + d, cy - d))


# 形状


def _shaft(s):
    """矛身两端（尾、尖）。"""
    k = TIP_PIVOT if s.pivot_at_tip() else 0.5
    L = HALF_LEN * 2.0
    rx, ry = s.rot
    return s.x - rx * L * k, s.y - ry * L * k, s.x + rx * L * (1.0 - k), s.y + ry * L * (1.0 - k)


def _draw(win, p, s):
    ts = win._ts
    x = s.last_x + (s.x - s.last_x) * ts
    y = s.last_y + (s.y - s.last_y) * ts
    a0 = _ang_from_up(*s.last_rot)
    a1 = _ang_from_up(*s.rot)
    ang = a0 + ((a1 - a0 + 180.0) % 360.0 - 180.0) * ts
    if s.vibrate > 0:
        x += (s.vibrate % 3) - 1.0
        y += ((s.vibrate // 2) % 3) - 1.0
    ay = 1.0 - TIP_PIVOT if s.pivot_at_tip() else 0.5
    blit(p, win.atlas, SPRITE, x, y, ang, 1.0, 1.0, SPEAR_COLOR, ax=0.5, ay=ay)


# 扎墙


def _wall_hit(win, s):
    """沿投掷方向撞墙：按离出手点的距离、概率和速度判定扎不扎得进，同一格只扎一根。"""
    WL, HL = win._WL, win._HL
    d = math.hypot(s.x - s.thrown_x, s.y - s.thrown_y)
    ok = d < STICK_RANGE * max(1.0, s.damage)
    if ok:
        lucky = s._rng.random() < STICK_CHANCE
        ok = lucky or d < SURE_STICK
    if ok:
        spot = s.wall_spot(WL, HL)
        ok = not any(
            o is not s and o.mode == WALL and (o.wall[0], o.wall[2]) == (spot[0], spot[2]) for o in win.spears
        )
    if ok and math.hypot(s.vx, s.vy) < STICK_MIN_SPEED:
        ok = False
    dx, dy = s.throw_dir
    if ok:
        s.stick(WL, HL)
        return
    for _ in range(WALL_SPARKS):
        a = s._rng.uniform(0.0, math.tau)
        v = 10.0 * s._rng.random()
        win.add_spark(
            s.x + dx * (s.rad - 1.0),
            s.y + dy * (s.rad - 1.0),
            math.cos(a) * v - dx * 10.0,
            math.sin(a) * v - dy * 10.0,
            life=4,
        )
    win._shake_impact(None, (dx, dy), 0.0, 0.0, dx * 1.5, dy * 1.5)
    s.hit_wall()


# 飞行中的命中


def _seg_circle_t(ax, ay, bx, by, cx, cy, r):
    """线段 a→b 首次进入以 c 为心、r 为半径的圆的比例；不碰返回 None。"""
    dx, dy = bx - ax, by - ay
    fx, fy = ax - cx, ay - cy
    a = dx * dx + dy * dy
    c = fx * fx + fy * fy - r * r
    if c <= 0.0:
        return 0.0
    if a < 1e-12:
        return None
    b = 2.0 * (fx * dx + fy * dy)
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None
    t = (-b - math.sqrt(disc)) / (2.0 * a)
    return t if 0.0 <= t <= 1.0 else None


def _ahead(s, x, y, first):
    """出手首帧只算投掷方向前方的东西。"""
    if not first:
        return True
    dx, dy = s.throw_dir
    ux, uy = x - s.last_x, y - s.last_y
    d = math.hypot(ux, uy)
    return d < 1e-9 or (ux * dx + uy * dy) / d > FIRST_TRACE_DOT


def _held_by(body, obj):
    return body is not None and body.hand_of(obj) is not None


def _strike(win, s):
    """投掷态这一 tick 扫过的线段：先打最早碰到的猫或果子，再看光标，最后穿过小东西。"""
    first = s.trace_from is not None
    ax, ay = s.trace_from if first else (s.last_x, s.last_y)
    s.trace_from = None
    bx, by = s.x, s.y
    pad = CAT_TRACE_PAD if s.thrown_by is not None else 0.0
    best, best_t = None, None
    if win.cfg_friendly_fire:
        for pet in win.pets:
            b = pet.body
            if b is s.thrown_by or pet.behavior is None:
                continue
            for c in (b.chunk0, b.chunk1):
                if not _ahead(s, c.x, c.y, first):
                    continue
                t = _seg_circle_t(ax, ay, bx, by, c.x, c.y, s.rad + pad + c.rad)
                if t is not None and (best_t is None or t < best_t):
                    best, best_t = ("cat", pet, c), t
    for f in win.fruits:
        if f.state not in (ItemState.FREE, ItemState.HANGING, ItemState.CARRIED) or _held_by(s.thrown_by, f):
            continue
        if not _ahead(s, f.x, f.y, first):
            continue
        t = _seg_circle_t(ax, ay, bx, by, f.x, f.y, s.rad + pad + f.rad)
        if t is not None and (best_t is None or t < best_t):
            best, best_t = ("fruit", f, None), t
    if best is not None:
        if best[0] == "cat":
            _stab(win, s, best[1], best[2], s.damage)
        else:
            _hit_fruit(s, best[1])
        _end_ride_of(win, s)
        return
    if s.thrown_by is not None:
        _catch_cursor(win, s, ax, ay, bx, by)
    _pierce_small(win, s, ax, ay, bx, by, pad)


def _fling_hit(win, s):
    """光标甩出的矛：开了友伤时快速扫过猫会扎进去，伤害按速度算。"""
    sp = math.hypot(s.vx, s.vy)
    if not win.cfg_friendly_fire or sp < FLING_HIT_SPEED:
        return
    for pet in win.pets:
        if pet.behavior is None:
            continue
        b = pet.body
        for c in (b.chunk0, b.chunk1):
            if _seg_circle_t(s.last_x, s.last_y, s.x, s.y, c.x, c.y, s.rad + c.rad) is not None:
                s.fling = False
                _stab(win, s, pet, c, sp / THROW_SPEED, blame=True)
                return


def _stab(win, s, pet, chunk, damage, blame=False):
    """扎中一只猫：冲量、按伤害晕或死、累计伤，矛留在身上；够狠又贴着墙时把那一节钉在墙上。"""
    b = pet.body
    k = s.mass * 2.0 / chunk.mass
    px, py = s.vx * k, s.vy * k
    m = math.hypot(px, py)
    if m > STAB_PUSH_MAX:
        px, py = px * STAB_PUSH_MAX / m, py * STAB_PUSH_MAX / m
    chunk.vx += px
    chunk.vy += py
    beh = pet.behavior
    if not b.dead and beh is not None:
        b.wounds += damage
        if damage >= LETHAL or b.wounds >= 1.0:
            beh.kill(blame=blame)
        else:
            beh.apply_stun(int(damage * STAB_STUN_K + STAB_STUN_BONUS), blame=blame)
    pin = _pin_point(win, s, chunk) if damage > PIN_DAMAGE else None
    s.lodge(chunk, _body_ang(b), pin)


def _pin_point(win, s, chunk):
    """被扎的这一节贴着投掷方向上的墙（一格内）时，钉住的位置。"""
    dx, dy = s.throw_dir
    if dx > 0:
        gap = win._WL - chunk.x
    elif dx < 0:
        gap = chunk.x
    elif dy > 0:
        gap = win._HL - chunk.y
    else:
        gap = chunk.y
    if gap >= TILE + chunk.rad:
        return None
    if dx:
        x = win._WL - chunk.rad if dx > 0 else chunk.rad
        return x, chunk.y
    y = win._HL - chunk.rad if dy > 0 else chunk.rad
    return chunk.x, y


def _body_ang(b):
    return _ang_from_up(b.chunk0.x - b.chunk1.x, b.chunk0.y - b.chunk1.y)


def _hit_fruit(s, f):
    """打中果子：把它推开，吊着的过一会儿掉下来；矛弹开。"""
    if f.state != ItemState.CARRIED:
        f.vx += s.vx * s.mass / f.mass
        f.vy += s.vy * s.mass / f.mass
    st = getattr(f, "stalk", None)
    if st is not None and st.release_counter == 0:
        st.release_counter = s._rng.randint(*FRUIT_RELEASE)
    s.bounce_off()


def _pierce_small(win, s, ax, ay, bx, by, pad):
    """穿过小飞虫：杀死并串在矛上（最多五只），路上的总质量够大才停下。"""
    load = 0.0
    taken = {id(o) for o, _ in s.impaled}
    for f in win.batflies:
        if f.state in (ItemState.EATEN, ItemState.GONE, ItemState.MOUSE) or id(f) in taken:
            continue
        if _held_by(s.thrown_by, f):
            continue
        if _seg_circle_t(ax, ay, bx, by, f.x, f.y, s.rad + pad + f.rad) is None:
            continue
        for pet in win.pets:
            pet.body.release(f, to_free=True)
        f.held_by_hand = None
        f.state = ItemState.FREE
        f.vx += s.vx
        f.vy += s.vy
        f.die()
        used = {slot for _, slot in s.impaled}
        slot = next((i for i in range(FLY_SLOTS) if i not in used), None)
        if slot is not None and len(s.impaled) <= FLY_SLOTS:
            s.impaled.append((f, slot))
        load += f.mass
        if load > STOP_MASS:
            s.x, s.y = f.x, f.y
            s.to_free()
            s.vx *= 0.5
            s.vy *= 0.5
            _end_ride_of(win, s)
            return


def _carry_impaled(win):
    """串在矛上的小东西跟着矛走；被拿走、被吃掉的就脱开。"""
    for s in win.spears:
        if not s.impaled:
            continue
        keep = []
        for f, slot in s.impaled:
            if f.state != ItemState.FREE or f.held_by_hand is not None or s.state == ItemState.GONE:
                continue
            k = lerp(FLY_SPAN, -FLY_SPAN, slot / (FLY_SLOTS - 1))
            f.x, f.y = s.x + s.rot[0] * k, s.y + s.rot[1] * k
            f.vx = f.vy = 0.0
            keep.append((f, slot))
        s.impaled = keep


def _clash(win):
    """两件迎面飞来的武器相撞：都朝相反的随机方向弹开，迸火花。"""
    flying = [s for s in win.spears if s.flying()]
    if not flying:
        return
    others = [w for w in win.items_affording(THROWABLE) if w.in_flight()]
    done = set()
    for s in flying:
        if id(s) in done:
            continue
        for w in others:
            if w is s or id(w) in done:
                continue
            if (w.x - w.last_x < 0.0) == (s.x - s.last_x < 0.0):
                continue
            if _seg_circle_t(s.last_x, s.last_y, s.x, s.y, w.x, w.y, s.rad + w.rad) is None:
                continue
            mx, my = (w.last_x + s.last_x) * 0.5, (w.last_y + s.last_y) * 0.5
            speed = math.hypot(s.vx, s.vy)
            n = CLASH_SPARKS + 2 + (2 if getattr(w, "pierces", False) else 0)
            for _ in range(n):
                a = s._rng.uniform(0.0, math.tau)
                v = lerp(2.0, 7.0, s._rng.random()) * n
                win.add_spark(mx, my, math.cos(a) * v, math.sin(a) * v)
            a = s._rng.uniform(0.0, math.tau)
            dx, dy = math.cos(a), math.sin(a)
            s.clash(mx, my, dx, dy, speed, s._rng)
            w.clash(mx, my, -dx, -dy, speed, s._rng)
            _end_ride_of(win, s)
            done.add(id(s))
            done.add(id(w))
            break


# 扎身


def _follow_body(win, s):
    """扎在猫身上：跟着那一节走；猫醒过来（不晕也不死）时掉下来。"""
    owner = next((pet for pet in win.pets if s.stuck_in in (pet.body.chunk0, pet.body.chunk1)), None)
    if owner is None or (not owner.body.dead and owner.body.stun <= 0):
        c = s.stuck_in
        s.pull_out()
        s.state = ItemState.FREE
        s.to_free()
        if c is not None:
            s.vx, s.vy = c.vx, c.vy
        return
    s.follow_body(_body_ang(owner.body))


# 光标


def _ride(win):
    return getattr(win, "_spear_ride", None)


def _end_ride(win):
    ride = _ride(win)
    win._spear_ride = None
    if ride is not None and win.cursor_hijack is ride[1]:
        win.stop_cursor_hijack()


def _end_ride_of(win, s):
    ride = _ride(win)
    if ride is not None and ride[0] is s:
        _end_ride(win)


def _catch_cursor(win, s, ax, ay, bx, by):
    """猫扔出的矛扫过光标：抢过光标带着一起飞。"""
    if _ride(win) is not None or win.cursor_hijack is not None:
        return
    cur = win.cursor_logical()
    if cur is None:
        return
    if _seg_dist(cur[0], cur[1], ax, ay, bx, by) >= s.rad + CURSOR_PAD:
        return
    hj = win.start_cursor_hold(cur[0], cur[1], CURSOR_RIDE_MAX)
    if hj is not None:
        win._spear_ride = [s, hj, None]


def _ride_tick(win):
    """光标跟着矛飞；矛扎进墙就钉住一阵，矛没扎进去光标就脱身。"""
    ride = _ride(win)
    if ride is None:
        return
    s, hj, pin = ride
    if win.cursor_hijack is not hj or not hj.active:
        win._spear_ride = None
        return
    if s.mode == WALL:
        side, face, along = s.wall
        x, y = (face, along) if side in ("l", "r") else (along, face)
        win.move_cursor_hold(clampf(x, 0.0, win._WL), clampf(y, 0.0, win._HL))
        ride[2] = CURSOR_PIN_TICKS if pin is None else pin - 1
        if ride[2] <= 0:
            _end_ride(win)
        return
    if not s.flying():
        _end_ride(win)
        return
    win.move_cursor_hold(*s.tip())


KIND = SpearKind()
