"""Wayland 后端与 KWin 脚本生成的纯逻辑测试（不依赖合成器/DBus）。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from PySide6.QtCore import QRect

from slugcatpet.platform.backend import DesktopBackend
from slugcatpet.platform.wayland.kwin_bridge import WaylandKWinBackend
from slugcatpet.window import PetWindow


class _CursorBackend(DesktopBackend):
    def __init__(self, pos=None, origin=(0, 0)):
        self._pos = pos
        self._origin = origin

    def cursor_global(self):
        return self._pos

    def overlay_origin(self):
        return self._origin


class _FakeWindow:
    to_logical = PetWindow.to_logical
    cursor_logical = PetWindow.cursor_logical

    def __init__(self, backend, last=None):
        self._wayland = True
        self._backend = backend
        self._last_local_pointer = last
        self._scale = 2.0
        self._WL = 720.0
        self._HL = 450.0


class ScriptRenderTests(unittest.TestCase):
    def test_placeholders_are_replaced(self):
        backend = SimpleNamespace(
            _target_screen="eDP-1",
            _rect=QRect(0, 0, 1440, 932),
        )
        text = WaylandKWinBackend._render_script(backend)
        for token in ("@APP_ID@", "@TARGET_SCREEN@", "@OVERLAY_W@", "@DBUS_SERVICE@"):
            self.assertNotIn(token, text)
        self.assertIn('var TARGET_SCREEN = "eDP-1";', text)
        self.assertIn("var OVERLAY_W = 1440;", text)
        self.assertIn("var OVERLAY_H = 932;", text)
        self.assertIn('var SERVICE = "org.slugcatpet.Bridge";', text)


class CursorTests(unittest.TestCase):
    def test_global_cursor_is_converted_to_overlay_then_logical(self):
        backend = _CursorBackend((500, 400), (100, 100))
        win = _FakeWindow(backend)
        self.assertEqual(win.cursor_logical(), (200.0, 150.0))

    def test_cursor_outside_overlay_is_unavailable(self):
        backend = _CursorBackend((50, 50), (100, 100))
        win = _FakeWindow(backend)
        self.assertIsNone(win.cursor_logical())

    def test_last_local_pointer_is_used_without_bridge(self):
        win = _FakeWindow(_CursorBackend(None), last=(123.0, 44.0))
        self.assertEqual(win.cursor_logical(), (123.0, 44.0))


if __name__ == "__main__":
    unittest.main()
