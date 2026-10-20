"""Wayland 输入区域：设置后必须提交表面，区域才会真正生效。

Qt 在 ``QWindow.setMask()`` 时只发送 ``wl_surface.set_input_region``，不会自动
``wl_surface.commit``。必须再调用 ``requestUpdate()``，否则合成器仍按旧区域
（通常是整窗）投递输入。详见 ``ai-docs/PHASE0_RESULTS.md`` 3.3。
"""

from __future__ import annotations

from PySide6.QtGui import QRegion, QWindow
from PySide6.QtWidgets import QWidget


def outside_region(window: QWindow | QWidget) -> QRegion:
    """表面外 1×1，用于完全穿透。

    不能用空 QRegion：Qt Wayland 会把它编码成 ``set_input_region(nil)``，
    等价于整窗接收输入。
    """
    handle = _window_handle(window)
    if handle is None:
        return QRegion(0, 0, 1, 1)
    return QRegion(max(1, handle.width()), max(1, handle.height()), 1, 1)


def set_input_region(window: QWindow | QWidget, region: QRegion) -> bool:
    """设置输入区域并提交表面；成功返回 True。

    ``region`` 为空时自动改为表面外 1×1，保证完全穿透。
    """
    handle = _window_handle(window)
    if handle is None:
        return False
    if region.isEmpty():
        region = outside_region(handle)
    handle.setMask(region)
    handle.requestUpdate()  # 关键：触发 wl_surface.commit
    return True


def _window_handle(window: QWindow | QWidget) -> QWindow | None:
    if isinstance(window, QWindow):
        return window
    handle = window.windowHandle()
    return handle if isinstance(handle, QWindow) else None
