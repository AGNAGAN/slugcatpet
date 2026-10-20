"""进程的 AppUserModelID：任务栏和音量合成器按它把本程序识别为独立应用。"""

from __future__ import annotations

import sys
from pathlib import Path

APP_USER_MODEL_ID = "SlugcatPet"
DESKTOP_FILE_NAME = "org.slugcatpet.SlugcatPet"


def set_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def _desktop_file_installed() -> bool:
    try:
        from PySide6.QtCore import QStandardPaths

        name = f"{DESKTOP_FILE_NAME}.desktop"
        for folder in QStandardPaths.standardLocations(QStandardPaths.StandardLocation.ApplicationsLocation):
            if Path(folder, name).is_file():
                return True
    except Exception:
        pass
    return False


def set_desktop_file_name() -> None:
    """Wayland app_id；只有 .desktop 已安装时才设置，避免 portal 报 app 不存在。

    KWin 脚本始终以窗口标题作为主识别条件，所以源码运行（没有 desktop 文件）
    也能正常工作。
    """
    if sys.platform == "win32" or not _desktop_file_installed():
        return
    try:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.setDesktopFileName(DESKTOP_FILE_NAME)
    except Exception:
        pass
