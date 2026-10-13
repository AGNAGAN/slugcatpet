"""共享渲染原语：软绳、带状、atlas sprite 绘制。"""
from __future__ import annotations
import math
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPolygonF
from PySide6.QtCore import QPointF, Qt


def _outline(points, halfwidths) -> QPainterPath:
    n = len(points)
    left, right = [], []
    for i, (cx, cy) in enumerate(points):
        ax, ay = points[max(0, i - 1)]
        bx, by = points[min(n - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L, dx / L
        hw = halfwidths[i]
        left.append(QPointF(cx + nx * hw, cy + ny * hw))
        right.append(QPointF(cx - nx * hw, cy - ny * hw))
    path = QPainterPath()
    path.moveTo(left[0])
    for q in left[1:]:
        path.lineTo(q)
    for q in reversed(right):
        path.lineTo(q)
    path.closeSubpath()
    path.setFillRule(Qt.FillRule.WindingFill)
    return path


def draw_rope(painter, points, widths, color) -> None:
    """沿点链画锥形软绳；points 根→尖，widths 各点全宽。"""
    if len(points) < 2:
        return
    half = [w * 0.5 for w in widths]
    path = _outline(points, half)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(*color) if not isinstance(color, QColor) else color)
    painter.drawPath(path)
    tx, ty = points[-1]
    painter.drawEllipse(QPointF(tx, ty), half[-1], half[-1])
    painter.restore()


def blit(painter, atlas, element, x, y, rotation, scale_x, scale_y, color,
         ax=0.5, ay=0.5) -> None:
    key = atlas.find_atlas(element)
    if key is None:
        return
    col = color if isinstance(color, QColor) else QColor(*color)
    pm = atlas.sprite(key, element, col)
    sw, sh = atlas.source_size(key, element)
    apx, apy = ax * sw, ay * sh
    painter.save()
    painter.translate(x, y)
    if rotation:
        painter.rotate(rotation)
    painter.scale(scale_x, scale_y)
    painter.drawPixmap(QPointF(-apx, -apy), pm)
    painter.restore()


def draw_fruit(painter, atlas, x, y, rot_deg, bites,
               flesh_color=(0, 0, 255), outline_color=(0, 0, 0),
               scalex=1.0, scaley=1.0) -> None:
    """果子两层叠加（A 底 / B 上），k=clamp(3-bites,0,2)。"""
    k = int(max(0, min(2, 3 - bites)))
    blit(painter, atlas, f"DangleFruit{k}A", x, y, rot_deg, scalex, scaley,
         outline_color, ax=0.5, ay=0.5)
    blit(painter, atlas, f"DangleFruit{k}B", x, y, rot_deg, scalex, scaley,
         flesh_color, ax=0.5, ay=0.5)


def draw_stone(painter, atlas, x, y, rot_deg, frame, color=(70, 72, 78), scale=1.0) -> None:
    blit(painter, atlas, frame, x, y, rot_deg, scale, scale, color, ax=0.5, ay=0.5)


def draw_stone_trail(painter, x, y, ux, uy, length, halfwidth, color, alpha) -> None:
    """抛石运动拖尾：宽端在石头、沿 -(ux,uy) 收成尖的半透明三角。"""
    nx, ny = -uy, ux
    tailx, taily = x - ux * length, y - uy * length
    poly = QPolygonF([QPointF(x + nx * halfwidth, y + ny * halfwidth),
                      QPointF(x - nx * halfwidth, y - ny * halfwidth),
                      QPointF(tailx, taily)])
    col = QColor(color if isinstance(color, QColor) else QColor(*color))
    col.setAlpha(alpha)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(col)
    painter.drawPolygon(poly)
    painter.restore()


def ribbon(painter, points, halfwidths, colors) -> None:
    n = len(points)
    if n < 2:
        return
    path = _outline(points, halfwidths)
    grad = QLinearGradient(QPointF(points[0][0], points[0][1]),
                           QPointF(points[-1][0], points[-1][1]))
    for i, c in enumerate(colors):
        grad.setColorAt(i / (n - 1), QColor(*c))

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(grad)
    painter.drawPath(path)
    painter.restore()
