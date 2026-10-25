"""Phase 3 的纯逻辑测试：窗口快照、全屏判定和全屏收起。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QObject, QRect, Signal

from slugcatpet.control.hotkey import DEFAULT_HOTKEYS, HK_MEOW, MOD_ALT, HotkeyFilter
from slugcatpet.platform.envwatch import EnvironmentWatcher
from slugcatpet.platform.wayland.kwin_bridge import WaylandKWinBackend, _shortcut_specs


class _FakePet:
    cfg_fullscreen_mode = "hide"

    def __init__(self):
        self.frozen = False
        self.floor_sink = False

    def freeze(self, source):
        self.frozen = True

    def unfreeze(self, source):
        self.frozen = False

    def set_floor_sink(self, on):
        self.floor_sink = bool(on)

    def apply_workspace(self, area, geometry):
        pass


class _FakeWindow:
    def __init__(self):
        self.visible = True
        self.hidden = 0
        self.shown = 0

    def isVisible(self):
        return self.visible

    def hide(self):
        self.visible = False
        self.hidden += 1

    def show(self):
        self.visible = True
        self.shown += 1


class WindowSnapshotTests(unittest.TestCase):
    def test_filters_output_and_bad_rectangles(self):
        payload = json.dumps(
            [
                {"x": 10, "y": 900, "w": 400, "h": 300, "output": "HDMI-A-1"},
                {"x": 10, "y": 0, "w": 400, "h": 300, "output": "eDP-1"},
                {"x": 10, "y": 900, "w": 5, "h": 300, "output": "HDMI-A-1"},
                {"x": "bad", "y": 900, "w": 400, "h": 300, "output": "HDMI-A-1"},
                {"x": 20, "y": 1200, "w": 300, "h": 200},
            ]
        )
        rects = WaylandKWinBackend.parse_window_rects(payload, (0, 900), "HDMI-A-1")
        self.assertEqual(len(rects), 2)
        self.assertEqual(rects[0], QRect(10, 0, 400, 300))
        self.assertEqual(rects[1], QRect(20, 300, 300, 200))

    def test_bad_json_is_empty(self):
        self.assertEqual(WaylandKWinBackend.parse_window_rects("{"), [])
        self.assertEqual(WaylandKWinBackend.parse_window_rects("{}"), [])
        self.assertEqual(WaylandKWinBackend.parse_window_rects(None), [])


class FullscreenTests(unittest.TestCase):
    @staticmethod
    def _backend(full, rect, screen="eDP-1"):
        obj = type("Backend", (), {})()
        obj.supports_fullscreen = True
        obj._fullscreen = full
        obj._fullscreen_rect = QRect(*rect)
        obj._target_screen = screen
        obj._rect = QRect(0, 0, 1440, 900)
        obj._target_geometry = lambda: (
            QRect(0, 900, 1707, 1067) if screen == "HDMI-A-1" else QRect(0, 0, 1440, 900)
        )
        return obj

    def test_fullscreen_on_target_output(self):
        b = self._backend(True, (0, 0, 1440, 900))
        self.assertTrue(WaylandKWinBackend.foreground_fullscreen(b))

    def test_fullscreen_on_other_output_does_not_hide(self):
        b = self._backend(True, (0, 900, 1707, 1067), screen="HDMI-A-1")
        self.assertTrue(WaylandKWinBackend.foreground_fullscreen(b))
        b = self._backend(True, (0, 0, 1440, 900), screen="HDMI-A-1")
        self.assertFalse(WaylandKWinBackend.foreground_fullscreen(b))

    def test_unknown_state(self):
        b = self._backend(None, (0, 0, 0, 0))
        self.assertIsNone(WaylandKWinBackend.foreground_fullscreen(b))


class EnvwatchProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_provider_hides_and_restores_after_debounce(self):
        win = _FakeWindow()
        pet = _FakePet()
        state = {"full": True}
        watcher = EnvironmentWatcher(
            [win],
            pet,
            state_provider=lambda: 5,
            fullscreen_provider=lambda: state["full"],
        )
        watcher._check_fullscreen()
        watcher._check_fullscreen()
        self.assertFalse(win.visible)
        self.assertTrue(pet.frozen)

        state["full"] = False
        win.visible = False
        watcher._check_fullscreen()
        watcher._check_fullscreen()
        self.assertTrue(win.visible)
        self.assertFalse(pet.frozen)

    def test_unknown_provider_keeps_state(self):
        win = _FakeWindow()
        pet = _FakePet()
        watcher = EnvironmentWatcher(
            [win],
            pet,
            state_provider=lambda: 5,
            fullscreen_provider=lambda: None,
        )
        for _ in range(3):
            watcher._check_fullscreen()
        self.assertTrue(win.visible)
        self.assertFalse(watcher._fullscreen)


class ShortcutSpecTests(unittest.TestCase):
    def test_specs_cover_global_and_frozen_keys(self):
        with patch(
            "slugcatpet.platform.wayland.kwin_bridge.load_hotkeys", return_value=dict(DEFAULT_HOTKEYS)
        ):
            specs = _shortcut_specs()
        ids = {spec["id"] for spec in specs}
        self.assertEqual(ids, {1, 2, 3, 5, 6, 7, 8, 9})
        keys = {spec["id"]: spec["key"] for spec in specs}
        self.assertEqual(keys[5], "Ctrl+Alt+P")
        self.assertEqual(keys[7], "Ctrl+Alt+Shift+Right")
        self.assertEqual(keys[8], "Ctrl+Alt+R")
        self.assertEqual(keys[9], "Alt+M")
        codes = {spec["id"]: spec["code"] for spec in specs}
        self.assertEqual(codes[5], 201326672)
        self.assertEqual(codes[7], 251658260)
        self.assertEqual(codes[9], 134217805)
        actions = {spec["id"]: spec["action"] for spec in specs}
        self.assertEqual(len(set(actions.values())), len(actions))
        for hotkey_id, action in actions.items():
            self.assertTrue(action.startswith("slugcatpet_"))
            self.assertTrue(action.endswith(f"_{hotkey_id}"))

    def test_specs_follow_custom_hotkeys(self):
        keys = dict(DEFAULT_HOTKEYS)
        keys["freeze"] = (MOD_ALT, 0x4B)  # Alt+K
        with patch("slugcatpet.platform.wayland.kwin_bridge.load_hotkeys", return_value=keys):
            specs = _shortcut_specs()
        by_id = {spec["id"]: spec for spec in specs}
        self.assertEqual(by_id[5]["key"], "Alt+K")
        with patch(
            "slugcatpet.platform.wayland.kwin_bridge.load_hotkeys", return_value=dict(DEFAULT_HOTKEYS)
        ):
            defaults = _shortcut_specs()
        self.assertNotEqual(by_id[5]["action"], {s["id"]: s for s in defaults}[5]["action"])


class _FakeHotkeyBackend(QObject):
    hotkey_pressed = Signal(int)
    hotkey_released = Signal(int)

    def __init__(self):
        super().__init__()
        self.suspended = False
        self.refreshed = 0

    def register_hotkey(self, hotkey_id, mods, vk):
        return True

    def hotkey_available(self, mods, vk):
        return True

    def suspend_hotkeys(self):
        self.suspended = True
        return True

    def resume_hotkeys(self):
        self.suspended = False
        return True

    def refresh_hotkeys(self):
        self.refreshed += 1
        return True


class HotkeyFilterTests(unittest.TestCase):
    @patch("slugcatpet.control.hotkey._IS_WIN", False)
    def test_press_release_suspend_and_apply(self):
        backend = _FakeHotkeyBackend()
        hotkeys = HotkeyFilter(backend)
        seen = []
        hotkeys.triggered.connect(seen.append)
        self.assertTrue(hotkeys.register(HK_MEOW, MOD_ALT, 0x4D))
        backend.hotkey_pressed.emit(HK_MEOW)
        self.assertEqual(seen, [HK_MEOW])
        self.assertTrue(hotkeys.is_down(HK_MEOW))
        backend.hotkey_released.emit(HK_MEOW)
        self.assertFalse(hotkeys.is_down(HK_MEOW))

        hotkeys.suspend()
        self.assertTrue(backend.suspended)
        self.assertTrue(hotkeys.owns(MOD_ALT, 0x4D))
        backend.hotkey_pressed.emit(HK_MEOW)
        self.assertEqual(seen, [HK_MEOW])

        hotkeys.resume()
        self.assertFalse(backend.suspended)
        backend.hotkey_pressed.emit(HK_MEOW)
        self.assertEqual(seen, [HK_MEOW, HK_MEOW])
        self.assertTrue(hotkeys.apply())
        self.assertEqual(backend.refreshed, 1)


if __name__ == "__main__":
    unittest.main()
