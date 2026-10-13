"""竖杆和横杆：竖杆立在地上，横杆从最近的侧边伸出；能爬。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPainterPathStroker, QPen

from ...core.vecmath import _seg_dist
from ..base import CLIMBABLE, ItemKind
from ..state import ItemState
from .model import HORIZONTAL, MIN_LENGTH, POLE_RAD, TOP_MARGIN, VERTICAL, Pole

POLE_COLOR = (28, 28, 31)

_ICON_EDGE = QColor(20, 22, 26)
_ICON_SHEEN = QColor(104, 112, 126)
_ICON_CORE = QColor(40, 42, 47)
_ICON_TILE = QColor(255, 255, 255, 12)


def _ends(win, kind, lx, ly):
    if kind == VERTICAL:
        top = min(max(ly, TOP_MARGIN), win._HL - MIN_LENGTH)
        return lx, win._HL, lx, top
    ax = 0.0 if lx < win._WL * 0.5 else win._WL
    end = lx
    if abs(end - ax) < MIN_LENGTH:
        end = ax + (MIN_LENGTH if ax == 0.0 else -MIN_LENGTH)
    return ax, ly, end, ly


def _rod(p, ax, ay, bx, by):
    core = QPen(QColor(*POLE_COLOR))
    core.setWidthF(POLE_RAD * 2.0)
    core.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(core)
    p.drawLine(QPointF(ax, ay), QPointF(bx, by))


class PoleKind(ItemKind):
    store = "poles"
    seed_key = "pole"
    cap = 6
    affords = frozenset({CLIMBABLE})
    layer = "mid"
    mobile = False
    geometry = True
    dead_state = ItemState.GONE

    def __init__(self, key, pole_kind):
        self.key = key
        self.pole_kind = pole_kind

    def objects(self, win):
        return [pl for pl in win.poles if pl.kind == self.pole_kind]

    def make(self, win, lx, ly, seed):
        return Pole(self.pole_kind, *_ends(win, self.pole_kind, lx, ly), seed=seed)

    def tick(self, win):
        """杆不动。"""

    def hit(self, pl, cx, cy):
        if pl.state != ItemState.FREE:
            return None
        return max(0.0, _seg_dist(cx, cy, pl.ax, pl.ay, pl.bx, pl.by) - POLE_RAD)

    def draw_mark(self, p, pl, rad):
        band = QPainterPath()
        band.moveTo(pl.ax, pl.ay)
        band.lineTo(pl.bx, pl.by)
        outline = QPainterPathStroker()
        outline.setWidth(POLE_RAD * 2.0 + 8.0)
        outline.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.drawPath(outline.createStroke(band))

    def floor_shift(self, win, old, new):
        if self.pole_kind == VERTICAL:
            for pl in self.objects(win):
                if abs(pl.ay - old) < 0.5:
                    pl.ay = new

    def draw(self, win, p):
        p.save()
        for pl in win.poles:
            _rod(p, pl.ax, pl.ay, pl.bx, pl.by)
        p.restore()

    def draw_hint(self, win, p, cx, cy):
        p.save()
        p.setOpacity(0.5)
        _rod(p, *_ends(win, self.pole_kind, cx, cy))
        p.restore()

    def paint_icon(self, p, r, atlas):
        from ...ui.widgets import iconkit as ik

        vertical = self.pole_kind == VERTICAL
        w = r.width()
        L, T = r.left(), r.top()

        def Pt(fx, fy):
            return QPointF(L + fx * w, T + fy * r.height())

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_ICON_TILE)
        p.drawRoundedRect(r, w * 0.24, w * 0.24)
        if not ik.cat_ready(atlas):
            _icon_rod(p, r, vertical)
            return
        if vertical:
            ik.blit(p, atlas, "base", "LegsAVerticalPole", Pt(0.60, 0.66), 0.95, w)
            ik.blit(p, atlas, "base", "BodyA", Pt(0.64, 0.48), 0.50, w)
            ik.blit(p, atlas, "base", "PlayerArm0", Pt(0.56, 0.47), 0.36, w, rot=16.0)
            ik.blit(p, atlas, ik.HEAD_ATLAS, ik.HEAD_FAM + "0", Pt(0.64, 0.30), 0.46, w)
            ik.blit(p, atlas, ik.FACE_ATLAS, ik.FACE_FAM + "1", Pt(0.64, 0.28), 0.46, w, tint=ik.ICON_EYE)
            ik.blit(p, atlas, "base", "OnTopOfTerrainHand", Pt(0.39, 0.35), 0.37, w)
            _icon_rod(p, r, vertical)
            ik.blit(p, atlas, "base", "OnTopOfTerrainHand", Pt(0.575, 0.47), 0.37, w)
        else:
            p.setPen(ik.pen(ik.ICON_SAINT, 0.11 * w))
            p.drawLine(Pt(0.5, 0.78), Pt(0.5, 0.88))
            p.setPen(ik.pen(ik.ICON_SAINT, 0.045 * w))
            p.drawLine(Pt(0.5, 0.88), Pt(0.44, 0.97))
            p.drawLine(Pt(0.5, 0.88), Pt(0.56, 0.97))
            ik.blit(p, atlas, "ui", ik.CAT_HEAD, Pt(0.5, 0.82), 0.60, w)
            p.setPen(ik.pen(ik.ICON_SAINT, 0.055 * w))
            p.drawLine(Pt(0.45, 0.74), Pt(0.415, 0.325))
            p.drawLine(Pt(0.55, 0.74), Pt(0.585, 0.325))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ik.ICON_SAINT)
            rr = 0.033 * w
            for hx in (0.415, 0.585):
                p.drawEllipse(Pt(hx, 0.325), rr, rr)
            _icon_rod(p, r, vertical)


def _icon_rod(p, r, vertical):
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    if vertical:
        bw = w * 0.22
        rod = QRectF(cx - bw / 2, r.top() + h * 0.04, bw, h * 0.92)
        g = QLinearGradient(rod.left(), 0.0, rod.right(), 0.0)
        rad = bw / 2
    else:
        bh = h * 0.24
        rod = QRectF(r.left() + w * 0.04, cy - bh / 2, w * 0.92, bh)
        g = QLinearGradient(0.0, rod.top(), 0.0, rod.bottom())
        rad = bh / 2
    g.setColorAt(0.0, _ICON_EDGE)
    g.setColorAt(0.30, _ICON_SHEEN)
    g.setColorAt(0.55, _ICON_CORE)
    g.setColorAt(1.0, _ICON_EDGE)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(rod, rad, rad)


VPOLE = PoleKind("vpole", VERTICAL)
HPOLE = PoleKind("hpole", HORIZONTAL)
