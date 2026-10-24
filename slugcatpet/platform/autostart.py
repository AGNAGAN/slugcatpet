"""开机自启：读写 HKCU Run 注册表项。"""

from __future__ import annotations
import sys
from pathlib import Path

from .._paths import base_dir

_FROZEN = getattr(sys, "frozen", False)
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "SlugcatPet"
_SCRIPT = "run_slugcatpet.py"
_VALUE = ""  # 登记名：源码运行不覆盖打包版的登记


def configure(name: str, script: str) -> None:
    """别的 app 用自己的登记名和源码入口。"""
    global _NAME, _SCRIPT, _VALUE
    _NAME, _SCRIPT = name, script
    _VALUE = _NAME if _FROZEN else f"{_NAME} (source)"


configure(_NAME, _SCRIPT)


def _launch_command() -> str:
    if _FROZEN:
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" "{base_dir() / _SCRIPT}"'


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


def sync_path() -> None:
    """已开启自启时把登记的启动命令指向当前程序。"""
    if sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
        ) as k:
            cur, _ = winreg.QueryValueEx(k, _VALUE)
            cmd = _launch_command()
            if cur != cmd:
                winreg.SetValueEx(k, _VALUE, 0, winreg.REG_SZ, cmd)
    except OSError:
        pass


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
