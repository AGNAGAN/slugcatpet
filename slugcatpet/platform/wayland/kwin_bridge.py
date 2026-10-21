"""KWin 脚本 + DBus 桥。

KWin 脚本负责普通 Wayland 客户端做不到的事情：把 overlay 钉在目标输出上、
保持置顶，并把全局光标位置推给 Python。Python 侧只暴露一个很小的 session
bus 服务；脚本不可用时应用继续运行，``supports_*`` 会变为 False。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QTimer, Signal, Slot, ClassInfo
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
from PySide6.QtGui import QGuiApplication, QRegion

from ..._paths import user_dir
from ...control.hotkey import FROZEN_KEYS, GLOBAL_KEYS, qt_key_code, shortcut_sequence
from ..appid import DESKTOP_FILE_NAME
from ..backend import CURSOR_CAPTURE_TITLE, DesktopBackend, OVERLAY_TITLE

log = logging.getLogger(__name__)

DBUS_SERVICE = "org.slugcatpet.Bridge"
DBUS_PATH = "/Bridge"
DBUS_INTERFACE = "org.slugcatpet.Bridge"
KWIN_SERVICE = "org.kde.KWin"
KWIN_PATH = "/Scripting"
KWIN_INTERFACE = "org.kde.kwin.Scripting"
# 运行时脚本用独立名字，避免 KWin 的 reconfigure 按持久插件的启用状态
# 把它一起卸载；持久插件名仍是 slugcatpet。
PLUGIN_NAME = "slugcatpet-runtime"
PERSISTENT_PLUGIN_NAME = "slugcatpet"
_MIN_SIDE = 24
_SCREEN_TOL = 2

_HOTKEY_NAMES = {
    1: "abort",
    2: "quit",
    3: "HUD",
    4: "cancel placement",
    5: "freeze",
    6: "step",
    7: "step x10",
    8: "rain timer",
}


def _qt_supports_pointer_warp() -> bool:
    """Qt 6.12 的 Wayland 插件实现了 wp_pointer_warp_v1，QCursor.setPos 可用。"""
    try:
        from PySide6.QtCore import qVersion

        major, minor = (int(part) for part in qVersion().split(".")[:2])
    except (ImportError, TypeError, ValueError):
        return False
    return (major, minor) >= (6, 12)


def _shortcut_specs() -> list[dict]:
    """生成 KWin 脚本需要的快捷键定义；Windows 的 mods/vk 映射到这里。"""
    specs = []
    for table in (GLOBAL_KEYS, FROZEN_KEYS):
        for hotkey_id, (mods, vk, _label) in table.items():
            key = shortcut_sequence(mods, vk)
            specs.append(
                {
                    "id": int(hotkey_id),
                    "text": f"SlugcatPet: {_HOTKEY_NAMES.get(hotkey_id, hotkey_id)} ({key})",
                    "key": key,
                    "code": qt_key_code(mods, vk),
                }
            )
    return specs


@ClassInfo({"D-Bus Interface": DBUS_INTERFACE})
class _BridgeService(QObject):
    cursor_moved = Signal(int, int)
    overlay_geometry_changed = Signal(int, int, int, int)
    fullscreen_changed = Signal(bool, int, int, int, int)
    window_list_changed = Signal(str)
    hotkey_pressed = Signal(int)
    hotkey_status_changed = Signal(str)
    log_message = Signal(str)

    @Slot(int, int)
    def CursorMoved(self, x: int, y: int) -> None:
        self.cursor_moved.emit(x, y)

    @Slot(int, int, int, int)
    def OverlayGeometryChanged(self, x: int, y: int, w: int, h: int) -> None:
        self.overlay_geometry_changed.emit(x, y, w, h)

    @Slot(bool, int, int, int, int)
    def FullscreenChanged(self, full: bool, x: int, y: int, w: int, h: int) -> None:
        self.fullscreen_changed.emit(bool(full), x, y, w, h)

    @Slot(str)
    def WindowListChanged(self, payload: str) -> None:
        self.window_list_changed.emit(payload)

    @Slot(int)
    def HotkeyPressed(self, hotkey_id: int) -> None:
        self.hotkey_pressed.emit(int(hotkey_id))

    @Slot(str)
    def HotkeyStatus(self, payload: str) -> None:
        self.hotkey_status_changed.emit(payload)

    @Slot(str)
    def Log(self, message: str) -> None:
        self.log_message.emit(message)


class WaylandKWinBackend(QObject, DesktopBackend):
    """通过 KWin Scripting DBus 接口控制 overlay。"""

    name = "kwin"
    cursor_moved = Signal(int, int)
    overlay_geometry_changed = Signal(int, int, int, int)
    fullscreen_changed = Signal(bool, int, int, int, int)
    window_list_changed = Signal(str)
    hotkey_pressed = Signal(int)
    hotkey_status_changed = Signal(str)

    def __init__(self):
        QObject.__init__(self)
        self._window = None
        self._target_screen = ""
        self._rect = QRect()
        self._origin = (0, 0)
        self._cursor: tuple[int, int] | None = None
        self._script_loaded = False
        self._script_path: Path | None = None
        self._service_registered = False
        self._object_registered = False
        self._shutting_down = False
        self._fullscreen: bool | None = None
        self._fullscreen_rect = QRect()
        self._window_data: list[QRect] = []
        self._window_rects: list[QRect] = []
        self._hotkey_specs = _shortcut_specs()
        self._hotkey_by_id = {int(spec["id"]): spec for spec in self._hotkey_specs}
        self._hotkey_status: dict[int, bool] = {}

        self._service = _BridgeService(self)
        self._service.cursor_moved.connect(self._on_cursor)
        self._service.overlay_geometry_changed.connect(self._on_overlay_geometry)
        self._service.fullscreen_changed.connect(self._on_fullscreen)
        self._service.window_list_changed.connect(self._on_window_list)
        self._service.hotkey_pressed.connect(self.hotkey_pressed.emit)
        self._service.hotkey_status_changed.connect(self._on_hotkey_status)
        self._service.log_message.connect(self._on_log)
        self._register_service()

    # ---- 能力开关 -----------------------------------------------------

    @property
    def available(self) -> bool:
        return self._service_registered

    @property
    def supports_geometry(self) -> bool:
        return self._script_loaded

    @property
    def supports_topmost(self) -> bool:
        return self._script_loaded

    @property
    def supports_cursor(self) -> bool:
        return self._service_registered and self._script_loaded

    @property
    def supports_cursor_write(self) -> bool:
        """Wayland 写光标依赖 Qt pointer-warp；KWin 6.8 已提供该协议。"""
        return self._service_registered and self._script_loaded and _qt_supports_pointer_warp()

    @property
    def supports_fullscreen(self) -> bool:
        return self._service_registered and self._script_loaded

    @property
    def supports_shelters(self) -> bool:
        return self._service_registered and self._script_loaded

    @property
    def supports_hotkeys(self) -> bool:
        return self._service_registered and self._script_loaded and bool(self._hotkey_specs)

    def hotkey_conflicts(self) -> list[str]:
        """返回未注册成功的组合键文本，供设置页提示。"""
        out = []
        for hotkey_id, ok in self._hotkey_status.items():
            if ok:
                continue
            spec = self._hotkey_by_id.get(int(hotkey_id))
            if spec is not None:
                out.append(str(spec["key"]))
        return out

    def hotkey_registered(self, hotkey_id: int) -> bool | None:
        return self._hotkey_status.get(int(hotkey_id))

    # ---- 服务注册 -----------------------------------------------------

    def _register_service(self) -> None:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            log.warning("KWin bridge: session bus unavailable")
            return
        if not bus.registerService(DBUS_SERVICE):
            log.warning("KWin bridge: service %s is already owned", DBUS_SERVICE)
            return
        self._service_registered = True
        if not bus.registerObject(
            DBUS_PATH,
            self._service,
            QDBusConnection.RegisterOption.ExportAllSlots,
        ):
            log.warning("KWin bridge: failed to export %s", DBUS_PATH)
            bus.unregisterService(DBUS_SERVICE)
            self._service_registered = False
            return
        self._object_registered = True

    # ---- overlay ------------------------------------------------------

    def attach_overlay(self, window) -> bool:
        if self._shutting_down or window is None:
            return False
        self._window = window
        self._read_window_config()
        if not self._service_registered:
            return False
        return self._load_script()

    def configure_overlay(self, screen_name: str, rect: QRect) -> None:
        if self._shutting_down or rect is None or rect.isEmpty():
            return
        name = screen_name or self._target_screen
        if name == self._target_screen and rect == self._rect:
            return
        self._target_screen = name
        self._rect = QRect(rect)
        self._origin = (rect.x(), rect.y())
        if self._window is not None and self._service_registered:
            self._load_script()

    def set_overlay_geometry(self, rect: QRect) -> None:
        self.configure_overlay(self._target_screen, rect)

    def _read_window_config(self) -> None:
        window = self._window
        if window is None:
            return
        screen = window.screen() or QGuiApplication.primaryScreen()
        get_name = getattr(window, "target_output_name", None)
        name = get_name() if callable(get_name) else ""
        if not name and screen is not None:
            name = screen.name()
        if name:
            self._target_screen = name
        rect = None
        get_rect = getattr(window, "overlay_rect", None)
        if callable(get_rect):
            rect = get_rect()
        if not isinstance(rect, QRect) or rect.isEmpty():
            if screen is not None:
                rect = QRect(screen.availableGeometry().topLeft(), window.size())
        if isinstance(rect, QRect) and not rect.isEmpty():
            self._rect = QRect(rect)
            self._origin = (rect.x(), rect.y())

    def overlay_origin(self) -> tuple[int, int]:
        return self._origin

    def cursor_global(self) -> tuple[int, int] | None:
        return self._cursor

    def set_input_region(self, window, region: QRegion) -> bool:
        from .input import set_input_region

        return set_input_region(window, region)

    # ---- 全屏与窗口快照 -----------------------------------------------

    def _target_geometry(self) -> QRect | None:
        if self._target_screen:
            for screen in QGuiApplication.screens():
                if screen.name() == self._target_screen:
                    return QRect(screen.geometry())
        if self._window is not None:
            try:
                screen = self._window.screen() or QGuiApplication.primaryScreen()
            except Exception:
                screen = None
            if screen is not None:
                return QRect(screen.geometry())
        if not self._rect.isEmpty():
            return QRect(self._rect)
        return None

    def foreground_fullscreen(self) -> bool | None:
        """活动窗口是否全屏盖住 overlay 所在输出；None 表示桥未就绪。"""
        if not self.supports_fullscreen or self._fullscreen is None:
            return None
        if not self._fullscreen:
            return False
        if self._fullscreen_rect.isEmpty():
            return None
        target = self._target_geometry()
        if target is None or target.isEmpty():
            return True
        r = self._fullscreen_rect
        t = _SCREEN_TOL
        return (
            r.x() <= target.x() + t
            and r.y() <= target.y() + t
            and r.x() + r.width() >= target.x() + target.width() - t
            and r.y() + r.height() >= target.y() + target.height() - t
        )

    def window_rects(self) -> list[QRect]:
        """挡雨窗口的 overlay-local 逻辑矩形。"""
        if not self.supports_shelters:
            return []
        return [QRect(r) for r in self._window_rects]

    @staticmethod
    def parse_window_rects(
        payload: str,
        origin: tuple[int, int] = (0, 0),
        target_screen: str = "",
    ) -> list[QRect]:
        """解析 KWin 快照并换成 overlay-local 坐标；坏数据直接跳过。"""
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        ox, oy = origin
        out = []
        for item in data:
            if not isinstance(item, dict):
                continue
            output = item.get("output")
            if target_screen and output and str(output) != target_screen:
                continue
            try:
                x = int(item["x"])
                y = int(item["y"])
                w = int(item["w"])
                h = int(item["h"])
            except (KeyError, TypeError, ValueError):
                continue
            if w < _MIN_SIDE or h < _MIN_SIDE:
                continue
            out.append(QRect(x - ox, y - oy, w, h))
        return out

    # ---- 热键 ---------------------------------------------------------

    def register_hotkey(self, hotkey_id: int, mods: int, vk: int) -> bool:
        """KWin 脚本在加载时统一注册固定快捷键；这里只报告可用性。"""
        if not self.supports_hotkeys or int(hotkey_id) not in self._hotkey_by_id:
            return False
        status = self._hotkey_status.get(int(hotkey_id))
        return status is not False

    # ---- KWin 脚本 ----------------------------------------------------

    def _load_script(self) -> bool:
        if self._shutting_down:
            return False
        try:
            source = self._render_script()
            path = user_dir() / "kwin" / "slugcatpet.js"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
            self._script_path = path
            # 持久插件如果已安装，保持其内容与当前输出一致。KWin 在某些
            # start()/reconfigure 时序下会重新加载持久插件；若它仍是旧几何，
            # 会在运行时脚本之后把 overlay 拉回上一块屏幕。
            try:
                from . import kwin_install

                if kwin_install.is_installed():
                    kwin_install.install(source)
            except Exception as exc:
                # 持久插件写失败不应影响本次运行时脚本加载。
                log.warning("KWin bridge: cannot sync persistent script: %s", exc)
        except Exception as exc:
            log.warning("KWin bridge: cannot write script: %s", exc)
            self._script_loaded = False
            return False

        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(KWIN_SERVICE, KWIN_PATH, KWIN_INTERFACE, bus)
        if not iface.isValid():
            log.warning("KWin bridge: %s%s is unavailable", KWIN_SERVICE, KWIN_PATH)
            self._script_loaded = False
            return False

        # 上一次异常退出可能留下同名脚本；登录时 KWin 也可能已加载持久插件。
        # 两者都先卸载，避免重复的光标/几何回调。
        self._call_scripting(iface, "unloadScript", PLUGIN_NAME, required=False)
        self._call_scripting(iface, "unloadScript", PERSISTENT_PLUGIN_NAME, required=False)
        self._fullscreen = None
        self._fullscreen_rect = QRect()
        self._hotkey_status.clear()
        reply = self._call_scripting(iface, "loadScript", str(path), PLUGIN_NAME)
        if reply is None:
            self._script_loaded = False
            return False
        self._call_scripting(iface, "start", required=False)
        self._script_loaded = True
        # KWin 的 start() 可能按 [Plugins] 配置把持久脚本也一起启动；它带的是
        # 上次写入的几何，会在本脚本之后执行并覆盖目标输出。运行时脚本使用
        # 独立插件名，因此延迟再卸载持久插件是安全的。
        for delay in (0, 300, 1200):
            QTimer.singleShot(delay, self._unload_persistent_script)
        log.info("KWin bridge: script loaded for %s %s", self._target_screen, self._rect)
        return True

    def _unload_persistent_script(self) -> None:
        if self._shutting_down:
            return
        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(KWIN_SERVICE, KWIN_PATH, KWIN_INTERFACE, bus)
        if iface.isValid():
            self._call_scripting(iface, "unloadScript", PERSISTENT_PLUGIN_NAME, required=False)

    def reload(self) -> bool:
        if self._window is None or not self._service_registered or self._shutting_down:
            return False
        return self._load_script()

    def render_script(self) -> str:
        """当前输出/几何对应的 KWin 脚本，供持久安装使用。"""
        return self._render_script()

    def integration_state(self):
        from . import kwin_install

        return kwin_install.state()

    def set_integration_enabled(self, on: bool) -> bool:
        """安装/启用登录后自动加载的 KWin 脚本。

        运行时脚本仍然由 ``loadScript()`` 管理；这里的开关只影响 KWin 启动时
        是否从用户脚本目录自动加载。启用/停用后 reconfigure，并延迟重新加载
        运行时脚本：KWin 可能异步加载持久插件，运行时脚本用独立插件名，
        不会被它的启用状态带走。
        """
        from . import kwin_install

        if on and not kwin_install.install(self._render_script()):
            return False
        if not kwin_install.set_enabled(bool(on)):
            return False
        if not kwin_install.reconfigure():
            log.warning("KWin integration: saved, but reconfigure was not accepted")
        if self._window is not None and self._service_registered and not self._shutting_down:
            # 给 KWin 的 reconfigure 一点时间；reload 会同时清掉可能被加载的
            # 持久插件，确保本次会话只有 slugcatpet-runtime 在运行。
            QTimer.singleShot(700, self.reload)
        return True

    def _render_script(self) -> str:
        template = Path(__file__).with_name("kwin_script") / "contents" / "code" / "main.js"
        text = template.read_text(encoding="utf-8")
        rect = self._rect
        specs = getattr(self, "_hotkey_specs", None) or _shortcut_specs()
        values = {
            "@APP_ID@": DESKTOP_FILE_NAME,
            "@OVERLAY_CAPTION@": OVERLAY_TITLE,
            "@CAPTURE_CAPTION@": CURSOR_CAPTURE_TITLE,
            "@TARGET_SCREEN@": self._target_screen,
            "@OVERLAY_X@": str(rect.x()),
            "@OVERLAY_Y@": str(rect.y()),
            "@OVERLAY_W@": str(rect.width()),
            "@OVERLAY_H@": str(rect.height()),
            "@HOTKEYS_JSON@": json.dumps(specs, ensure_ascii=False),
            "@DBUS_SERVICE@": DBUS_SERVICE,
            "@DBUS_PATH@": DBUS_PATH,
            "@DBUS_INTERFACE@": DBUS_INTERFACE,
        }
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    def _call_scripting(self, iface: QDBusInterface, method: str, *args, required=True):
        try:
            reply = iface.call(method, *args)
        except Exception as exc:
            if required:
                log.warning("KWin bridge: %s failed: %s", method, exc)
            return None
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            if required:
                log.warning("KWin bridge: %s error: %s", method, reply.errorMessage())
            return None
        return reply

    def _unload_script(self) -> None:
        if not self._script_loaded:
            return
        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(KWIN_SERVICE, KWIN_PATH, KWIN_INTERFACE, bus)
        if iface.isValid():
            self._call_scripting(iface, "unloadScript", PLUGIN_NAME, required=False)
        self._script_loaded = False

    # ---- 回调 ---------------------------------------------------------

    def _on_cursor(self, x: int, y: int) -> None:
        self._cursor = (x, y)
        log.debug("KWin bridge: cursor %s,%s", x, y)
        self.cursor_moved.emit(x, y)

    def _on_overlay_geometry(self, x: int, y: int, w: int, h: int) -> None:
        self._origin = (x, y)
        self._rect = QRect(x, y, w, h)
        log.debug("KWin bridge: overlay geometry %s,%s %sx%s", x, y, w, h)
        self.overlay_geometry_changed.emit(x, y, w, h)

    def _on_fullscreen(self, full: bool, x: int, y: int, w: int, h: int) -> None:
        rect = QRect(x, y, w, h)
        changed = bool(full) != self._fullscreen or rect != self._fullscreen_rect
        self._fullscreen = bool(full)
        self._fullscreen_rect = rect
        if changed:
            log.debug("KWin bridge: fullscreen %s %s", self._fullscreen, rect)
            self.fullscreen_changed.emit(bool(full), x, y, w, h)

    def _on_window_list(self, payload: str) -> None:
        self._window_data = self.parse_window_rects(payload, self._origin, self._target_screen)
        self._window_rects = [QRect(r) for r in self._window_data]
        log.debug("KWin bridge: %s shelter windows", len(self._window_rects))
        self.window_list_changed.emit(payload)

    def _on_hotkey_status(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return
        if not isinstance(data, list):
            return
        status = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                status[int(item["id"])] = bool(item.get("ok"))
            except (KeyError, TypeError, ValueError):
                continue
        self._hotkey_status = status
        conflicts = self.hotkey_conflicts()
        if conflicts:
            log.warning("KWin bridge: unregistered shortcuts: %s", ", ".join(conflicts))
        self.hotkey_status_changed.emit(payload)
        # registerShortcut 只表示脚本接受了定义；真正是否拿到键要在
        # KGlobalAccel 注册完成后查一次。
        QTimer.singleShot(300, self._verify_hotkeys)

    def _verify_hotkeys(self) -> None:
        if self._shutting_down or not self._script_loaded:
            return
        iface = QDBusInterface(
            "org.kde.kglobalaccel",
            "/kglobalaccel",
            "org.kde.KGlobalAccel",
            QDBusConnection.sessionBus(),
        )
        if not iface.isValid():
            return
        status = {}
        for spec in self._hotkey_specs:
            reply = iface.call("action", int(spec["code"]))
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                continue
            args = reply.arguments()
            action = args[0] if args and isinstance(args[0], list) else []
            owner = action[1] if len(action) > 1 else ""
            status[int(spec["id"])] = owner == f"slugcatpet_{spec['id']}"
        if not status:
            return
        self._hotkey_status.update(status)
        conflicts = self.hotkey_conflicts()
        if conflicts:
            log.warning("KWin bridge: inactive shortcuts: %s", ", ".join(conflicts))
        payload = json.dumps(
            [{"id": hotkey_id, "ok": ok} for hotkey_id, ok in sorted(status.items())],
            ensure_ascii=False,
        )
        self.hotkey_status_changed.emit(payload)

    def _on_log(self, message: str) -> None:
        log.info("KWin bridge: %s", message)

    # ---- 生命周期 -----------------------------------------------------

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._unload_script()
        bus = QDBusConnection.sessionBus()
        if self._object_registered:
            bus.unregisterObject(DBUS_PATH)
            self._object_registered = False
        if self._service_registered:
            bus.unregisterService(DBUS_SERVICE)
            self._service_registered = False
        self._cursor = None
        self._window = None
        self._fullscreen = None
        self._fullscreen_rect = QRect()
        self._window_rects = []
        self._hotkey_status.clear()
