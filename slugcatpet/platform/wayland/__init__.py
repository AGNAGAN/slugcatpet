"""Wayland 会话识别与原生窗口辅助。

输入区域在本包内实现；几何、置顶和全局光标由 ``kwin_bridge`` 的 KWin 脚本 +
DBus 桥提供。非 KWin 合成器上这些能力会降级。
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication


def is_wayland() -> bool:
    """当前 Qt 是否运行在 Wayland 会话（而不是 X11 / offscreen）。"""
    app = QGuiApplication.instance()
    return app is not None and app.platformName() == "wayland"
