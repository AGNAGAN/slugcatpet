"""把桌宠和浮层控件的命中范围拼成 Wayland 输入区域。

坐标约定：
- 宠物、物品使用渲染逻辑坐标，乘 ``canvas_scale`` 后才是 overlay 本地坐标；
- 嵌入的面板已经是 overlay 本地坐标，不能再乘 scale；
- QWindow.setMask() 使用逻辑本地坐标，不乘 DPR（Phase 0 实测）。
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from PySide6.QtCore import QRect
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QWidget

from ...control.mouse import grab_circles

PET_PAD = 7.0
ITEM_PAD = 7.0
DEFAULT_ITEM_RAD = 8.0


def _circle_rect(cx: float, cy: float, rad: float, scale: float) -> QRect:
    """逻辑圆 → overlay 本地矩形；向外交整，避免亚像素漏点。"""
    s = scale or 1.0
    x0 = math.floor((cx - rad) * s)
    y0 = math.floor((cy - rad) * s)
    x1 = math.ceil((cx + rad) * s)
    y1 = math.ceil((cy + rad) * s)
    return QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def pet_rects(pet, scale: float) -> list[QRect]:
    """桌宠的可交互范围：头、身体、髋三个抓点的外扩圆。"""
    body = getattr(pet, "body", None)
    gfx = getattr(pet, "gfx", None)
    if body is None or gfx is None:
        return []
    try:
        circles = grab_circles(body, gfx, pad=PET_PAD)
    except Exception:
        return []
    out = []
    for _name, _chunk, x, y, rad in circles:
        out.append(_circle_rect(float(x), float(y), float(rad), scale))
    # 与 control.mouse.is_over() 的外接框保持一致，避免身体中间的空隙穿透。
    try:
        xs = [float(body.chunk0.x), float(body.chunk1.x), float(gfx.head.x)]
        ys = [float(body.chunk0.y), float(body.chunk1.y), float(gfx.head.y)]
        s = scale or 1.0
        x0 = math.floor((min(xs) - 11.0 - PET_PAD) * s)
        y0 = math.floor((min(ys) - 11.0 - PET_PAD) * s)
        x1 = math.ceil((max(xs) + 11.0 + PET_PAD) * s)
        y1 = math.ceil((max(ys) + 14.0 + PET_PAD) * s)
        out.append(QRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0)))
    except (AttributeError, TypeError, ValueError):
        pass
    return out


def item_rects(obj, scale: float) -> list[QRect]:
    """物品的粗略命中范围；杆、灯等没有圆形 rad 的按端点补。"""
    rects: list[QRect] = []

    def add(x, y, rad):
        try:
            x, y, rad = float(x), float(y), float(rad)
        except (TypeError, ValueError):
            return
        if math.isfinite(x) and math.isfinite(y) and math.isfinite(rad):
            rects.append(_circle_rect(x, y, max(2.0, rad), scale))

    if hasattr(obj, "ax") and hasattr(obj, "ay"):
        add(obj.ax, obj.ay, 8.0 + ITEM_PAD)
    if hasattr(obj, "bx") and hasattr(obj, "by"):
        add(obj.bx, obj.by, 8.0 + ITEM_PAD)
    if hasattr(obj, "anchor_x") and hasattr(obj, "anchor_y"):
        add(obj.anchor_x, obj.anchor_y, 16.0 + ITEM_PAD)
    if hasattr(obj, "bulb_x") and hasattr(obj, "bulb_y"):
        add(obj.bulb_x, obj.bulb_y, 16.0 + ITEM_PAD)
    if hasattr(obj, "x") and hasattr(obj, "y"):
        rad = float(getattr(obj, "rad", DEFAULT_ITEM_RAD) or DEFAULT_ITEM_RAD)
        add(obj.x, obj.y, rad + ITEM_PAD)
    return rects


def panel_rects(panels: Iterable[QWidget]) -> list[QRect]:
    """嵌入控件的本地矩形；隐藏或尺寸无效的控件不占输入。"""
    out = []
    for panel in panels:
        if panel is None or not panel.isVisible():
            continue
        r = panel.geometry()
        if r.width() > 0 and r.height() > 0:
            out.append(QRect(r))
    return out


def interaction_region(
    pets: Iterable,
    items: Iterable,
    panels: Iterable[QWidget],
    scale: float,
    width: int,
    height: int,
    *,
    full: bool = False,
) -> QRegion:
    """生成输入区域；没有命中时返回表面外 1×1，实现完全穿透。"""
    w, h = max(1, int(width)), max(1, int(height))
    if full:
        return QRegion(0, 0, w, h)
    region = QRegion()
    for pet in pets:
        for r in pet_rects(pet, scale):
            region = region.united(QRegion(r))
    for obj in items:
        for r in item_rects(obj, scale):
            region = region.united(QRegion(r))
    for r in panel_rects(panels):
        region = region.united(QRegion(r))
    region = region.intersected(QRegion(0, 0, w, h))
    if region.isEmpty():
        return QRegion(w, h, 1, 1)
    return region
