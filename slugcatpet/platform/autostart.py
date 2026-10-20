"""开机自启：Windows 写 HKCU Run，Linux 写 XDG autostart .desktop。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .._paths import base_dir
from .appid import DESKTOP_FILE_NAME

_FROZEN = getattr(sys, "frozen", False)
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "SlugcatPet" if _FROZEN else "SlugcatPet (source)"  # 源码运行不覆盖打包版的登记


def _autostart_dir() -> Path:
    """XDG autostart 目录；优先 XDG_CONFIG_HOME，测试时可用环境变量隔离。"""
    root = os.environ.get("XDG_CONFIG_HOME")
    return (Path(root) if root else Path.home() / ".config") / "autostart"


def _autostart_file() -> Path:
    return _autostart_dir() / f"{DESKTOP_FILE_NAME}.desktop"


def _exec_quote(value) -> str:
    """Desktop Entry 的 Exec 双引号转义。"%%" 是字面百分号。"""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{text}"'


def _linux_launch_command() -> str:
    if _FROZEN:
        return _exec_quote(sys.executable)
    return f"{_exec_quote(sys.executable)} {_exec_quote(base_dir() / 'run_slugcatpet.py')}"


def _workdir() -> Path:
    if _FROZEN:
        return Path(sys.executable).resolve().parent
    return base_dir()


def _launch_command() -> str:
    if _FROZEN:
        return f'"{sys.executable}"'
    if sys.platform == "win32":
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        return f'"{pyw if pyw.exists() else exe}" "{base_dir() / "run_slugcatpet.py"}"'
    return _linux_launch_command()


def _desktop_text() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=SlugcatPet\n"
        "Comment=Desktop pet on Rain World assets\n"
        f"Exec={_linux_launch_command()}\n"
        f"Path={_workdir()}\n"
        "Icon=slugcatpet\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _write_linux(on: bool) -> bool:
    path = _autostart_file()
    try:
        if on:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(_desktop_text(), encoding="utf-8")
            tmp.chmod(0o644)
            os.replace(tmp, path)
        else:
            path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def is_enabled() -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, _VALUE)
            return True
        except OSError:
            return False
    return _autostart_file().is_file()


def sync_path() -> None:
    """已开启自启时把登记的启动命令指向当前程序。"""
    if sys.platform == "win32":
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
        return
    path = _autostart_file()
    if not path.is_file():
        return
    try:
        cur = path.read_text(encoding="utf-8")
        new = _desktop_text()
        if cur != new:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(new, encoding="utf-8")
            tmp.chmod(0o644)
            os.replace(tmp, path)
    except OSError:
        pass


def set_enabled(on: bool) -> bool:
    if sys.platform == "win32":
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
    return _write_linux(on)
