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
    """设置 Wayland 应用名与 app_id。

    ``.desktop`` 未安装时不设置 app_id，避免 portal 找不到应用；KWin 脚本始终
    以窗口标题作为主识别条件，所以源码运行仍能正常工作。打包安装后会自动
    启用 app_id。
    """
    if sys.platform == "win32":
        return
    try:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.setApplicationName("SlugcatPet")
        # 不设置 applicationDisplayName：Qt 会把它追加到窗口标题，
        # KWin 脚本按精确标题识别 overlay。
        if _desktop_file_installed():
            QGuiApplication.setDesktopFileName(DESKTOP_FILE_NAME)
    except Exception:
        pass
