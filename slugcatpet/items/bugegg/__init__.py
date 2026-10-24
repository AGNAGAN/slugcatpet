"""蛋虫蛋：蛋虫死时从背上爆出来，谁都能吃、肉食的猫也得满格；不能手动放，太多时最早的先消解。
蜥蜴 app 里没人吃，放久了也消解。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from ...core.units import lerp
from ...core.vecmath import _ang_from_up
from ...rendering.primitives import blit
from ...world.liquid_drip import draw_drips
from ..base import CARRYABLE, EDIBLE, ItemKind, dump_loose
from ..eggbug.palette import palette
from ..state import ItemState
from .model import BITES, BugEgg

EGG_SX, EGG_SY = 0.7, 0.75
EGG_DOT = 0.45
STALK_W = 1.0
LIZARD_LINGER_TICKS = 1200  # 蜥蜴 app 里没有猫来吃：没人碰地躺这么久就消解


class BugEggKind(ItemKind):
    key = "bugegg"
    store = "bugeggs"
    apps = ("slugcat", "lizard")
    placeable = False
    affords = frozenset({EDIBLE, CARRYABLE})
    varies = True
    collides = True
    cap = 12
    grab_pad = 6.0
    grab_rank = 2

    def affords_now(self, e, use):
        return e.dissolve < 0

    def make(self, win, lx, ly, seed):
        return BugEgg(lx, ly, seed=seed)

    def dump(self, e):
        return dump_loose(e, hue=e.hue, bites=e.bites, swell=e.swell)

    def load(self, win, d, fit):
        x, y = fit.inside(float(d["x"]), float(d["y"]))
        e = BugEgg(x, y, seed=int(d.get("seed", 0)), hue=float(d.get("hue", 0.0)))
        e._bites = int(d.get("bites", BITES))
        e.swell = float(d.get("swell", 1.0))
        return e

    def make_room(self, win):
        live = [e for e in win.bugeggs if e.dissolve < 0]
        if len(live) < self.cap:
            return True
        old = next((e for e in live if e.state == ItemState.FREE and e.held_by_hand is None), None)
        if old is None:
            return False
        self.dissolve(win, old)
        return True

    def tick(self, win):
        from .. import LIZARD, app

        if app() == LIZARD:
            for e in win.bugeggs:
                if e.dissolve < 0 and e.state == ItemState.FREE and e.held_by_hand is None:
                    e.age += 1
                    if e.age >= LIZARD_LINGER_TICKS:
                        self.dissolve(win, e)
        super().tick(win)

    def drop(self, win, e):
        for pet in win.pets:
            pet.body.release(e)
        e.held_by_hand = None
        e.state = ItemState.EATEN

    def hit(self, e, cx, cy):
        if e.dissolve >= 0:
            return None
        return super().hit(e, cx, cy)

    def on_grab(self, e):
        e.held_by_hand = None

    def draw(self, win, p):
        ts = win._ts
        for e in win.bugeggs:
            if e.state in (ItemState.EATEN, ItemState.GONE):
                continue
            a = self.dissolve_alpha(e, ts)
            if a <= 0.0:
                continue
            x = e.last_x + (e.x - e.last_x) * ts
            y = e.last_y + (e.y - e.last_y) * ts
            r0, r1 = e.last_rotation, e.rotation
            rx, ry = r0[0] + (r1[0] - r0[0]) * ts, r0[1] + (r1[1] - r0[1]) * ts
            p.save()
            if a < 1.0:
                p.setOpacity(p.opacity() * a)
            stalk = [(s[2] + (s[0] - s[2]) * ts, s[3] + (s[1] - s[3]) * ts) for s in e.stalk_pts]
            draw_egg(p, win.atlas, x, y, rx, ry, e.swell_fac, e.bites, palette(e.hue), stalk)
            if e.drips:
                draw_drips(p, e.drips, ts, palette(e.hue)["drip"])
            p.restore()

    def paint_icon(self, p, r, atlas):
        c = r.center()
        draw_egg(p, atlas, c.x(), c.y(), 0.0, -1.0, r.height() / 16.0, BITES, palette(0.0))


def draw_egg(p, atlas, x, y, rx, ry, sf, bites, col, stalk=()):
    """一个蛋：尖上一截渐细的软柄、蛋壳、发光的蛋黄、红点；咬过一口换成缺口的样子，柄也没了。"""
    rot = _ang_from_up(rx, ry)
    cx, cy = x - rx * 3.0 * sf, y - ry * 3.0 * sf
    whole = bites >= BITES
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if whole and stalk:
        pen = QPen(QColor(*col["black"]))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        a = QPointF(cx + rx * 5.0 * sf, cy + ry * 5.0 * sf)
        n = len(stalk)
        for i, (sx, sy) in enumerate(stalk):
            pen.setWidthF(2.0 * STALK_W * lerp(1.0, 0.5, (i / (n - 1)) ** 0.25))
            p.setPen(pen)
            b = QPointF(sx, sy)
            p.drawLine(a, b)
            a = b
        p.setPen(Qt.PenStyle.NoPen)
    if atlas is None or atlas.find_atlas("DangleFruit0A") is None:
        p.setBrush(QColor(*col["glow"]))
        p.drawEllipse(QPointF(cx, cy), 3.0 * sf, 4.2 * sf)
        return
    shell = "DangleFruit0A" if whole else "DangleFruit1A"
    glow = "EggBugEggColor" if whole else "EggBugEggColorEaten"
    blit(p, atlas, shell, cx, cy, rot, EGG_SX * sf, EGG_SY * sf, col["black"], ay=0.7)
    blit(p, atlas, glow, cx, cy, rot, EGG_SX * sf, EGG_SY * sf, col["glow"], ay=0.7)
    blit(
        p, atlas, "JetFishEyeA", cx, cy, rot, EGG_DOT * sf, EGG_DOT * sf, col["dot"], ay=0.3 if whole else 0.6
    )


KIND = BugEggKind()
