"""托盘图标：猫色圆点，计时中外圈一道进度弧；晴天白弧顺时针缩短，雨天变暗加雨丝、蓝弧顺时针补满，一直下的雨不画弧。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from ...world.raintimer import DRY, IDLE, RAIN

ICON = 32
ARC_STEPS = 64  # 弧长量化，变了才重画
DRY_ARC = QColor(255, 255, 255)
RAIN_ARC = QColor(120, 175, 255)
RAIN_BODY = QColor(70, 84, 104)
RAIN_STREAK = QColor(190, 215, 245)


def arc_key(timer):
    """决定图标长相的量化状态，相同就不用重画。"""
    if timer is None or timer.phase == IDLE:
        return IDLE, 0
    if timer.phase == RAIN and timer.end_ts is None:
        return RAIN, 0
    p = timer.progress()
    return timer.phase, round((1.0 - p if timer.phase == DRY else p) * ARC_STEPS)


def tray_icon(body_rgb, frozen=False, timer=None) -> QIcon:
    """定格时右下角加暂停角标。"""
    phase, steps = arc_key(timer)
    pm = QPixmap(ICON, ICON)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    running = phase != IDLE
    body = QRectF(7, 7, 18, 18) if running else QRectF(4, 4, 24, 24)
    p.setBrush(RAIN_BODY if phase == RAIN else QColor(*body_rgb))
    p.setPen(QColor(40, 80, 20) if phase != RAIN else QColor(30, 38, 50))
    p.drawEllipse(body)
    if phase == RAIN:
        p.setPen(QPen(RAIN_STREAK, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for x in (11.5, 16.0, 20.5):
            p.drawLine(QPointF(x, 10.5), QPointF(x - 3.0, 21.5))
    if running and steps > 0:
        span = int(360 * 16 * steps / ARC_STEPS)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(
            QPen(DRY_ARC if phase == DRY else RAIN_ARC, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        )
        p.drawArc(QRectF(2.5, 2.5, ICON - 5, ICON - 5), 90 * 16, span if phase == DRY else -span)
    if frozen:
        p.setPen(QColor(255, 255, 255))
        p.setBrush(QColor(60, 110, 200))
        p.drawEllipse(15, 15, 16, 16)
        p.setPen(QColor(0, 0, 0, 0))
        p.setBrush(QColor(255, 255, 255))
        p.drawRect(19, 19, 3, 8)
        p.drawRect(24, 19, 3, 8)
    p.end()
    return QIcon(pm)
