"""挡雨的窗口：枚举屏上可见的顶层窗口，返回可见边框的矩形（物理 px）。"""

from __future__ import annotations
import ctypes
import os
from ctypes import wintypes

_SKIP_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "NotifyIconOverflowWindow",
    "TopLevelWindowForOverflowXamlIsland",
}
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_TRANSPARENT = 0x00000020
_DWMWA_EXTENDED_FRAME_BOUNDS = 9
_DWMWA_CLOAKED = 14
_MIN_SIDE = 24  # 比这还小的窗口不算

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_api = None


def _load():
    global _api
    if _api is None:
        try:
            user32 = ctypes.windll.user32
            dwm = ctypes.windll.dwmapi
            H = wintypes.HWND
            user32.EnumWindows.argtypes = [_ENUM_PROC, wintypes.LPARAM]
            user32.IsWindowVisible.argtypes = [H]
            user32.IsIconic.argtypes = [H]
            user32.GetWindowLongW.argtypes = [H, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
            user32.GetClassNameW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
            user32.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
            dwm.DwmGetWindowAttribute.argtypes = [H, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            dwm.DwmGetWindowAttribute.restype = ctypes.c_long
            _api = (user32, dwm)
        except (AttributeError, OSError):
            _api = False
    return _api


def window_rects(skip_hwnds=()) -> list[tuple[int, int, int, int]]:
    """可见顶层窗口的边框矩形，跳过桌面、任务栏、点击穿透窗口和本进程的工具窗。"""
    api = _load()
    if not api:
        return []
    user32, dwm = api
    skip = {int(h) for h in skip_hwnds if h}
    me = os.getpid()
    out = []
    cls = ctypes.create_unicode_buffer(64)
    rect = wintypes.RECT()
    cloaked = wintypes.DWORD()
    pid = wintypes.DWORD()

    def visit(hwnd, _lp):
        if hwnd in skip or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        ex = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if ex & _WS_EX_TRANSPARENT:
            return True
        if ex & _WS_EX_TOOLWINDOW:
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == me:
                return True
        if dwm.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), 4) == 0 and cloaked.value:
            return True
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in _SKIP_CLASSES:
            return True
        if dwm.DwmGetWindowAttribute(hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), 16) != 0:
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
        if rect.right - rect.left < _MIN_SIDE or rect.bottom - rect.top < _MIN_SIDE:
            return True
        out.append((rect.left, rect.top, rect.right, rect.bottom))
        return True

    user32.EnumWindows(_ENUM_PROC(lambda h, lp: visit(int(h or 0), lp)), 0)
    return out
