"""光标劫持：让光标下落或被弹开后锁住一段时间，可把系统光标换成「忙」样式。"""

from __future__ import annotations
import sys
import math
import atexit

_IS_WIN = sys.platform == "win32"

# 计时单位为 tick（40Hz）；坐标为 Win32 物理像素
T_FALL_GRAV = 1.6
T_CURSOR_LOCK = 200
WATCHDOG_MAX = 400
K_KNOCK = 0.88  # 被弹开时每 tick 的速度衰减
K_KNOCK_GRAV = 0.5
K_KNOCK_LAND = 6  # 速度低于此值就停下锁住

_ACTIVE = []

if _IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    def _clip(x, y):
        r = _RECT(int(x), int(y), int(x) + 1, int(y) + 1)
        return bool(_user32.ClipCursor(ctypes.byref(r)))

    def _unclip():
        _user32.ClipCursor(None)

    def _setpos(x, y):
        _user32.SetCursorPos(int(x), int(y))

    _OCR_IDS = (32512, 32513, 32649)  # OCR_NORMAL/IBEAM/HAND
    _IDC_APPSTARTING = 32650
    _SPI_SETCURSORS = 0x0057

    _user32.LoadCursorW.restype = ctypes.c_void_p
    _user32.LoadCursorW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    _user32.CopyIcon.restype = ctypes.c_void_p
    _user32.CopyIcon.argtypes = (ctypes.c_void_p,)
    _user32.SetSystemCursor.restype = wintypes.BOOL
    _user32.SetSystemCursor.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    _user32.SystemParametersInfoW.restype = wintypes.BOOL
    _user32.SystemParametersInfoW.argtypes = (wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT)

    def _set_busy_cursor():
        """把系统的箭头、文本、链接光标换成「忙」样式；SetSystemCursor 会取走句柄，所以每次先 CopyIcon。"""
        src = _user32.LoadCursorW(None, _IDC_APPSTARTING)
        if not src:
            return False
        ok = False
        for ocr in _OCR_IDS:
            h = _user32.CopyIcon(src)
            if h and _user32.SetSystemCursor(h, ocr):
                ok = True
        return ok

    def _restore_cursors():
        _user32.SystemParametersInfoW(_SPI_SETCURSORS, 0, None, 0)
else:

    def _clip(x, y):
        return False

    def _unclip():
        pass

    def _setpos(x, y):
        pass

    def _set_busy_cursor():
        return False

    def _restore_cursors():
        pass


def restore_cursors():
    try:
        _restore_cursors()
    except Exception:
        pass


class CursorHijack:
    """一次光标劫持；坐标由 window 按 dpr 换算成各平台的原生单位。

    默认走 Win32 的 ``ClipCursor`` / ``SetCursorPos``。Wayland 下由调用方传入
    ``setpos`` 等回调，使用 Qt 的 pointer-warp 实现；此时 ``clip`` 返回 False，
    状态机自动退化为逐 tick 重新定位。
    """

    def __init__(
        self,
        dev_x,
        dev_y,
        screen_w,
        screen_h,
        screen_x=0,
        screen_y=0,
        mock=False,
        lock_ticks=T_CURSOR_LOCK,
        mode="fall",
        watchdog_max=WATCHDOG_MAX,
        replace_cursor=True,
        knock_v=(0.0, 0.0),
        *,
        clip=None,
        unclip=None,
        setpos=None,
        busy_cursor=None,
        restore_cursor=None,
        on_release=None,
    ):
        custom_write = setpos is not None
        self._clip = clip or _clip
        self._unclip = unclip or _unclip
        self._setpos = setpos or _setpos
        self._busy_cursor = busy_cursor or _set_busy_cursor
        self._restore_cursor = restore_cursor or _restore_cursors
        self._on_release = on_release
        self.mock = bool(mock) or (not _IS_WIN and not custom_write)
        self.x = float(dev_x)
        self.y = float(dev_y)
        self.vx = float(knock_v[0])
        self.vy = float(knock_v[1])
        self.W = screen_w
        self.H = screen_h
        self.x0 = screen_x
        self.y0 = screen_y
        self.bottom = screen_y + screen_h - 2
        self.mode = mode
        if mode == "hold":
            self.phase = "hold"  # hold → done
        elif self.vx or self.vy:
            self.phase = "knock"  # knock → lock → done
        else:
            self.phase = "fall"  # fall → lock → done
        self.lock_ticks = int(lock_ticks)
        self.lock_t = 0
        self.watchdog = 0
        self.watchdog_max = int(watchdog_max)
        self.use_setpos = False  # ClipCursor 失败后改用 SetCursorPos
        self.replace_cursor = bool(replace_cursor)
        self.active = True
        _ACTIVE.append(self)
        if not self.mock and self.replace_cursor:
            try:
                self._busy_cursor()
            except Exception:
                pass

    def hold_at(self, dev_x, dev_y):
        self.x = float(dev_x)
        self.y = float(dev_y)

    def update(self) -> bool:
        if not self.active:
            return False
        self.watchdog += 1
        if self.watchdog >= self.watchdog_max:
            self.release()
            return False

        if self.phase == "knock":
            self.vx *= K_KNOCK
            self.vy = self.vy * K_KNOCK + K_KNOCK_GRAV
            self.x += self.vx
            self.y += self.vy
            self.use_setpos = True  # ClipCursor 体现不出位移，直接移光标
            if math.hypot(self.vx, self.vy) < K_KNOCK_LAND:
                self.phase = "lock"
                self.lock_t = 0
        elif self.phase == "fall":
            self.vy += T_FALL_GRAV
            self.y += self.vy
            if self.y >= self.bottom:
                self.y = self.bottom
                self.vy = 0.0
                self.phase = "lock"
                self.lock_t = 0
        elif self.phase == "lock":
            self.lock_t += 1
            if self.lock_t >= self.lock_ticks:
                self.release()
                return False

        self._apply()
        return True

    def _apply(self):
        if self.mock:
            return
        x = min(max(self.x, self.x0), self.x0 + self.W - 1)
        y = min(max(self.y, self.y0), self.y0 + self.H - 1)
        if not self.use_setpos:
            ok = False
            try:
                ok = self._clip(x, y)
            except Exception:
                ok = False
            if not ok:
                try:
                    self._unclip()
                except Exception:
                    pass
                self.use_setpos = True
        if self.use_setpos:
            try:
                self._setpos(x, y)
            except Exception:
                pass

    def release(self):
        if not self.active:
            return
        self.active = False
        self.phase = "done"
        if not self.mock:
            try:
                self._unclip()
            except Exception:
                pass
            if self.replace_cursor:
                try:
                    self._restore_cursor()
                except Exception:
                    pass
        if self._on_release is not None:
            try:
                self._on_release()
            except Exception:
                pass
        try:
            _ACTIVE.remove(self)
        except ValueError:
            pass


def abort_all():
    for h in list(_ACTIVE):
        h.release()
    if _IS_WIN:
        try:
            _unclip()
        except Exception:
            pass
        try:
            _restore_cursors()
        except Exception:
            pass


atexit.register(abort_all)
