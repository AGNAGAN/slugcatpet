"""侧边栏小图标共用的笔、配色与图集贴图。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from ...characters import get as get_cat_def

SAINT = get_cat_def("saint")
HEAD_ATLAS, HEAD_FAM = SAINT.frames["head"]
FACE_ATLAS, FACE_FAM = SAINT.frames["face"]
CAT_HEAD = "Kill_Slugcat"

ICON_SAINT = QColor(*SAINT.body_color)
ICON_EYE = QColor(*SAINT.eye_color)
ICON_GREY = QColor(192, 199, 183)
ICON_RED = QColor(210, 96, 84)


def pen(c, w, cap=True):
    p = QPen(c, w)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if cap:
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
    return p


def cat_ready(atlas):
    if atlas is None:
        return False
    base = atlas.get("base")
    return (
        base.has("BodyA")
        and base.has("LegsAVerticalPole")
        and base.has("PlayerArm0")
        and atlas.get(FACE_ATLAS).has(FACE_FAM + "1")
        and base.has("OnTopOfTerrainHand")
        and atlas.get(HEAD_ATLAS).has(HEAD_FAM + "0")
        and atlas.get("ui").has(CAT_HEAD)
    )


def blit(p, atlas, key, frame, center, k, w, rot=0.0, tint=None):
    """图集帧染色缩放绘制；rot 顺时针度。"""
    pm = atlas.sprite(key, frame, tint or ICON_SAINT, padded=False)
    sc = k * w / 22.0
    pw, ph = pm.width() * sc, pm.height() * sc
    p.save()
    p.translate(center.x(), center.y())
    if rot:
        p.rotate(rot)
    p.drawPixmap(QRectF(-pw / 2, -ph / 2, pw, ph), pm, QRectF(pm.rect()))
    p.restore()


def ui_icon(kind: str, color, px: int = 14) -> QIcon:
    """界面小图标（代码绘制，不走字体回退）：reset 回转箭头 / more 三点 / hidden 圈斜杠。"""
    dpr = 3
    pm = QPixmap(px * dpr, px * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    s = float(px)
    w = max(1.4, s * 0.12)
    if kind == "reset":
        r = s * 0.32
        cx = cy = s * 0.5
        p.setPen(pen(c, w))
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 90 * 16, 270 * 16)
        # 箭头在弧的起点（正上方），指向顺时针
        tip = QPointF(cx + r * 0.15, cy - r)
        a = s * 0.2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(tip.x() + a * 0.6, tip.y()),
                    QPointF(tip.x() - a * 0.4, tip.y() - a * 0.6),
                    QPointF(tip.x() - a * 0.4, tip.y() + a * 0.6),
                ]
            )
        )
    elif kind == "more":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        d = s * 0.17
        for i in (-1, 0, 1):
            p.drawEllipse(QPointF(s * 0.5 + i * s * 0.28, s * 0.5), d / 2 + 0.3, d / 2 + 0.3)
    elif kind == "hidden":
        r = s * 0.34
        p.setPen(pen(c, w))
        p.drawEllipse(QPointF(s * 0.5, s * 0.5), r, r)
        k = r * math.sqrt(0.5)
        p.drawLine(QPointF(s * 0.5 - k, s * 0.5 + k), QPointF(s * 0.5 + k, s * 0.5 - k))
    p.end()
    return QIcon(pm)
