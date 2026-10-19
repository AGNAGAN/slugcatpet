"""置顶保持：前台切换时和定时轮询时检查各窗口的 WS_EX_TOPMOST，丢了就补上，不去压别的置顶窗口。"""

from __future__ import annotations
import sys

_IS_WIN = sys.platform == "win32"

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
WS_EX_TOPMOST = 0x00000008
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    WINEVENTPROC = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    try:
        _GetWindowLongPtr = _user32.GetWindowLongPtrW
        _GetWindowLongPtr.restype = ctypes.c_void_p
        _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    except AttributeError:  # 32 位系统没有 Ptr 版本
        _GetWindowLongPtr = _user32.GetWindowLongW

    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    _user32.SetWinEventHook.restype = wintypes.HANDLE
    _user32.SetWinEventHook.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HMODULE,
        WINEVENTPROC,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _user32.UnhookWinEvent.restype = wintypes.BOOL
    _user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]

    def _win_get_exstyle(hwnd: int) -> int:
        v = _GetWindowLongPtr(wintypes.HWND(hwnd), GWL_EXSTYLE)
        return int(v) if v is not None else 0

    try:
        _SetWindowLongPtr = _user32.SetWindowLongPtrW
        _SetWindowLongPtr.restype = ctypes.c_void_p
        _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    except AttributeError:
        _SetWindowLongPtr = _user32.SetWindowLongW

    def _win_set_owner(hwnd: int, owner: int) -> None:
        _SetWindowLongPtr(wintypes.HWND(hwnd), GWLP_HWNDPARENT, owner)

    def _win_set_topmost(hwnd: int) -> None:
        # 置顶但不抢前台
        _user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(HWND_TOPMOST),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def _win_install_hook(callback):
        # 返回 proc 供调用方持有，防止被回收
        proc = WINEVENTPROC(callback)
        hook = _user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            None,
            proc,
            0,
            0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        return proc, (int(hook) if hook else 0)

    def _win_remove_hook(hook) -> None:
        _user32.UnhookWinEvent(wintypes.HANDLE(hook))


class TopmostKeeper:
    """windows 按先下后上排列。"""

    def __init__(
        self,
        windows,
        is_suspended=None,
        *,
        get_exstyle=None,
        set_topmost=None,
        install_hook=None,
        remove_hook=None,
    ):
        self._windows = list(windows)
        self._is_suspended = is_suspended or (lambda: False)
        if get_exstyle is None or set_topmost is None:
            if _IS_WIN:
                get_exstyle = get_exstyle or _win_get_exstyle
                set_topmost = set_topmost or _win_set_topmost
            else:  # 非 Windows 时 reassert 什么都不做
                get_exstyle = get_exstyle or (lambda h: WS_EX_TOPMOST)
                set_topmost = set_topmost or (lambda h: None)
        self._get_exstyle = get_exstyle
        self._set_topmost = set_topmost
        self._install_hook = install_hook or (_win_install_hook if _IS_WIN else None)
        self._remove_hook = remove_hook or (_win_remove_hook if _IS_WIN else None)
        self._proc = None
        self._hook = None

    def reassert(self):
        """有窗口丢了置顶就重新按次序整理一遍。"""
        if self._is_suspended():
            return
        for w in self._windows:
            try:
                if not w.isVisible():
                    continue
                hwnd = int(w.winId())
                if hwnd and not (self._get_exstyle(hwnd) & WS_EX_TOPMOST):
                    self.force_top()
                    return
            except Exception:
                pass

    def force_top(self):
        """不看标志位，把所有可见窗口按列表次序（先下后上）提到置顶组最上面。"""
        if self._is_suspended():
            return
        for w in self._windows:
            try:
                if not w.isVisible():
                    continue
                w.raise_()
                hwnd = int(w.winId())
                if hwnd:
                    self._set_topmost(hwnd)
            except Exception:
                pass

    def start(self):
        if self._hook is not None or self._install_hook is None:
            return
        try:
            self._proc, self._hook = self._install_hook(self._on_foreground)
        except Exception:
            self._proc = self._hook = None

    def stop(self):
        if self._hook and self._remove_hook is not None:
            try:
                self._remove_hook(self._hook)
            except Exception:
                pass
        self._proc = None
        self._hook = None

    def _on_foreground(self, *args):
        # ctypes 回调里不能抛异常
        try:
            self.reassert()
        except Exception:
            pass


def raise_topmost(w) -> None:
    """把一个窗口提到置顶组最上面，不抢前台；全屏程序上面也盖得住。"""
    try:
        w.raise_()
        if _IS_WIN:
            hwnd = int(w.winId())
            if hwnd:
                _win_set_topmost(hwnd)
    except Exception:
        pass


def own_by(owner, w) -> None:
    """让 w 成为 owner 的从属窗口：叠放永远在 owner 之上，生命周期各管各的。"""
    if not _IS_WIN:
        return
    try:
        owner.winId()
        w.winId()
        w.windowHandle().setTransientParent(owner.windowHandle())
        if w.isVisible():  # 已显示的窗口 Qt 要等下次显示才生效，直接改原生属主
            _win_set_owner(int(w.winId()), int(owner.winId()))
    except Exception:
        pass
