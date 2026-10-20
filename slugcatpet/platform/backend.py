"""桌面后端接口：把窗口几何、置顶、光标和输入区域从 UI 中隔离出来。

Windows 继续走现有的 Win32 路径；原生 Wayland 由 ``wayland.kwin_bridge`` 提供
KWin 脚本 + DBus 桥。没有可用后端时退回 ``NullBackend``，应用仍能启动，只是
光标跟随、置顶等能力降级。
"""

from __future__ import annotations

import sys
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QWidget

OVERLAY_TITLE = "SlugcatPet Overlay"
CURSOR_CAPTURE_TITLE = "SlugcatPet Cursor Capture"


class DesktopBackend:
    """桌面能力的最小接口。

    坐标约定：``cursor_global()`` 和 ``overlay_origin()`` 都是合成器逻辑坐标；
    ``cursor_overlay_pos()`` 返回光标相对 overlay 左上角的逻辑坐标。调用方再把
    overlay 坐标除以 ``canvas_scale`` 得到宠物世界坐标。
    """

    name = "null"
    supports_geometry = False
    supports_topmost = False
    supports_cursor = False
    supports_cursor_write = False
    supports_fullscreen = False
    supports_shelters = False
    supports_hotkeys = False

    def attach_overlay(self, window: QWidget) -> bool:
        """把主表面交给后端；返回后端是否已经接管。"""
        return False

    def configure_overlay(self, screen_name: str, rect: QRect) -> None:
        """更新目标输出和 overlay 全局矩形（逻辑坐标）。"""

    def set_input_region(self, window: QWidget, region: QRegion) -> bool:
        return False

    def cursor_global(self) -> tuple[int, int] | None:
        return None

    def cursor_pos(self) -> tuple[int, int] | None:
        """计划接口名：全局逻辑坐标；没有全局光标时返回 None。"""
        return self.cursor_global()

    def cursor_overlay_pos(self) -> tuple[int, int] | None:
        pos = self.cursor_global()
        if pos is None:
            return None
        ox, oy = self.overlay_origin()
        return pos[0] - ox, pos[1] - oy

    def overlay_origin(self) -> tuple[int, int]:
        return 0, 0

    def set_overlay_geometry(self, rect: QRect) -> None:
        """计划接口名：只改 overlay 矩形，目标输出保持当前绑定。"""

    def foreground_fullscreen(self) -> bool | None:
        """前台窗口是否覆盖 overlay 所在输出；None=未知/自己的窗口。"""
        return None

    def window_rects(self) -> list[QRect]:
        """挡雨窗口的 overlay-local 矩形；第一版 Wayland 未实现，返回空。"""
        return []

    def set_autostart(self, on: bool) -> bool:
        return False

    def register_hotkey(self, hotkey_id: int, mods: int, vk: int) -> bool:
        """注册一个全局热键；后端只能注册固定集合时返回 False。"""
        return False

    def hotkey_available(self, mods: int, vk: int) -> bool:
        """检查组合键是否可用；未知时返回 False。"""
        return False

    def install_hotkeys(self, callbacks) -> bool:
        """兼容旧接口；新代码用 register_hotkey。"""
        return False

    def reload(self) -> bool:
        """重新加载平台集成（KWin 脚本等）；不支持时返回 False。"""
        return False

    def shutdown(self) -> None:
        """退出时卸载脚本、注销 DBus 服务；必须可重复调用。"""


class NullBackend(DesktopBackend):
    """非 KDE 会话、或 KWin 不可用时的降级后端。"""

    name = "null"


class Win32Backend(DesktopBackend):
    """Windows 行为包装：几何、光标和输入穿透仍由现有 Win32 代码完成。"""

    name = "win32"
    supports_geometry = True
    supports_topmost = True
    supports_cursor = True
    supports_cursor_write = True
    supports_hotkeys = True

    def __init__(self):
        self._window: QWidget | None = None

    def attach_overlay(self, window: QWidget) -> bool:
        self._window = window
        return True

    def configure_overlay(self, screen_name: str, rect: QRect) -> None:
        self.set_overlay_geometry(rect)

    def set_overlay_geometry(self, rect: QRect) -> None:
        if self._window is not None:
            self._window.move(rect.topLeft())
            if self._window.size() != rect.size():
                self._window.resize(rect.size())

    def set_input_region(self, window: QWidget, region: QRegion) -> bool:
        try:
            from ..control.mouse import set_passthrough

            set_passthrough(int(window.winId()), region.isEmpty())
            return True
        except Exception:
            return False

    def cursor_global(self) -> tuple[int, int] | None:
        from PySide6.QtGui import QCursor

        pos = QCursor.pos()
        return pos.x(), pos.y()

    def overlay_origin(self) -> tuple[int, int]:
        if self._window is None:
            return 0, 0
        p = self._window.mapToGlobal(QPoint(0, 0))
        return p.x(), p.y()


def create_backend() -> DesktopBackend:
    """按当前会话选择后端；导入放在函数内，避免无 Wayland 依赖时被提前加载。"""
    if sys.platform == "win32":
        return Win32Backend()

    from .wayland import is_wayland

    if is_wayland():
        from .wayland.kwin_bridge import WaylandKWinBackend

        return WaylandKWinBackend()
    return NullBackend()
