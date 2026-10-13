"""按位置找所在屏幕的可用区域，多屏下限位用。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication


def available_at(pos: QPoint) -> QRect:
    """pos 所在屏幕的可用区域；不在任何屏幕上时取主屏。"""
    scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
    return scr.availableGeometry()


def clamp_rect(pos: QPoint, w: int, h: int) -> QPoint:
    """把 w×h 的窗口左上角夹进其中心所在屏幕。"""
    r = available_at(QPoint(pos.x() + w // 2, pos.y() + h // 2))
    x = max(r.x(), min(pos.x(), r.x() + r.width() - w))
    y = max(r.y(), min(pos.y(), r.y() + r.height() - h))
    return QPoint(x, y)
