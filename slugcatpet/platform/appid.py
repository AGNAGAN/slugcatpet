"""进程的 AppUserModelID：任务栏和音量合成器按它把本程序识别为独立应用。"""
from __future__ import annotations

import sys

APP_USER_MODEL_ID = "SlugcatPet"


def set_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass
