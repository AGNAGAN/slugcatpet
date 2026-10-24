"""蛋虫：在地上乱跑、怕猫和光标、受惊会跳；场上同时只有一只活的，死了的过一阵消解。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from ...core.units import clampf, lerp
from ...core.vecmath import _ang_from_up
from ...rendering.primitives import blit
from ...world.liquid_drip import draw_drips
from ..base import CARRYABLE, EDIBLE, THROWABLE, ItemKind, alive_creature, creatures
from ..state import ItemState
from .palette import colors, mix as _mix
from .gfx import ANT_SEGS, EGG_PER_ROW, SHIN, THIGH, dist_to_line, ik
from ..bugegg.model import RAD as EGG_RAD
from .model import EggBug

CORPSE_TICKS = 7200  # 尸体没人碰时多久开始消解
EATEN_LINGER = 200  # 啃完扔开后再留这么久
BURST_SPEED = 16.0
SHELTER_MARGIN = 20.0
BODY_PTS = 7
HEAD_RX, HEAD_RY = 4.5, 5.5
EGG_SX, EGG_SY = 0.7, 0.75
EGG_DOT = 0.45
EYE_RAD = 2.0
ANT_W = 1.0  # 触角半宽
ICON_SYMBOL = "Kill_EggBug"
PREVIEW_BOX = 240.0  # 放置预览先画到这么大的透明图上再整体半透明
ICON_COLOR = QColor(0, 255, 120)


class EggBugKind(ItemKind):
    key = "eggbug"
    store = "eggbugs"
    apps = ("slugcat", "lizard")
    affords = frozenset({EDIBLE, CARRYABLE})
    varies = True
    cap = None
    collides = True
    grab_pad = 7.0
    grab_rank = 3

    def affords_now(self, b, use):
        if use == EDIBLE:
            return b.edible
        return b.dead and b.dissolve < 0

    def can_place(self, win):
        return not any(not b.dead for b in win.eggbugs if b.dissolve < 0)

    def make(self, win, lx, ly, seed):
        for b in win.eggbugs:
            if b.dead:
                self.dissolve(win, b)
        return EggBug(lx, ly, seed=seed)

    def drop(self, win, b):
        for pet in win.pets:
            pet.body.release(b)
        b.held_by_hand = None
        b.state = self.dead_state

    def hit(self, b, cx, cy):
        if b.state in (ItemState.EATEN, ItemState.GONE) or b.dissolve >= 0:
            return None
        return b.dist_to(cx, cy)

    def grab_dist(self, b, cx, cy):
        return b.dist_to(cx, cy) + b.rad

    def draw_mark(self, p, b, rad):
        for c in (b.c0, b.c1):
            p.drawEllipse(QPointF(c.x, c.y), c.rad + 4.0, c.rad + 4.0)

    def on_grab(self, b):
        b.held_by_hand = None
        b.footing = 0

    def tick(self, win):
        bugs = win.eggbugs
        if not bugs:
            return
        threats = _threats(win)
        weapons = [(id(w), w.x, w.y, w.vx, w.vy) for w in win.items_affording(THROWABLE) if w.in_flight()]
        rain = win.rain
        wet = rain.dangerous()
        for b in bugs:
            shelter = None
            if wet and rain.exposed(b.x, b.y):
                shelter = rain.nearest_shelter_x(b.x, 0.0, win._WL, SHELTER_MARGIN)
            b.sense(threats, weapons, win._WL, win._HL, shelter)
            if b.dead and b.dissolve < 0 and b.state == ItemState.FREE and b.held_by_hand is None:
                b.corpse_age = getattr(b, "corpse_age", 0) + 1
                if b.meat <= 0:
                    b.corpse_age = max(b.corpse_age, CORPSE_TICKS - EATEN_LINGER)
                if b.corpse_age >= CORPSE_TICKS:
                    self.dissolve(win, b)
        super().tick(win)
        for b in win.eggbugs:
            if b.burst:
                b.burst = False
                _burst(win, b)

    def draw(self, win, p):
        ts = win._ts
        for b in win.eggbugs:
            if b.state in (ItemState.EATEN, ItemState.GONE):
                continue
            a = self.dissolve_alpha(b, ts)
            if a <= 0.0:
                continue
            draw_bug(win, p, b, ts, a)

    def on_enter_place(self, win):
        win._place_preview = EggBug(0.0, 0.0, seed=win.item_seed(self))

    def draw_hint(self, win, p, cx, cy):
        """光标处半透明的一只，和放下去的同一个样子，悬空蹬腿。"""
        b = getattr(win, "_place_preview", None)
        if b is None:
            return
        half = (b.c0.x - b.c1.x) * 0.5
        for c, x in ((b.c0, cx + half), (b.c1, cx - half)):
            c.x = c.last_x = x
            c.y = c.last_y = cy
        b.gfx.update(win._HL)
        s, box = win._scale, PREVIEW_BOX
        pm = QPixmap(int(box * s), int(box * s))
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.scale(s, s)
        q.translate(box * 0.5 - cx, box * 0.5 - cy)
        draw_bug(win, q, b, 1.0)
        q.end()
        pm.setDevicePixelRatio(s)
        p.save()
        p.setOpacity(0.5)
        p.drawPixmap(QPointF(cx - box * 0.5, cy - box * 0.5), pm)
        p.restore()

    def paint_icon(self, p, r, atlas):
        if atlas is not None and atlas.get("ui").has(ICON_SYMBOL):
            sw, sh = atlas.source_size("ui", ICON_SYMBOL)
            s = min(r.width() / sw, r.height() / sh) * 0.92
            dw, dh = sw * s, sh * s
            pm = atlas.sprite("ui", ICON_SYMBOL, ICON_COLOR)
            p.drawPixmap(
                QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh), pm, QRectF(pm.rect())
            )
            return
        _icon_shape(p, r.center().x(), r.center().y(), r.width(), r.height())


def _burst(win, b):
    """死时背上的六个蛋飞出去：大多往上，速度偏快。"""
    g, rng = b.gfx, b._rng
    b.has_eggs = False
    for x, y, vx, vy in g.eggs:
        e = win.spawn("bugegg", x, y)
        if e is None:
            continue
        a = math.radians(180.0 * rng.random() ** 3 * (1.0 if rng.random() < 0.5 else -1.0))
        sp = BURST_SPEED * rng.random() ** 0.3
        e.vx, e.vy = vx + math.sin(a) * sp, vy - math.cos(a) * sp
        e.hue = g.hue
        e.swell, e.liquid = 0.0, 1.0
        e.rad = EGG_RAD
        e.rot_vel = rng.uniform(-20.0, 20.0)
        a = rng.uniform(0.0, math.tau)
        e.set_rotation(math.cos(a), math.sin(a))


def _threats(win):
    """猫（活着、没藏起来）、场上活着的捕食者和光标；正在被光标拖的蛋虫不怕光标。"""
    out = []
    for pet in win.pets:
        b = pet.body
        if pet.behavior is None or b.dead:
            continue
        out.append((id(pet), (b.chunk0.x + b.chunk1.x) * 0.5, (b.chunk0.y + b.chunk1.y) * 0.5))
    for o in creatures(win):
        if getattr(o, "predator", False) and alive_creature(o):
            out.append((id(o), o.x, o.y))
    drag = getattr(win, "_drag", None)
    if drag is None or drag[0] is not KIND:
        cur = win.cursor_logical()
        if cur is not None and 0.0 <= cur[0] <= win._WL and 0.0 <= cur[1] <= win._HL:
            out.append(("cursor", cur[0], cur[1]))
    return out


# 绘制


def _lp(a, b, t):
    return a + (b - a) * t


def _bezier(p0, p1, p2, p3, t):
    u = 1.0 - t
    a, b, c, d = u * u * u, 3.0 * u * u * t, 3.0 * u * t * t, t * t * t
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
    )


def draw_bug(win, p, b, ts, alpha=1.0):
    g = b.gfx
    col = colors(g)
    atlas = win.atlas
    c0, c1 = b.c0, b.c1
    j = g.jitter
    hx, hy = _lp(c0.last_x, c0.x, ts) + j[0], _lp(c0.last_y, c0.y, ts) + j[1]
    rx, ry = _lp(c1.last_x, c1.x, ts) + j[2], _lp(c1.last_y, c1.y, ts) + j[3]
    tx, ty = _lp(g.last_tail[0], g.tail[0], ts), _lp(g.last_tail[1], g.tail[1], ts)
    dx, dy = hx - rx, hy - ry
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    px, py = -dy, dx
    flip = _lp(g.last_flip, g.flip, ts)
    black = QColor(*col["black"])

    p.save()
    if alpha < 1.0:
        p.setOpacity(p.opacity() * alpha)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)

    eyes = []
    for i in range(2):
        k = (-1.0 if (i == 0) == (flip < 0.0) else 1.0) * (1.0 - abs(flip)) * 3.0
        eyes.append(QPointF(hx + dx * 4.0 + px * k, hy + dy * 4.0 + py * k))
    eye = QColor(*col["eye"])
    p.setBrush(eye)
    p.drawEllipse(eyes[0], EYE_RAD, EYE_RAD)

    eggs = [(_lp(lx, e[0], ts), _lp(ly, e[1], ts)) for e, (lx, ly) in zip(g.eggs, g.last_eggs)]
    attach = [g.egg_attach(i) for i in range(len(g.eggs))]
    order = [r * EGG_PER_ROW + e for r in range(2) for e in reversed(range(EGG_PER_ROW))]
    for i in order:
        _egg(p, atlas, g.show_eggs, eggs[i], attach[i], hx, hy, col, front=False)

    # 身体：头 → 腹 → 尾尖的三次贝塞尔，两头尖、中间宽，侧翻时变窄
    tlx, tly = tx - rx, ty - ry
    tn = math.hypot(tlx, tly) or 1.0
    p0 = (hx + dx * 3.0, hy + dy * 3.0)
    p3 = (tx + tlx / tn * 3.0, ty + tly / tn * 3.0)
    pts = [_bezier(p0, (rx, ry), (rx, ry), p3, i / (BODY_PTS - 1)) for i in range(BODY_PTS)]
    wide = lerp(7.0, 5.0, abs(flip))
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        a = pts[max(0, i - 1)]
        c = pts[min(BODY_PTS - 1, i + 1)]
        nx, ny = c[0] - a[0], c[1] - a[1]
        nn = math.hypot(nx, ny) or 1.0
        nx, ny = -ny / nn, nx / nn
        f = i / (BODY_PTS - 1)
        w = lerp(1.5, wide, clampf(math.sin(f**0.75 * math.pi), 0.0, 1.0) ** 0.3)
        left.append(QPointF(x + nx * w, y + ny * w))
        right.append(QPointF(x - nx * w, y - ny * w))
    path = QPainterPath(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    p.setBrush(black)
    p.drawPath(path)

    p.save()
    p.translate(hx, hy)
    p.rotate(_ang_from_up(dx, dy))
    p.drawEllipse(QPointF(0.0, 0.0), HEAD_RX, HEAD_RY)
    p.restore()

    _antennae(p, g, ts, hx, hy, col)

    p.setBrush(eye)
    p.drawEllipse(eyes[1], EYE_RAD, EYE_RAD)

    _legs(p, atlas, g, ts, hx, hy, rx, ry, dx, dy, flip, black)

    for i in order:
        if g.row_in_front(i // EGG_PER_ROW, ts):
            _egg(p, atlas, g.show_eggs, eggs[i], attach[i], hx, hy, col, front=True)

    if g.drips:
        draw_drips(p, g.drips, ts, col["drip"], col["blood"])
    p.restore()


def _egg(p, atlas, full, pos, att, hx, hy, col, front):
    """背上的一个蛋：身后一层是带黑壳的整蛋，朝外那排在身前再叠一层亮色；蛋没了只剩空窝。"""
    if not full:
        rot = _ang_from_up(hx - att[0], hy - att[1])
        blit(p, atlas, "JetFishEyeA", att[0], att[1], rot, 0.2, 0.35, col["stub"])
        return
    x, y = pos
    rot = _ang_from_up(att[0] - x, att[1] - y)
    if atlas.find_atlas("DangleFruit0A") is None:
        p.setBrush(QColor(*col["glow"]))
        p.drawEllipse(QPointF(x, y), 3.0, 4.2)
        return
    if front:
        blit(p, atlas, "EggBugEggColor", x, y, rot, EGG_SX, EGG_SY, col["glow"], ay=0.7)
    else:
        blit(p, atlas, "DangleFruit0A", x, y, rot, EGG_SX, EGG_SY, col["black"], ay=0.7)
        blit(p, atlas, "DangleFruit0B", x, y, rot, EGG_SX, EGG_SY, col["glow"], ay=0.7)
    blit(p, atlas, "JetFishEyeA", x, y, rot, EGG_DOT, EGG_DOT, col["dot"], ay=0.3)


def _antennae(p, g, ts, hx, hy, col):
    """两根触角：从头中心起、宽 2 的细条，颜色由黑渐变到尖上的色，只有最后一段收尖。"""
    black, tip = col["black"], col["tip"]
    for s in range(2):
        px, py = hx, hy
        for i in range(ANT_SEGS):
            lx, ly = g.last_ants[s][i]
            x, y = _lp(lx, g.ants[s][i][0], ts), _lp(ly, g.ants[s][i][1], ts)
            nx, ny = x - px, y - py
            nn = math.hypot(nx, ny) or 1.0
            nx, ny = -ny / nn * ANT_W, nx / nn * ANT_W
            poly = [QPointF(px + nx, py + ny), QPointF(px - nx, py - ny)]
            if i < ANT_SEGS - 1:
                poly += [QPointF(x - nx, y - ny), QPointF(x + nx, y + ny)]
            else:
                poly.append(QPointF(x, y))
            p.setBrush(QColor(*_mix(black, tip, (i + 0.5) / ANT_SEGS)))
            p.drawPolygon(poly)
            px, py = x, y


def _legs(p, atlas, g, ts, hx, hy, rx, ry, dx, dy, flip, black):
    """四条两节腿（蜈蚣腿贴图）：腿根随侧翻左右分开，膝盖弯向和弯度随脚的位置变。"""
    px, py = -dy, dx
    sprites = atlas.find_atlas("CentipedeLegA") is not None
    bx, by = rx - dx * 20.0, ry - dy * 20.0
    fl = abs(flip)
    for i, leg in enumerate(g.legs):
        side = -1.0 if i % 2 == 0 else 1.0
        k = side * 3.0 * (1.0 - fl)
        f = 4.0 if i < 2 else -4.0
        sx = lerp(hx, rx, 0.3) + px * k + dx * f
        sy = lerp(hy, ry, 0.3) + py * k + dy * f
        fx, fy = _lp(leg[2], leg[0], ts), _lp(leg[3], leg[1], ts)
        d = math.hypot(fx - sx, fy - sy)
        if d < 6.0:
            ux, uy = ((fx - sx) / d, (fy - sy) / d) if d > 1e-6 else (0.0, 1.0)
            fx, fy = sx + ux * 6.0, sy + uy * 6.0
        f2 = lerp(side, flip * clampf(dist_to_line(fx, fy, bx, by, bx + px, by + py) / -20.0, -1.0, 1.0), fl)
        kx, ky = ik(sx, sy, fx, fy, THIGH, SHIN, f2)
        if sprites:
            dk = math.hypot(kx - sx, ky - sy)
            df = math.hypot(fx - kx, fy - ky)
            fs = -math.copysign(1.0, flip)
            blit(
                p,
                atlas,
                "CentipedeLegA",
                sx,
                sy,
                _ang_from_up(kx - sx, ky - sy),
                fs * 0.8,
                dk / 27.0,
                black,
                ay=0.9,
            )
            fs = -math.copysign(1.0, f2)
            blit(
                p,
                atlas,
                "CentipedeLegB",
                kx,
                ky,
                _ang_from_up(fx - kx, fy - ky),
                fs,
                (df + 1.0) / 25.0,
                black,
                ay=0.9,
            )
            continue
        pen = QPen(black, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(sx, sy), QPointF(kx, ky))
        p.drawLine(QPointF(kx, ky), QPointF(fx, fy))
        p.setPen(Qt.PenStyle.NoPen)


def _icon_shape(p, cx, cy, w, h):
    """没有游戏 UI 图集时的图标：黑身子、四条腿、背上三颗青色的蛋。"""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    body = QColor(24, 22, 26)
    pen = QPen(body, max(1.2, w * 0.06))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    by = cy + h * 0.08
    for fx in (-0.34, -0.12, 0.14, 0.36):
        kx = cx + w * fx * 0.8
        p.drawLine(QPointF(kx, by), QPointF(kx + w * 0.04, by - h * 0.12))
        p.drawLine(QPointF(kx + w * 0.04, by - h * 0.12), QPointF(cx + w * fx * 1.15, by + h * 0.3))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body)
    r = QRectF(0.0, 0.0, w * 0.7, h * 0.36)
    r.moveCenter(QPointF(cx - w * 0.04, by))
    p.drawEllipse(r)
    p.drawEllipse(QPointF(cx + w * 0.33, by - h * 0.02), w * 0.1, h * 0.12)
    p.setBrush(QColor(60, 235, 215))
    for i in range(3):
        p.drawEllipse(QPointF(cx - w * (0.24 - i * 0.15), by - h * 0.2), w * 0.065, h * 0.1)
    p.restore()


KIND = EggBugKind()
