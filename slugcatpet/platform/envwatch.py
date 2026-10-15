"""环境监视：别的程序全屏时收起或沉底，跟随工作区和任务栏变化，保持置顶；一个定时器轮询，间隔不超过 2s。"""

from __future__ import annotations
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication

from .topmost import TopmostKeeper

_TRUSTED_FULLSCREEN_STATES = {3, 4}  # SHQueryUserNotificationState 的 D3D 独占全屏、演示模式
_DESKTOP_CLASSES = {"Progman", "WorkerW"}
# 任务栏、开始菜单、搜索、多任务视图等浮层：拿到前台时保持原状态
_HOLD_CLASSES = {
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Button",
    "Windows.UI.Core.CoreWindow",
    "XamlExplorerHostIslandWindow",
    "MultitaskingViewFrame",
    "ForegroundStaging",
    "NotifyIconOverflowWindow",
    "TopLevelWindowForOverflowXamlIsland",
}
POLL_MS = 1000
_RECT_TOL = 2  # 矩形匹配容差（物理 px）
DEBOUNCE_POLLS = 2  # 连续这么多次判断一致才切换


def _default_state_provider() -> int:
    """用户通知状态；取不到时返回 5（ACCEPTS_NOTIFICATIONS）。"""
    try:
        state = ctypes.c_int(0)
        hr = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
        if hr == 0:
            return state.value
    except Exception:
        pass
    return 5


def _default_foreground_provider():
    """前台窗口的 (hwnd, rect, 类名)，取不到时返回 None。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return None
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
        return int(hwnd), (rect.left, rect.top, rect.right, rect.bottom), buf.value
    except Exception:
        return None


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _default_monitor_provider(hwnd: int):
    try:
        user32 = ctypes.windll.user32
        mon = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
        mi = _MonitorInfo()
        mi.cbSize = ctypes.sizeof(mi)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        r = mi.rcMonitor
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return None


class EnvironmentWatcher(QObject):
    def __init__(
        self,
        windows,
        pet,
        state_provider=None,
        foreground_provider=None,
        interval_ms: int = POLL_MS,
        parent=None,
        topmost=None,
        monitor_provider=None,
    ):
        super().__init__(parent)
        self._windows = list(windows)
        self._pet = pet
        self._state_provider = state_provider or _default_state_provider
        self._foreground_provider = foreground_provider or _default_foreground_provider
        self._monitor_provider = monitor_provider or _default_monitor_provider
        self._fullscreen = False
        self._mode = "normal"  # normal / hide / sink
        self._streak = 0
        self._topmost = topmost or TopmostKeeper(self._windows, is_suspended=lambda: self._fullscreen)
        self._vis_snapshot: list[bool] | None = None
        self._area = None
        self._geo = None
        self._primary_conn = None
        self._screen_conn = None
        self._timer = QTimer(self)
        self._timer.setInterval(min(interval_ms, 2000))
        self._timer.timeout.connect(self._on_poll)

    def start(self):
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self._area = screen.availableGeometry()
            self._geo = screen.geometry()
        self._connect_screen(screen)
        app = QGuiApplication.instance()
        if app is not None:
            self._primary_conn = app.primaryScreenChanged.connect(self._on_primary_changed)
        self._timer.start()
        self._topmost.start()

    def stop(self):
        self._timer.stop()
        self._topmost.stop()
        if self._primary_conn is not None:
            QObject.disconnect(self._primary_conn)
            self._primary_conn = None
        self._connect_screen(None)

    def force_top(self):
        self._topmost.force_top()

    def _on_poll(self):
        self._check_fullscreen()
        self._check_workspace()
        if self._mode == "sink":  # 全屏程序常自带置顶，要主动压到它上面
            self._topmost.force_top()
        else:
            self._topmost.reassert()

    def _check_fullscreen(self):
        try:
            exclusive = self._state_provider() in _TRUSTED_FULLSCREEN_STATES
        except Exception:
            exclusive = False
        if exclusive:  # 独占全屏时置顶窗画不出来，只能收起
            self._streak = 0
            self._set_mode("hide")
            return
        full = self._foreground_fullscreen()
        if full is None:
            self._streak = 0
            return
        want = getattr(self._pet, "cfg_fullscreen_mode", "hide") if full else "normal"
        if want == self._mode:
            self._streak = 0
            return
        self._streak += 1
        if self._streak >= DEBOUNCE_POLLS:
            self._streak = 0
            self._set_mode(want)

    def _foreground_fullscreen(self):
        """前台窗口盖满桌宠所在显示器时为 True，桌面为 False，自己的窗口或系统浮层为 None（保持原状）。

        两边都按物理像素比较，缩放不是 100% 时也对得上。"""
        fg = self._foreground_provider()
        if fg is None:
            return None
        hwnd, (left, top, right, bottom), cls = fg
        if hwnd in self._own_hwnds() or cls in _HOLD_CLASSES:
            return None
        if cls in _DESKTOP_CLASSES:
            return False
        try:
            mon = self._monitor_provider(int(self._pet.winId()))
        except Exception:
            mon = None
        if mon is None:
            return None
        ml, mt, mr, mb = mon
        t = _RECT_TOL
        return left <= ml + t and top <= mt + t and right >= mr - t and bottom >= mb - t

    def _set_mode(self, mode):
        if mode == self._mode:
            return
        if self._mode == "hide":
            self._exit_fullscreen()
        elif self._mode == "sink":
            self._pet.set_floor_sink(False)
        self._mode = mode
        if mode == "hide":
            self._enter_fullscreen()
        elif mode == "sink":
            self._pet.set_floor_sink(True)
            self._topmost.force_top()

    def _own_hwnds(self) -> set[int]:
        hwnds = set()
        for w in self._windows:
            try:
                hwnds.add(int(w.winId()))
            except Exception:
                pass
        return hwnds

    def _enter_fullscreen(self):
        self._fullscreen = True
        self._vis_snapshot = [self._is_visible(w) for w in self._windows]
        for w in self._windows:
            try:
                w.hide()
            except Exception:
                pass
        try:
            self._pet.freeze("env")
        except Exception:
            pass

    def _exit_fullscreen(self):
        self._fullscreen = False
        try:
            self._pet.unfreeze("env")
        except Exception:
            pass
        snap = self._vis_snapshot if self._vis_snapshot is not None else [True] * len(self._windows)
        for w, vis in zip(self._windows, snap):
            if not vis:
                continue
            try:
                w.show()
            except Exception:
                pass
        self._vis_snapshot = None

    def reveal(self, windows):
        """重新显示这些窗口；全屏收起中由它管的窗口记到快照里，等退出全屏时再显示。"""
        later = self._fullscreen and self._vis_snapshot is not None
        for w in windows:
            if later and w in self._windows:
                self._vis_snapshot[self._windows.index(w)] = True
                continue
            try:
                w.show()
            except Exception:
                pass

    @staticmethod
    def _is_visible(w) -> bool:
        try:
            return bool(w.isVisible())
        except Exception:
            return True

    def _check_workspace(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        geo = screen.geometry()
        if self._area is not None and area == self._area and geo == self._geo:
            return
        self._area = area
        self._geo = geo
        try:
            self._pet.apply_workspace(area, geo)
        except Exception:
            pass

    def _connect_screen(self, screen):
        """只盯一块屏的工作区变化；screen 为 None 时断开。"""
        if self._screen_conn is not None:
            QObject.disconnect(self._screen_conn)
            self._screen_conn = None
        if screen is not None:
            self._screen_conn = screen.availableGeometryChanged.connect(self._on_screen_signal)

    def _on_screen_signal(self, *args):
        self._check_workspace()

    def _on_primary_changed(self, screen):
        self._connect_screen(screen)
        self._check_workspace()
