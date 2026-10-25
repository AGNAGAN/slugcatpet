"""开机自启：Windows 写 HKCU Run，Linux 写 XDG autostart .desktop。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .._paths import base_dir
from .appid import DESKTOP_FILE_NAME

_FROZEN = getattr(sys, "frozen", False)
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "SlugcatPet"
_SCRIPT = "run_slugcatpet.py"
_LAUNCHER = "slugcatpet"
_VALUE = ""  # 登记名：源码运行不覆盖打包版的登记


def configure(name: str, script: str) -> None:
    """别的 app 用自己的登记名和源码入口。"""
    global _NAME, _SCRIPT, _LAUNCHER, _VALUE
    _NAME, _SCRIPT = name, script
    stem = Path(script).stem
    _LAUNCHER = stem[4:] if stem.startswith("run_") else stem
    _VALUE = _NAME if _FROZEN else f"{_NAME} (source)"


configure(_NAME, _SCRIPT)


def _autostart_dir() -> Path:
    """XDG autostart 目录；优先 XDG_CONFIG_HOME，测试时可用环境变量隔离。"""
    root = os.environ.get("XDG_CONFIG_HOME")
    return (Path(root) if root else Path.home() / ".config") / "autostart"


def _desktop_file_name() -> str:
    """蛞蝓猫沿用已安装的 desktop id；别的 app 用独立文件。"""
    return DESKTOP_FILE_NAME if _NAME == "SlugcatPet" else f"org.slugcatpet.{_NAME}"


def _autostart_file() -> Path:
    return _autostart_dir() / f"{_desktop_file_name()}.desktop"


def _exec_quote(value) -> str:
    """Desktop Entry 的 Exec 双引号转义。"%%" 是字面百分号。"""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{text}"'


def _source_launch_command() -> str:
    return f"{_exec_quote(sys.executable)} {_exec_quote(base_dir() / _SCRIPT)}"


def _installed_launcher() -> str | None:
    """打包/uv tool 安装后的 console script。"""
    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 is not None and argv0.name == _LAUNCHER and argv0.is_file():
        return str(argv0.resolve())
    return shutil.which(_LAUNCHER)


def _linux_launch_command() -> str:
    if _FROZEN:
        return _exec_quote(sys.executable)
    if (base_dir() / _SCRIPT).is_file():
        return _source_launch_command()
    launcher = _installed_launcher()
    if launcher:
        return _exec_quote(launcher)
    # 源码仓库不完整时仍保留可诊断的旧路径，而不是生成空 Exec。
    return _source_launch_command()


def _workdir() -> Path:
    if _FROZEN:
        return Path(sys.executable).resolve().parent
    if (base_dir() / _SCRIPT).is_file():
        return base_dir()
    return Path.home()


def _launch_command() -> str:
    if _FROZEN:
        return f'"{sys.executable}"'
    if sys.platform == "win32":
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        return f'"{pyw if pyw.exists() else exe}" "{base_dir() / _SCRIPT}"'
    return _linux_launch_command()


def _desktop_text() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={_NAME}\n"
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
