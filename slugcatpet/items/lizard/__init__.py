"""蜥蜴：活物物品。模拟全在房间坐标（y↑），这里负责窗口坐标换算、放置 / 拖拽 / 存档，
以及蜥蜴和蛋虫、光标之间的桥（PreyView / CursorView 把它们包成蜥蜴 AI 认得的「生物」）。

蜥蜴之间保留原版的物理碰撞（同一碰撞层，互相推开），按品种关系互相示威、打斗。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor

from ..base import ItemKind
from ..eggbug.model import MOUTH
from ..state import ItemState
from . import shortcut
from .model import Lizard, Noise
from .rw import V2, dir_vec, inverse_lerp, lerp
from .terrain import terrain_for

PAD = 6.0  # 光标离身体表面这么近就算抓得到
SYMBOLS = {
    "green": "Kill_Green_Lizard",
    "pink": "Kill_Standard_Lizard",
    "cyan": "Kill_Standard_Lizard",
    "blue": "Kill_Standard_Lizard",
    "red": "Kill_Standard_Lizard",
    "white": "Kill_White_Lizard",
}
# CreatureSymbol.ColorOfCreature 里不取 standardColor 的品种
SYMBOL_COLOR = {"cyan": (0.0, 0.9098039, 0.8980392), "red": (46.0 / 51.0, 0.05490196, 0.05490196)}
MAX_LIZARDS = 3


class _Env:
    """窗口的地面线：y_room = HL - y_win。"""

    __slots__ = ("HL",)

    def __init__(self, HL: float = 0.0):
        self.HL = HL


class _Ctx:
    """Lizard.step 的输入。"""

    __slots__ = ("terrain", "WL", "HL", "creatures", "lizards", "noise_out", "sparks", "orbs")

    def __init__(self):
        self.terrain = None
        self.WL = self.HL = 0.0
        self.creatures = []
        self.lizards = []
        self.noise_out = []  # 本 tick 产生的噪音，下一 tick 起交给各蜥蜴
        self.sparks = []  # 头盾弹开的 Spark / FlashOrb
        self.orbs = []


class _ChunkView:
    """蛋虫的一节在房间坐标下的视图（写回时换回窗口坐标）。"""

    __slots__ = ("owner", "index", "c")

    def __init__(self, owner: PreyView, index: int, c):
        self.owner = owner
        self.index = index
        self.c = c

    @property
    def pos(self) -> V2:
        return V2(self.c.x, self.owner.env.HL - self.c.y)

    @pos.setter
    def pos(self, v: V2) -> None:
        self.c.x = v.x
        self.c.y = self.owner.env.HL - v.y

    @property
    def last_pos(self) -> V2:
        return V2(self.c.last_x, self.owner.env.HL - self.c.last_y)

    @property
    def vel(self) -> V2:
        return V2(self.c.vx, -self.c.vy)

    @vel.setter
    def vel(self, v: V2) -> None:
        self.c.vx = v.x
        self.c.vy = -v.y

    @property
    def rad(self) -> float:
        return self.c.rad

    @property
    def mass(self) -> float:
        return self.c.mass

    def move_from_outside_my_update(self, eu: bool, to: V2) -> None:
        """被叼的这节搬到嘴前：另一节跟着平移（被叼的蛋虫在 _held_step 里让它自己晃）。"""
        o = self.owner
        c = self.c
        nx, ny = to.x, o.env.HL - to.y
        dx, dy = nx - c.x, ny - c.y
        c.last_x, c.last_y = c.x, c.y
        c.x, c.y = nx, ny
        for other in o.bug.chunks:
            if other is not c:
                other.x += dx
                other.y += dy

    hard_set_position = move_from_outside_my_update


class PreyView:
    """EggBug 作为蜥蜴的猎物：房间坐标、原版 Creature 的字段名。

    被叼时总是抓腹部那一节（chunk 1）：蛋虫的「被拿着」只支持腹部定位、头自己晃。
    """

    is_creature = True
    kind_key = "eggbug"
    body_size = 0.4
    scaryness = 1.0
    visibility_bonus = 0.0
    new_to_room_invincibility = 0
    grab_chunk_index = 1

    def __init__(self, bug, env: _Env):
        self.bug = bug
        self.env = env
        self.body_chunks = [_ChunkView(self, 0, bug.c0), _ChunkView(self, 1, bug.c1)]
        self.grabbed_by: list = []
        self.eaten = False
        self.taken_away = False  # 被叼着钻出了屏幕
        self._prev = None

    @property
    def in_shortcut(self) -> bool:
        return any(getattr(g.grabber, "in_shortcut", False) for g in self.grabbed_by)

    @property
    def gone(self) -> bool:
        b = self.bug
        return b.state in (ItemState.EATEN, ItemState.GONE) or b.dissolve >= 0

    @property
    def represented_creature(self) -> PreyView:
        return self

    @property
    def realized_creature(self) -> PreyView | None:
        return None if self.gone or self.in_shortcut else self

    @property
    def dead(self) -> bool:
        return self.bug.dead

    @property
    def main_body_chunk(self) -> _ChunkView:
        return self.body_chunks[0]

    @property
    def danger_pos(self) -> V2:
        return self.body_chunks[0].pos

    @property
    def pos_tile(self) -> tuple[int, int]:
        p = self.body_chunks[0].pos
        return (math.floor(p.x / 20.0), math.floor(p.y / 20.0))

    @property
    def total_mass(self) -> float:
        return self.bug.c0.mass + self.bug.c1.mass

    @property
    def collidable(self) -> bool:
        return self.bug.state == ItemState.FREE and self.bug.dissolve < 0

    def can_be_grabbed(self, grabber) -> bool:
        b = self.bug
        if self.gone or self.in_shortcut:
            return False
        return b.state == ItemState.FREE or (b.state == ItemState.CARRIED and bool(self.grabbed_by))

    def grabbed(self, grasp) -> None:
        self.grabbed_by.append(grasp)
        b = self.bug
        b.state = ItemState.CARRIED
        b.held_by_hand = MOUTH
        b.footing = 0
        b.stun = max(b.stun, 10)  # pacifying：叼着时不挣扎着逃

    def on_released(self, grasp) -> None:
        b = self.bug
        if b.state == ItemState.CARRIED and not self.grabbed_by:
            b.state = ItemState.FREE
            b.held_by_hand = None

    def detect_impacts(self, out: list) -> None:
        """PhysicalObject.TerrainImpact 里的 InGameNoise：第一次碰到地面 / 墙，速度 > 4 且够响。
        蛋虫在窗口坐标里自己积分，这里按碰撞标志和上一 tick 的速度还原撞击。"""
        b = self.bug
        HL = self.env.HL
        if b.state != ItemState.FREE:
            self._prev = None
            return
        prev = self._prev
        self._prev = [(c.vx, c.vy) for c in b.chunks]
        if prev is None:
            return
        for c, (pvx, pvy) in zip(b.chunks, prev):
            hit = None
            if c.cy == 1 and c.lcy < 1:
                hit = (abs(pvy), (0.0, -1.0))
            elif c.cx != 0 and c.lcx != c.cx:
                hit = (abs(pvx), (float(c.cx), 0.0))
            if hit is None:
                continue
            speed, d = hit
            m = speed * lerp(c.mass, 1.0, 0.5)
            if speed > 4.0 and m > 0.5:
                pos = V2(c.x, HL - c.y) + V2(d[0], d[1]) * (c.rad * 0.9)
                out.append(
                    Noise(pos, lerp(350.0, lerp(100.0, 1500.0, inverse_lerp(0.5, 20.0, m)), 0.5), self, 1.0)
                )

    def push_out_of(self, pos: V2, rad: float, excepted_chunk: int) -> None:
        for ch in self.body_chunks:
            if ch.index == excepted_chunk:
                continue
            cp = ch.pos
            d = math.hypot(cp.x - pos.x, cp.y - pos.y)
            if d < rad + ch.rad:
                v = dir_vec(cp, pos)
                ch.pos = cp - v * (rad + ch.rad - d)
                ch.vel = ch.vel - v * (rad + ch.rad - d)

    def violence(
        self, source, direction_and_momentum, hit_chunk, kind, damage: float, stun_bonus: float
    ) -> None:
        self.bug.violence(damage, stun_bonus)

    def pulled_by_tongue(self) -> None:
        """被舌头拽着就站不稳：蛋虫的腿是直接加速度，站稳时能和白蜥蜴舌头的弹性拉力僵持住。"""
        self.bug.footing = 0


class EggSource:
    """蛋虫的蛋作为噪音源：不是生物。"""

    is_creature = False

    def __init__(self, egg, env: _Env):
        self.egg = egg
        self.env = env
        self.grabbed_by: list = []
        self._prev = None

    def detect_impacts(self, out: list) -> None:
        e = self.egg
        if e.state != ItemState.FREE:
            self._prev = None
            return
        prev, self._prev = self._prev, e.vy
        if prev is None:
            return
        floor = self.env.HL
        if prev > 4.0 and e.vy < prev * 0.5 and e.y + e.rad >= floor - 1.5:
            m = prev * lerp(e.mass, 1.0, 0.5)
            if m > 0.5:
                pos = V2(e.x, floor - e.y - e.rad * 0.9)
                out.append(
                    Noise(pos, lerp(350.0, lerp(100.0, 1500.0, inverse_lerp(0.5, 20.0, m)), 0.5), self, 1.0)
                )


class _PlainChunk:
    __slots__ = ("owner", "index", "pos", "last_pos", "vel", "rad", "mass")

    def __init__(self, owner):
        self.owner = owner
        self.index = 0
        self.pos = self.last_pos = V2()
        self.vel = V2()
        self.rad = 8.0
        self.mass = 0.35


class CursorView:
    """光标：蜥蜴会看它，不追不怕（关系恒为 Ignores）。"""

    is_creature = True
    kind_key = "cursor"
    body_size = 1.0
    scaryness = 1.0
    visibility_bonus = 0.0
    new_to_room_invincibility = 0
    dead = False
    pos_tile = (0, 0)

    def __init__(self):
        self.chunk = _PlainChunk(self)
        self.body_chunks = [self.chunk]
        self.main_body_chunk = self.chunk
        self.grabbed_by: list = []
        self.present = False

    @property
    def represented_creature(self) -> CursorView:
        return self

    @property
    def realized_creature(self) -> CursorView | None:
        return self if self.present else None

    @property
    def danger_pos(self) -> V2:
        return self.chunk.pos

    @property
    def total_mass(self) -> float:
        return self.chunk.mass

    def update(self, cur, WL: float, HL: float) -> None:
        if cur is None or not (0.0 <= cur[0] <= WL and 0.0 <= cur[1] <= HL):
            self.present = False
            return
        c = self.chunk
        pos = V2(cur[0], HL - cur[1])
        c.last_pos = c.pos if self.present else pos
        c.pos = pos
        c.vel = pos - c.last_pos
        self.present = True
        self.pos_tile = (math.floor(pos.x / 20.0), math.floor(pos.y / 20.0))


def _collide_pair(a, b) -> None:
    """Room.Update 里的物体碰撞：同层的每对身体节重叠就按质量反比推开，整对物体只通知一次 Collide。"""
    for g in a.grasps if hasattr(a, "grasps") else ():
        if g is not None and g.grabbed is b:
            return
    for g in b.grasps if hasattr(b, "grasps") else ():
        if g is not None and g.grabbed is a:
            return
    notified = False
    for i, ca in enumerate(a.body_chunks):
        for j, cb in enumerate(b.body_chunks):
            pa, pb = ca.pos, cb.pos
            rs = ca.rad + cb.rad
            dx, dy = pb.x - pa.x, pb.y - pa.y
            if dx > rs or dx < -rs or dy > rs or dy < -rs:
                continue
            d = math.hypot(dx, dy)
            if d >= rs:
                continue
            v = dir_vec(pa, pb)
            w = cb.mass / (ca.mass + cb.mass)
            va = v * ((rs - d) * w)
            vb = v * ((rs - d) * (1.0 - w))
            ca.pos = pa - va
            ca.vel = ca.vel - va
            cb.pos = pb + vb
            cb.vel = cb.vel + vb
            if dx == 0.0:
                ca.vel = ca.vel + V2(1e-4, 0.0)
                cb.vel = cb.vel - V2(1e-4, 0.0)
            if not notified:
                for me, other, mi, oi in ((a, b, i, j), (b, a, j, i)):
                    cb_fn = getattr(me, "collide", None)
                    if cb_fn is not None:
                        cb_fn(other, mi, oi)
            notified = True


class LizardKind(ItemKind):
    store = "lizards"
    seed_key = "lizard"
    apps = ("lizard",)
    cap = MAX_LIZARDS  # 各品种合计
    layer = "front"
    collides = False  # 碰撞在 tick 里自己做（要通知 Collide）
    grab_pad = PAD
    grab_rank = 1
    splash_states = ()
    dead_state = ItemState.EATEN

    def __init__(self, key: str, breed: str, mobile: bool):
        self.key = key
        self.breed = breed
        self.mobile = mobile  # 各品种共用一个列表，只让一种算进宿主的活动物品，免得重复

    # 放置 / 存档

    def can_place(self, win) -> bool:
        return len(win.lizards) < self.cap

    def make(self, win, lx, ly, seed):
        T = terrain_for(win)
        x = min(max(lx, 12.0), T.WL - 12.0)
        y = min(max(T.HL - ly, 12.0), T.HL - 12.0)
        L = Lizard(x, y, self.breed, seed)
        L.terrain = T
        return L

    def dump(self, L):
        if L.lizard_params.key != self.breed or L.state in (ItemState.EATEN, ItemState.GONE):
            return None
        return {"x": L.x, "y": L.y, "seed": L._id}

    def load(self, win, d, fit):
        if len(win.lizards) >= MAX_LIZARDS:
            return None
        x, y = fit.inside(float(d["x"]), float(d["y"]))
        return self.make(win, x, y, int(d.get("seed", 0)))

    # 移除

    def hit(self, L, cx, cy):
        if L.state in (ItemState.EATEN, ItemState.GONE) or L.in_shortcut:
            return None
        return L.dist_to(cx, cy)

    def draw_mark(self, p, L, rad):
        hl = L.terrain.HL
        for c in L.body_chunks:
            p.drawEllipse(QPointF(c.pos.x, hl - c.pos.y), c.rad + 4.0, c.rad + 4.0)

    def drop(self, win, L):
        L.lose_all_grasps()
        if L.drag is not None:
            L.end_drag(V2())
        L.state = self.dead_state

    # 拖拽

    def grab_dist(self, L, cx, cy):
        return math.inf if L.in_shortcut else L.dist_to(cx, cy)

    def on_release(self, win, L):
        if L.state != ItemState.MOUSE:
            return
        L.end_drag(V2(L._fvx, -L._fvy))
        L.state = ItemState.FREE

    # 推进

    def tick(self, win):
        ls = win.lizards
        if not ls:
            return
        env = _env(win)
        ctx = _ctx(win)
        T = terrain_for(win)
        HL = win._HL
        env.HL = HL
        ctx.terrain, ctx.WL, ctx.HL = T, win._WL, HL
        for lst in (ctx.sparks, ctx.orbs):
            for x in lst:
                x.update(T)
            lst[:] = [x for x in lst if not x.dead]
        views = [_view(b, env) for b in win.eggbugs]
        heard, ctx.noise_out = ctx.noise_out, []  # 上一 tick 产生的噪音，这一 tick 才被听到
        for L in ls:
            for n in heard:
                L.hear_noise(n)
        cursor = getattr(win, "_lz_cursor", None)
        if cursor is None:
            cursor = win._lz_cursor = CursorView()
        cursor.update(win.cursor_logical(), win._WL, HL)
        here = [L for L in ls if not L.in_shortcut]
        crits = [v for v in views if not v.gone and not v.in_shortcut]
        if cursor.present:
            crits.append(cursor)
        ctx.creatures = crits + here
        ctx.lizards = here
        for L in ls:
            self._sync(L, HL)
            if L.in_shortcut:
                L.terrain = T
                shortcut.update(L, T)
            else:
                L.step(ctx)
        for i, a in enumerate(here):
            for b in here[i + 1 :]:
                _collide_pair(a, b)
        for v in crits:
            if v is cursor or not v.collidable:
                continue
            for L in here:
                _collide_pair(L, v)
        for L in here:
            _contain(L, win._WL, HL)
        for v in views:
            v.detect_impacts(ctx.noise_out)
        for e in win.bugeggs:
            _egg_source(win, e, env).detect_impacts(ctx.noise_out)
        if len(win.__dict__.get("_lz_egg_src", ())) > 4 * len(win.bugeggs) + 16:
            alive = {id(e) for e in win.bugeggs}
            win._lz_egg_src = {k: v for k, v in win._lz_egg_src.items() if k in alive}
        for v in views:
            _clamp_legs(v.bug)  # 蛋虫先于蜥蜴推进：舌头 / 叼持 / 碰撞挪动它之后，腿要重新夹回腿长内
        for v in views:
            if v.taken_away:
                v.taken_away = False
                _eggbug_kind().drop(win, v.bug)
            elif v.eaten:
                v.eaten = False
                _eggbug_kind().dissolve(win, v.bug)
        win.lizards = [L for L in ls if L.state != self.dead_state]

    def _sync(self, L, HL):
        """被拖时把光标位置同步给身体；叼着的猎物被别人拿走或没了就松口。"""
        if L.state == ItemState.MOUSE:
            tgt = V2(min(max(L._mx, 0.0), L.terrain.WL), min(max(HL - L._my, 8.0), HL - 8.0))
            if L.drag is None:
                L.begin_drag(tgt)
            L.drag_to(tgt, V2(L._fvx, -L._fvy))
        elif L.drag is not None:
            L.end_drag(V2())
        g = L.grasps[0]
        if g is not None:
            prey = g.grabbed
            if isinstance(prey, PreyView) and (prey.gone or prey.bug.state != ItemState.CARRIED):
                L.release_grasp(0)

    # 绘制

    def draw(self, win, p):
        ts, atlas, hl = win._ts, win.atlas, win._HL
        for L in win.lizards:
            if L.state in (ItemState.EATEN, ItemState.GONE) or L.sc_phase == shortcut.AWAY:
                continue
            _draw_lizard(p, L, ts, 1.0, atlas, hl)
        ctx = getattr(win, "_lz_ctx", None)
        if ctx is not None and (ctx.sparks or ctx.orbs):
            from .draw import draw_flash_orbs, draw_sparks

            draw_sparks(p, ctx.sparks, ts, 1.0, hl)
            draw_flash_orbs(p, ctx.orbs, ts, 1.0, hl)

    def draw_under(self, win, p):
        """跳跃烟雾在最底层（杆之下）。"""
        from .draw import draw_jump_smoke

        ts, hl = win._ts, win._HL
        for L in win.lizards:
            if L.jump_module is not None and L.jump_module.smoke is not None:
                draw_jump_smoke(p, L.jump_module, ts, 1.0, hl)

    def draw_overlay(self, win, p):
        """JumpLight / ShockWave 是 Bloom 层：盖在所有层之上。"""
        from .draw import draw_jump_lights

        ts, hl = win._ts, win._HL
        for L in win.lizards:
            if L.jump_module is not None and (L.jump_module.lights or L.jump_module.shock_waves):
                draw_jump_lights(p, L.jump_module, ts, 1.0, hl)

    def on_enter_place(self, win):
        win._place_preview = self.make(win, 0.0, 0.0, win.item_seed(self))

    def draw_hint(self, win, p, cx, cy):
        """光标处半透明的一只，横躺着悬在空中。"""
        L = getattr(win, "_place_preview", None)
        if L is None:
            return
        T = terrain_for(win)
        L.terrain = T
        step = L.body_chunk_connections[0].distance
        y = T.HL - cy
        for i, c in enumerate(L.body_chunks):
            pos = V2(cx + (1 - i) * step, y)
            c.pos = c.last_pos = c.last_last_pos = pos
            c.vel = V2()
        L.graphics_module.update()
        _draw_lizard(p, L, 1.0, 0.5, win.atlas, win._HL)

    def paint_icon(self, p, r, atlas):
        """原版 CreatureSymbol：绿蜥蜴 Kill_Green_Lizard，粉蜥蜴 Kill_Standard_Lizard，颜色取品种的 standardColor。"""
        from .breeds import get

        name = SYMBOLS[self.breed]
        c = SYMBOL_COLOR.get(self.breed) or get(self.breed).standard_color
        col = QColor(*(int(round(255 * v)) for v in c))
        ui = atlas.get("ui") if atlas is not None else None
        if ui is None or not ui.has(name):
            p.setBrush(col)
            p.drawEllipse(r.center(), r.width() * 0.35, r.height() * 0.35)
            return
        sw, sh = atlas.source_size("ui", name)
        s = min(r.width() / sw, r.height() / sh) * 0.92
        dw, dh = sw * s, sh * s
        pm = atlas.sprite("ui", name, col)
        p.drawPixmap(QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh), pm, QRectF(pm.rect()))


def _contain(L, WL: float, HL: float) -> None:
    """身体中心不可能合法地跑到窗口外（碰撞推挤可能把它挤进实心格出不来）：夹回来。"""
    moved = False
    for c in L.body_chunks:
        x, y = c.pos.x, c.pos.y
        if 0.0 <= x <= WL and 0.0 <= y <= HL:
            continue
        nx = min(max(x, c.rad), WL - c.rad)
        ny = min(max(y, c.rad), HL - c.rad)
        c.pos = V2(nx, ny)
        c.last_pos = c.pos
        c.vel = V2(0.0 if nx != x else c.vel.x, 0.0 if ny != y else c.vel.y)
        moved = True
    if moved:
        L.graphics_module.reset()


def _draw_lizard(p, L, ts, alpha, atlas, hl):
    try:
        from .draw import draw_lizard
    except ImportError:
        p.setBrush(QColor(*(int(255 * v) for v in L.effect_color)))
        for c in L.body_chunks:
            p.drawEllipse(QPointF(c.pos.x, hl - c.pos.y), c.rad, c.rad)
        return
    draw_lizard(p, L.graphics_module, ts, alpha, atlas, hl)


def _env(win) -> _Env:
    e = getattr(win, "_lz_env", None)
    if e is None:
        e = win._lz_env = _Env(win._HL)
    return e


def _ctx(win) -> _Ctx:
    c = getattr(win, "_lz_ctx", None)
    if c is None:
        c = win._lz_ctx = _Ctx()
    return c


def _view(bug, env: _Env) -> PreyView:
    v = getattr(bug, "_lz_view", None)
    if v is None:
        v = bug._lz_view = PreyView(bug, env)
    return v


def _clamp_legs(bug) -> None:
    """EggBugGfx._legs 末尾那句的重做：脚离髋超过腿长就拉回，脚的上一帧位置同样（绘制按两者插值）。"""
    from ..eggbug.gfx import LEG_LEN

    g = bug.gfx
    for i, leg in enumerate(g.legs):
        hx, hy = g.hip(i)
        for a, b in ((0, 1), (2, 3)):
            dx, dy = leg[a] - hx, leg[b] - hy
            d = math.hypot(dx, dy)
            if d > LEG_LEN:
                leg[a], leg[b] = hx + dx / d * LEG_LEN, hy + dy / d * LEG_LEN


def _egg_source(win, egg, env: _Env) -> EggSource:
    """蛋有 __slots__，噪音源按 id 记在窗口上。"""
    d = getattr(win, "_lz_egg_src", None)
    if d is None:
        d = win._lz_egg_src = {}
    v = d.get(id(egg))
    if v is None or v.egg is not egg:
        v = d[id(egg)] = EggSource(egg, env)
    return v


def _eggbug_kind():
    from ..eggbug import KIND

    return KIND


GREEN = LizardKind("lizard_green", "green", True)
PINK = LizardKind("lizard_pink", "pink", False)
CYAN = LizardKind("lizard_cyan", "cyan", False)
BLUE = LizardKind("lizard_blue", "blue", False)
WHITE = LizardKind("lizard_white", "white", False)
RED = LizardKind("lizard_red", "red", False)
KINDS = (GREEN, PINK, BLUE, CYAN, WHITE, RED)
