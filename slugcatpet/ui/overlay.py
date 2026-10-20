"""overlay 子控件的坐标与旧存档迁移工具。

嵌入 overlay 后，面板的 ``pos()``/``geometry()`` 都是 overlay 本地逻辑坐标。
这里集中处理三件事，避免每个面板各写一套：

- 把控件事件坐标换算成 overlay 本地坐标；
- 把面板左上角夹进 overlay 可见范围；
- 首次迁移旧版保存的全局坐标。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QWidget


def local_point(host: QWidget, widget: QWidget, ev) -> QPoint:
    """控件事件坐标 → overlay 本地坐标。"""
    try:
        return widget.mapTo(host, ev.position().toPoint())
    except (AttributeError, RuntimeError):
        return host.mapFromGlobal(ev.globalPosition().toPoint())


def clamp_local(host: QWidget, pos: QPoint, width: int, height: int) -> QPoint:
    """把 width×height 的本地矩形左上角夹进 overlay。"""
    max_x = max(0, host.width() - width)
    max_y = max(0, host.height() - height)
    return QPoint(max(0, min(pos.x(), max_x)), max(0, min(pos.y(), max_y)))


def clamp_local_rect(host: QWidget, rect: QRect) -> QRect:
    p = clamp_local(host, rect.topLeft(), rect.width(), rect.height())
    return QRect(p, rect.size())


def _legacy_point(value, overlay: QRect) -> QPoint | None:
    """把旧存档里的点转换成 overlay 本地坐标。

    早期版本保存的是屏幕全局坐标。若点落在 overlay 的全局矩形内，减去原点；
    若它已经落在本地矩形内（Phase 1 曾直接保存过本地坐标），保持不动。
    两组坐标都命中时以全局坐标为准，因为迁移标记缺失的存档来自旧全局格式。
    """
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        return None
    if overlay.contains(x, y):
        return QPoint(x - overlay.x(), y - overlay.y())
    local = QRect(0, 0, overlay.width(), overlay.height())
    if local.contains(x, y):
        return QPoint(x, y)
    return None


def _legacy_y(value, overlay: QRect) -> int | None:
    try:
        y = int(value)
    except (TypeError, ValueError):
        return None
    if overlay.y() <= y <= overlay.y() + overlay.height():
        return y - overlay.y()
    if 0 <= y <= overlay.height():
        return y
    return None


def migrate_ui_coords(params: dict, overlay: QRect) -> bool:
    """把旧版全局坐标改成 overlay 本地坐标；返回是否发生了迁移。

    只在 Wayland 首次启动时调用。迁移完成后写 ``ui_coord_space``，避免把已经
    是本地坐标的值再次减去 overlay 原点。
    """
    if params.get("ui_coord_space") == "overlay":
        return False
    if overlay.width() <= 0 or overlay.height() <= 0:
        return False

    hud = _legacy_point((params.get("hud_x"), params.get("hud_y")), overlay)
    if hud is not None:
        params["hud_x"], params["hud_y"] = hud.x(), hud.y()

    tab_y = _legacy_y(params.get("tab_y"), overlay)
    if tab_y is not None:
        params["tab_y"] = tab_y

    rain = params.get("rain_timer")
    if isinstance(rain, dict):
        dial = _legacy_point(rain.get("dial_pos"), overlay)
        if dial is not None:
            rain["dial_pos"] = [dial.x(), dial.y()]

    params["ui_coord_space"] = "overlay"
    return True
