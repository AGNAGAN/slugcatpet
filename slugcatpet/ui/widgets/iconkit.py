"""侧边栏小图标共用的笔、配色与图集贴图。"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen

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
