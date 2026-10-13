"""皮肤尾巴：游戏的尾巴三角网格，按 DMS 方式贴图。"""
from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QImage, QPixmap, QPolygonF, QTransform

_PADDED = OrderedDict()      # cacheKey -> 四周外扩 1px（复制边缘）的画刷图
_PADDED_CAP = 32

def _tris(n_verts):
    """游戏 / DMS 的尾巴三角：每段两个，段间两个，尾尖一个（N 段共 4N-3 个）。"""
    last = n_verts - 3
    own = [(i, i + 1, i + 2) for k in range(0, last, 4) for i in (k, k + 1)] + [(last, last + 1, last + 2)]
    link = [(i, i + 1, i + 2) for k in range(2, last, 4) for i in (k, k + 1)]
    return tuple(own + link)


def _affine(src, dst):
    (x0, y0), (x1, y1), (x2, y2) = src
    (u0, v0), (u1, v1), (u2, v2) = dst
    a, b = x1 - x0, x2 - x0
    c, d = y1 - y0, y2 - y0
    det = a * d - b * c
    if abs(det) < 1e-9:
        return None
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    p, q = u1 - u0, u2 - u0
    r, s = v1 - v0, v2 - v0
    m11 = p * ia + q * ic
    m21 = p * ib + q * id_
    m12 = r * ia + s * ic
    m22 = r * ib + s * id_
    dx = u0 - m11 * x0 - m21 * y0
    dy = v0 - m12 * x0 - m22 * y0
    return QTransform(m11, m12, m21, m22, dx, dy)


def _padded(pm):
    """边缘复制外扩 1px，画刷平铺时三角边上不会采到对边的像素。"""
    key = pm.cacheKey()
    hit = _PADDED.get(key)
    if hit is not None:
        _PADDED.move_to_end(key)
        return hit
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), np.uint32).reshape(h, img.bytesPerLine() // 4)[:, :w]
    a = np.ascontiguousarray(np.pad(a, 1, mode="edge"))
    out = QPixmap.fromImage(QImage(a.data, w + 2, h + 2, (w + 2) * 4,
                                   QImage.Format.Format_ARGB32_Premultiplied).copy())
    _PADDED[key] = out
    if len(_PADDED) > _PADDED_CAP:
        _PADDED.popitem(last=False)
    return out


def _tri(painter, brush_pm, src, dst):
    tf = _affine(src, dst)
    if tf is None:
        return
    brush = QBrush(brush_pm)
    brush.setTransform(QTransform.fromTranslate(-1.0, -1.0) * tf)
    painter.setBrush(brush)
    painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in dst]))


def game_tail_vertices(root, nodes, root_rad, rads):
    """游戏尾网格的顶点（N 段共 4N-1 个，y 向下）：每段两端各一对，段首尾沿段向内收 1/5，最后一段收成尖。"""
    vx, vy = root
    w = root_rad
    out = []
    for i, ((sx, sy), r) in enumerate(zip(nodes, rads)):
        dx, dy = sx - vx, sy - vy
        d = math.hypot(dx, dy)
        nx, ny = (dx / d, dy / d) if d > 1e-9 else (0.0, 1.0)
        px, py = ny, -nx
        k = 0.0 if i == 0 else d / 5.0
        out.append((vx - px * w + nx * k, vy - py * w + ny * k))
        out.append((vx + px * w + nx * k, vy + py * w + ny * k))
        if i < len(nodes) - 1:
            out.append((sx - px * r - nx * k, sy - py * r - ny * k))
            out.append((sx + px * r - nx * k, sy + py * r - ny * k))
        else:
            out.append((sx, sy))
        w, vx, vy = r, sx, sy
    return out


def draw_game_tail(painter, verts, pm, band=None) -> None:
    """按 DMS MapTailUV 贴图：u=顶点序号/顶点数，偶数顶点取图底、奇数取图顶。
    band 为 0..1 时只用高 1/3 的窗口（0=最下、1=最上），用于不对称尾巴。"""
    nv = len(verts)
    if pm is None or pm.isNull() or nv < 7 or nv % 4 != 3:
        return
    w, h = float(pm.width()), float(pm.height())
    lo, hi = h, 0.0
    if band is not None:
        off = band * (2.0 / 3.0)
        lo, hi = h * (1.0 - off), h * (1.0 - off - 1.0 / 3.0)
    uv = [(w * i / nv, lo if i % 2 == 0 else hi) for i in range(nv)]
    brush_pm = _padded(pm)
    painter.save()
    painter.setRenderHint(painter.RenderHint.Antialiasing, False)
    painter.setPen(Qt.PenStyle.NoPen)
    for a, b, c in _tris(nv):
        _tri(painter, brush_pm, (uv[a], uv[b], uv[c]), (verts[a], verts[b], verts[c]))
    painter.restore()
