#!/usr/bin/env python3
"""本机 KWin 持久脚本安装/启用冒烟测试。

会临时修改真实 ``kwinrc`` 和 ``~/.local/share/kwin/scripts/slugcatpet``，
结束后恢复配置并卸载脚本。只在 Plasma/Wayland 开发机上运行。
"""

from __future__ import annotations

import sys
import time
from types import SimpleNamespace

from PySide6.QtCore import QRect
from PySide6.QtDBus import QDBusConnection, QDBusInterface

from slugcatpet.platform.wayland import kwin_install
from slugcatpet.platform.wayland.kwin_bridge import WaylandKWinBackend


def _is_loaded(name: str) -> bool:
    bus = QDBusConnection.sessionBus()
    iface = QDBusInterface(
        kwin_install.KWIN_SERVICE,
        kwin_install.KWIN_SCRIPTING_PATH,
        kwin_install.KWIN_SCRIPTING_INTERFACE,
        bus,
    )
    if not iface.isValid():
        return False
    reply = iface.call("isScriptLoaded", name)
    return bool(reply.arguments() and reply.arguments()[0])


def _wait_loaded(name: str, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_loaded(name):
            return True
        time.sleep(0.1)
    return False


def main() -> int:
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        print("FAIL: session bus unavailable")
        return 2
    iface = QDBusInterface(
        kwin_install.KWIN_SERVICE,
        kwin_install.KWIN_SCRIPTING_PATH,
        kwin_install.KWIN_SCRIPTING_INTERFACE,
        bus,
    )
    if not iface.isValid():
        print("FAIL: KWin scripting interface unavailable")
        return 2

    rc_path = kwin_install.kwinrc_path()
    existed = rc_path.is_file()
    backup = rc_path.read_bytes() if existed else b""
    backend = SimpleNamespace(_target_screen="", _rect=QRect(0, 0, 1920, 1080))
    source = WaylandKWinBackend._render_script(backend)
    ok = False
    try:
        if not kwin_install.install(source):
            print("FAIL: cannot install script")
            return 1
        if not kwin_install.set_enabled(True):
            print("FAIL: cannot update kwinrc")
            return 1
        if not kwin_install.reconfigure():
            print("FAIL: KWin reconfigure rejected")
            return 1
        ok = _wait_loaded(kwin_install.PLUGIN_ID)
        print("loaded after enable:", ok)
        if not ok:
            return 1
    finally:
        kwin_install.unload_script(kwin_install.PLUGIN_ID)
        kwin_install.uninstall()
        kwin_install.reconfigure()
        if existed:
            rc_path.parent.mkdir(parents=True, exist_ok=True)
            rc_path.write_bytes(backup)
        else:
            rc_path.unlink(missing_ok=True)
        kwin_install.reconfigure()

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
