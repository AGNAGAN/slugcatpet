"""黏菌：粘在最近的屏幕边上，触须随风晃，暗时发光；能吃、能叼。"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPolygonF, QRadialGradient

from ...core.gfxmath import _hsl2rgb
from ...core.units import clampf, inv_lerp, lerp
from ...rendering.graphics import _ang_from_up
from ...rendering.primitives import blit, draw_fruit
from ..base import CARRYABLE, EDIBLE, ItemKind
from ..state import ItemState
from .model import STUCK_GAP, TENDRIL_JAG_K, SlimeMold, _dirvec, _lerp_map

SLIME_HUE_LIGHT = 0.07
SLIME_HUE_DARK = 0.05
SLIME_BODY_L = 0.55
SLIME_OUTLINE_L = 0.25
SLIME_DARK_LO = 0.3
SLIME_DARK_HI = 0.7
SLIME_DRAW_SCALE = 1.0
SLIME_LIGHT_SCALE = 55.0 / 140.0    # 下调防过曝
SLIME_BLOOM_SCALE = 12.0 / 30.0
SLIME_RESTICK_PAD = 50.0
_JAG_COS = [math.cos(2.0 * math.pi * i / TENDRIL_JAG_K) for i in range(TENDRIL_JAG_K)]
_JAG_SIN = [math.sin(2.0 * math.pi * i / TENDRIL_JAG_K) for i in range(TENDRIL_JAG_K)]

_ICON_BODY = QColor(255, 122, 26)
_ICON_TENDRIL = QColor(204, 92, 16)
_ICON_GLOW = QColor(255, 150, 50, 90)


def _body_rgb(dm, l):
    r, g, b = _hsl2rgb(lerp(SLIME_HUE_LIGHT, SLIME_HUE_DARK, dm), 1.0, l)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def _saturate(rgb):
    mn, mx = min(rgb), max(rgb)
    if mx <= mn:
        return (mx, mx, mx)
    k = mx / (mx - mn)
    return tuple(int(round((c - mn) * k)) for c in rgb)


def _colors(dm):
    body = _body_rgb(dm, SLIME_BODY_L)
    return body, _body_rgb(dm, SLIME_OUTLINE_L), _saturate(body)


def _slerp2(ax, ay, bx, by, t):
    dot = clampf(ax * bx + ay * by, -1.0, 1.0)
    if dot > 0.9995:
        return (ax + (bx - ax) * t, ay + (by - ay) * t)
    theta = math.acos(dot)
    s = math.sin(theta)
    return (ax * math.sin((1.0 - t) * theta) / s + bx * math.sin(t * theta) / s,
            ay * math.sin((1.0 - t) * theta) / s + by * math.sin(t * theta) / s)


def _darkness(win):
    return clampf(inv_lerp(SLIME_DARK_LO, SLIME_DARK_HI, getattr(win, "cold_cycle_prog", 0.0)),
                  0.0, 1.0)


def _edge_anchor(win, lx, ly):
    d = {"top": ly, "bottom": win._HL - ly, "left": lx, "right": win._WL - lx}
    edge = min(d, key=d.get)
    if edge == "top":
        sx, sy, nx, ny = clampf(lx, 0.0, win._WL), 0.0, 0.0, 1.0
    elif edge == "bottom":
        sx, sy, nx, ny = clampf(lx, 0.0, win._WL), win._HL, 0.0, -1.0
    elif edge == "left":
        sx, sy, nx, ny = 0.0, clampf(ly, 0.0, win._HL), 1.0, 0.0
    else:
        sx, sy, nx, ny = win._WL, clampf(ly, 0.0, win._HL), -1.0, 0.0
    return sx, sy, sx + nx * STUCK_GAP, sy + ny * STUCK_GAP


class SlimeMoldKind(ItemKind):
    key = "slimemold"
    store = "slimemolds"
    affords = frozenset({EDIBLE, CARRYABLE})
    collides = True
    grab_pad = 7.0
    grab_states = (ItemState.FREE, ItemState.HANGING)
    grab_rank = 0
    splash_states = (ItemState.FREE, ItemState.HANGING)

    def make(self, win, lx, ly, seed):
        sx, sy, bx, by = _edge_anchor(win, lx, ly)
        m = SlimeMold(bx, by, seed=seed)
        m.stick_to(sx, sy)
        return m

    def on_enter_place(self, win):
        win._place_preview = SlimeMold(0.0, 0.0, seed=win.item_seed(self))

    def drop(self, win, m):
        for pet in win.pets:
            if m is pet.body.carried_fruit:
                pet.body.release_fruit()
        m.state = ItemState.EATEN

    def on_grab(self, m):
        m.stuck_pos = None
        m.held_by_hand = None

    def on_release(self, win, m):
        if m.state != ItemState.MOUSE:
            return
        d = {"top": m.y, "left": m.x, "right": win._WL - m.x}
        edge = min(d, key=d.get)
        if d[edge] <= SLIME_RESTICK_PAD:
            sx, sy, _, _ = _edge_anchor(win, m.x, m.y)
            m.vx = m.vy = 0.0
            m.stick_to(sx, sy)
        else:
            m.state = ItemState.FREE

    def draw(self, win, p):
        dm = _darkness(win)
        for m in win.slimemolds:
            _draw_one(win, p, m, dm)

    def draw_hint(self, win, p, cx, cy):
        m = getattr(win, "_place_preview", None)
        if m is None:
            return
        sx, sy, bx, by = _edge_anchor(win, cx, cy)
        m.x, m.y = bx, by
        if m.stuck_pos is None:
            m.stick_to(sx, sy)
        else:
            m.stuck_pos = (sx, sy)
            ux, uy = _dirvec(bx, by, sx, sy)
            m.rotation = (-ux, -uy)
        m.step(win._WL, win._HL)
        p.save()
        p.setOpacity(0.5)
        _draw_one(win, p, m, _darkness(win))
        p.restore()

    def paint_icon(self, p, r, atlas):
        if atlas is not None and atlas.get("ui").has("Symbol_SlimeMold"):
            sw, sh = atlas.source_size("ui", "Symbol_SlimeMold")
            s = min(r.width() / sw, r.height() / sh) * 0.92
            dw, dh = sw * s, sh * s
            pm = atlas.sprite("ui", "Symbol_SlimeMold", _ICON_BODY)
            p.drawPixmap(QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh),
                         pm, QRectF(pm.rect()))
            return
        from ...ui.widgets.iconkit import pen
        cx, cy = r.center().x(), r.center().y()
        w, h = r.width(), r.height()
        bx, by = cx, cy - h * 0.14
        glow_r = min(w, h) * 0.42
        grad = QRadialGradient(QPointF(bx, by), glow_r)
        grad.setColorAt(0.0, _ICON_GLOW)
        grad.setColorAt(1.0, QColor(255, 150, 50, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QPointF(bx, by), glow_r, glow_r)
        p.setPen(pen(_ICON_TENDRIL, max(1.6, w * 0.09)))
        for dx in (-0.22, -0.05, 0.12, 0.28):
            sx = bx + dx * w
            p.drawLine(QPointF(sx, by + h * 0.06), QPointF(sx + dx * w * 0.25, by + h * 0.42))
        d = min(w, h) * 0.34
        bulb = QRectF(0, 0, d, d)
        bulb.moveCenter(QPointF(bx, by))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_ICON_BODY)
        p.drawEllipse(bulb)


def _draw_one(win, p, m, dm):
    ts = win._ts
    atlas = win.atlas
    body, outline, glow = _colors(dm)
    x = m.last_x + (m.x - m.last_x) * ts
    y = m.last_y + (m.y - m.last_y) * ts
    vx, vy = _slerp2(m.last_rotation[0], m.last_rotation[1], m.rotation[0], m.rotation[1], ts)
    rot_deg = _ang_from_up(vx, vy) + 180.0
    draw_fruit(p, atlas, x, y, rot_deg, m.bites, flesh_color=body, outline_color=outline,
               scalex=SLIME_DRAW_SCALE, scaley=SLIME_DRAW_SCALE * 0.85)
    if m.state != ItemState.EATEN:
        _draw_tendrils(win, p, m, body)
    hox = (-2.0 * (1.0 - dm) + vx * (1.0 + dm)) * SLIME_DRAW_SCALE
    hoy = (-2.0 * (1.0 - dm) + vy * (1.0 + dm)) * SLIME_DRAW_SCALE
    hl_t = lerp(0.5, 0.2, dm)
    hlc = (int(lerp(body[0], 255, hl_t)), int(lerp(body[1], 255, hl_t)),
           int(lerp(body[2], 255, hl_t)))
    hsx = _lerp_map(m.bites, 3.0, 1.0, 0.25, 0.15) * SLIME_DRAW_SCALE
    hsy = _lerp_map(m.bites, 3.0, 1.0, 0.30, 0.05) * SLIME_DRAW_SCALE
    if atlas.find_atlas("Circle20") is not None:
        blit(p, atlas, "Circle20", x + hox, y + hoy, rot_deg, hsx, hsy, hlc)
    else:
        p.save(); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(*hlc))
        p.translate(x + hox, y + hoy); p.rotate(rot_deg)
        p.scale(hsx * 20.0, hsy * 20.0)
        p.drawEllipse(QPointF(0.0, 0.0), 0.5, 0.5); p.restore()
    if dm > 0.0:
        light_r = _lerp_map(m.bites, 3.0, 1.0, 140.0, 40.0) * SLIME_LIGHT_SCALE
        bloom_r = _lerp_map(m.bites, 3.0, 1.0, 30.0, 10.0) * SLIME_BLOOM_SCALE
        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setPen(Qt.PenStyle.NoPen)
        for gr, ga in ((light_r, 0.12 * dm), (bloom_r, 0.25 * dm)):
            grad = QRadialGradient(QPointF(x, y), gr)
            a = int(clampf(ga, 0.0, 1.0) * 255)
            c0 = QColor(*glow); c0.setAlpha(a)
            cm = QColor(*glow); cm.setAlpha(a)          # 0.35 前不淡出，更柔
            c1 = QColor(*glow); c1.setAlpha(0)
            grad.setColorAt(0.0, c0); grad.setColorAt(0.35, cm); grad.setColorAt(1.0, c1)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(x, y), gr, gr)
        p.restore()


def _draw_tendrils(win, p, m, body):
    """逐根触须画锯齿团；alpha 值当形状种子，非透明度。"""
    ts = win._ts
    T = m.tendrils
    n = len(T)
    polys = m._tendril_polys
    if polys is None:
        polys = [QPolygonF([QPointF(0.5 * jf[k] * _JAG_COS[k], 0.5 * jf[k] * _JAG_SIN[k])
                            for k in range(TENDRIL_JAG_K)])
                 for jf in m.tendril_jag]
        m._tendril_polys = polys
    bx = m.last_x + (m.x - m.last_x) * ts
    by = m.last_y + (m.y - m.last_y) * ts
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(*body)))
    for idx, tg in enumerate(T):
        tx = tg[2] + (tg[0] - tg[2]) * ts
        ty = tg[3] + (tg[1] - tg[3]) * ts
        link = int(tg[6])
        if link < 0 or link >= n:
            ax, ay = bx, by
        else:
            pt = T[link]
            ax = pt[2] + (pt[0] - pt[2]) * ts
            ay = pt[3] + (pt[1] - pt[3]) * ts
        dist = math.hypot(ax - tx, ay - ty)
        length = dist + 3.0
        width = lerp(4.0, 1.5, inv_lerp(0.0, tg[7] * 3.5, dist) ** 2)
        rot = _ang_from_up(ax - tx, ay - ty)
        p.save()
        p.translate(tx, ty)
        if rot:
            p.rotate(rot)
        p.translate(0.0, -0.45 * length)                 # anchorY=0.05
        p.scale(width, length)
        p.drawPolygon(polys[idx])
        p.restore()
    p.restore()


KIND = SlimeMoldKind()
