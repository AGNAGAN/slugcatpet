"""KWin 脚本的持久安装与启用。

开发期由 ``kwin_bridge`` 用 ``Scripting.loadScript()`` 临时加载脚本；登录后
自动加载则需要把脚本装进 XDG 数据目录，并在 ``kwinrc`` 的 ``[Plugins]``
组里显式写入 ``slugcatpetEnabled=true``。这个模块只做文件与配置操作，Qt/DBus
调用放在 ``reconfigure()`` 里延迟导入，方便单元测试。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

PLUGIN_ID = "slugcatpet"
PLUGIN_KEY = f"{PLUGIN_ID}Enabled"
KWINRC_SECTION = "Plugins"
KWIN_SERVICE = "org.kde.KWin"
KWIN_PATH = "/KWin"
KWIN_INTERFACE = "org.kde.KWin"
KWIN_SCRIPTING_PATH = "/Scripting"
KWIN_SCRIPTING_INTERFACE = "org.kde.kwin.Scripting"


@dataclass(frozen=True)
class IntegrationState:
    installed: bool
    enabled: bool


def data_home() -> Path:
    root = os.environ.get("XDG_DATA_HOME")
    return Path(root) if root else Path.home() / ".local" / "share"


def config_home() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    return Path(root) if root else Path.home() / ".config"


def install_dir() -> Path:
    return data_home() / "kwin" / "scripts" / PLUGIN_ID


def script_path() -> Path:
    return install_dir() / "contents" / "code" / "main.js"


def metadata_path() -> Path:
    return install_dir() / "metadata.json"


def kwinrc_path() -> Path:
    return config_home() / "kwinrc"


def bundled_metadata() -> str:
    path = Path(__file__).with_name("kwin_script") / "metadata.json"
    return path.read_text(encoding="utf-8")


def is_installed() -> bool:
    return script_path().is_file() and metadata_path().is_file()


def read_plugin_enabled(text: str | None = None) -> bool:
    if text is None:
        try:
            text = kwinrc_path().read_text(encoding="utf-8")
        except OSError:
            return False
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section != KWINRC_SECTION or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == PLUGIN_KEY:
            return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def with_plugin_enabled(text: str, on: bool) -> str:
    """在 KConfig 文本里写入/替换 ``[Plugins] slugcatpetEnabled``。"""
    value = "true" if on else "false"
    lines = text.splitlines()
    target = f"{PLUGIN_KEY}={value}"
    section = None
    section_start = None
    key_line = None
    section_end = None

    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            if section == KWINRC_SECTION and section_end is None:
                section_end = i
            section = line[1:-1].strip()
            if section == KWINRC_SECTION and section_start is None:
                section_start = i
            continue
        if section != KWINRC_SECTION or not line or line.startswith(("#", ";")):
            continue
        if "=" in line and line.split("=", 1)[0].strip() == PLUGIN_KEY:
            key_line = i
            break

    if key_line is not None:
        lines[key_line] = target
    elif section_start is not None:
        end = section_end if section_end is not None else len(lines)
        insert = end
        while insert > section_start + 1 and not lines[insert - 1].strip():
            insert -= 1
        lines.insert(insert, target)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{KWINRC_SECTION}]", target])

    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o644)
    os.replace(tmp, path)


def install(source: str, metadata: str | None = None) -> bool:
    """把渲染后的脚本和 metadata 安装到 KWin 的用户脚本目录。"""
    if not source.strip():
        return False
    try:
        _atomic_write(script_path(), source)
        _atomic_write(metadata_path(), metadata if metadata is not None else bundled_metadata())
        return True
    except OSError as exc:
        log.warning("KWin integration: install failed: %s", exc)
        return False


def set_enabled(on: bool) -> bool:
    path = kwinrc_path()
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        new = with_plugin_enabled(text, bool(on))
        if new != text or not path.is_file():
            _atomic_write(path, new)
        return True
    except OSError as exc:
        log.warning("KWin integration: cannot update %s: %s", path, exc)
        return False


def is_enabled() -> bool:
    return read_plugin_enabled()


def uninstall() -> bool:
    """删除脚本并关闭 KWin 插件；保留用户数据和配置文件的其余内容。"""
    ok = True
    try:
        path = install_dir()
        if path.is_dir():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
    except OSError as exc:
        log.warning("KWin integration: uninstall failed: %s", exc)
        ok = False
    return set_enabled(False) and ok


def reconfigure() -> bool:
    """让正在运行的 KWin 重新读取 kwinrc；KWin 不运行时安静返回 False。"""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        iface = QDBusInterface(KWIN_SERVICE, KWIN_PATH, KWIN_INTERFACE, bus)
        if not iface.isValid():
            return False
        reply = iface.call("reconfigure")
        return reply.type() != QDBusMessage.MessageType.ErrorMessage
    except Exception as exc:
        log.warning("KWin integration: reconfigure failed: %s", exc)
        return False


def unload_script(plugin_id: str = PLUGIN_ID) -> bool:
    """从当前 KWin 会话卸载脚本；配置变更不会自动卸掉已加载实例。"""
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        iface = QDBusInterface(KWIN_SERVICE, KWIN_SCRIPTING_PATH, KWIN_SCRIPTING_INTERFACE, bus)
        if not iface.isValid():
            return False
        reply = iface.call("unloadScript", plugin_id)
        return reply.type() != QDBusMessage.MessageType.ErrorMessage
    except Exception as exc:
        log.warning("KWin integration: unload failed: %s", exc)
        return False


def state() -> IntegrationState:
    return IntegrationState(installed=is_installed(), enabled=is_enabled())
