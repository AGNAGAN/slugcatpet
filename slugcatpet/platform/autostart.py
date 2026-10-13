"""开机自启：读写 HKCU Run 注册表项。"""

from __future__ import annotations
import sys
from pathlib import Path

from .._paths import base_dir

_FROZEN = getattr(sys, "frozen", False)
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "SlugcatPet" if _FROZEN else "SlugcatPet (source)"  # 源码运行不覆盖打包版的登记


def _launch_command() -> str:
    if _FROZEN:
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" "{base_dir() / "run_slugcatpet.py"}"'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _VALUE)
        return True
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, _VALUE, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(k, _VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
