"""Wayland 光标写入的纯逻辑测试（不启动合成器）。"""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from PySide6.QtCore import QRect
from PySide6.QtGui import QCursor

from slugcatpet.platform.cursorfx import CursorHijack
from slugcatpet.platform.wayland.kwin_bridge import _qt_supports_pointer_warp
from slugcatpet.window import PetWindow
from slugcatpet.world.effects import EffectsMixin


class CursorHijackDriverTests(unittest.TestCase):
    def test_custom_writer_replaces_clip_and_releases(self):
        clips = []
        unclips = []
        moves = []
        busy = []
        releases = []

        hijack = CursorHijack(
            50,
            60,
            100,
            80,
            10,
            20,
            mode="hold",
            replace_cursor=True,
            clip=lambda x, y: clips.append((x, y)) or False,
            unclip=lambda: unclips.append(True),
            setpos=lambda x, y: moves.append((x, y)),
            busy_cursor=lambda: busy.append(True),
            restore_cursor=lambda: releases.append(True),
            on_release=lambda: releases.append("released"),
        )
        self.assertFalse(hijack.mock)
        self.assertEqual(busy, [True])
        self.assertTrue(hijack.update())
        self.assertEqual(clips, [(50.0, 60.0)])
        self.assertEqual(unclips, [True])
        self.assertEqual(moves, [(50.0, 60.0)])
        hijack.release()
        self.assertFalse(hijack.active)
        self.assertEqual(releases, [True, "released"])

    def test_custom_writer_keeps_internal_physical_coordinates(self):
        moves = []
        hijack = CursorHijack(
            150,
            240,
            300,
            1000,
            0,
            0,
            lock_ticks=1,
            setpos=lambda x, y: moves.append((x, y)),
            clip=lambda x, y: False,
            unclip=lambda: None,
            busy_cursor=lambda: None,
            restore_cursor=lambda: None,
        )
        self.assertTrue(hijack.update())
        hijack.release()
        self.assertEqual(moves, [(150.0, 241.6)])

    @unittest.skipIf(sys.platform == "win32", "Linux 默认没有原生光标写入")
    def test_without_writer_stays_mock_on_linux(self):
        hijack = CursorHijack(1, 2, 10, 10)
        self.assertTrue(hijack.mock)
        self.assertTrue(hijack.update())
        hijack.release()
        self.assertFalse(hijack.active)

    def test_left_or_right_click_releases_after_initial_release(self):
        state = {"down": True}
        hijack = CursorHijack(
            1,
            2,
            10,
            10,
            mode="hold",
            button_down=lambda: state["down"],
            setpos=lambda x, y: None,
            clip=lambda x, y: False,
            unclip=lambda: None,
            busy_cursor=lambda: None,
            restore_cursor=lambda: None,
        )
        # 触发劫持的点击还没松开时，不能立刻自解除。
        self.assertTrue(hijack.update())
        state["down"] = False
        self.assertTrue(hijack.update())
        state["down"] = True
        self.assertFalse(hijack.update())
        self.assertFalse(hijack.active)


class _FakeOverlay:
    def __init__(self, area, frame):
        self._area = area
        self._frame = frame

    def windowHandle(self):
        return None

    def frameGeometry(self):
        return self._frame

    def width(self):
        return self._frame.width()

    def height(self):
        return self._frame.height()


class WaylandCursorWriterTests(unittest.TestCase):
    def test_writer_divides_by_dpr(self):
        overlay = _FakeOverlay(QRect(0, 0, 1707, 1099), QRect(0, 0, 1707, 1099))
        with mock.patch.object(QCursor, "setPos") as set_pos:
            writer = EffectsMixin._wayland_cursor_writer(overlay, 1.5)
            writer(300, 450)
        point = set_pos.call_args.args[0]
        self.assertEqual((point.x(), point.y()), (200, 300))

    def test_writer_uses_overlay_local_when_qt_frame_is_zero(self):
        overlay = _FakeOverlay(QRect(0, 900, 1707, 1099), QRect(0, 0, 1707, 1099))
        with mock.patch.object(QCursor, "setPos") as set_pos:
            writer = EffectsMixin._wayland_cursor_writer(overlay, 1.5)
            writer(450, 1800)
        point = set_pos.call_args.args[0]
        self.assertEqual((point.x(), point.y()), (300, 300))

    def test_writer_adds_qt_frame_origin(self):
        overlay = _FakeOverlay(QRect(0, 900, 1707, 1099), QRect(0, 900, 1707, 1099))
        with mock.patch.object(QCursor, "setPos") as set_pos:
            writer = EffectsMixin._wayland_cursor_writer(overlay, 1.5)
            writer(450, 1800)
        point = set_pos.call_args.args[0]
        self.assertEqual((point.x(), point.y()), (300, 1200))

    def test_qt_version_gate(self):
        with mock.patch("PySide6.QtCore.qVersion", return_value="6.11.4"):
            self.assertFalse(_qt_supports_pointer_warp())
        with mock.patch("PySide6.QtCore.qVersion", return_value="6.12.0"):
            self.assertTrue(_qt_supports_pointer_warp())

    def test_window_capability_follows_backend(self):
        available = PetWindow.cursor_hijack_available.fget
        self.assertTrue(available(SimpleNamespace(_backend=SimpleNamespace(supports_cursor_write=True))))
        self.assertFalse(available(SimpleNamespace(_backend=SimpleNamespace(supports_cursor_write=False))))


if __name__ == "__main__":
    unittest.main()
