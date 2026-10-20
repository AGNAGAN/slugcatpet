"""Wayland 输入区域与本地坐标的纯逻辑回归测试。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QRegion

from slugcatpet.platform.wayland.input import set_input_region
from slugcatpet.platform.wayland.regions import interaction_region, item_rects, pet_rects


class _FakeBody:
    def __init__(self, x, y):
        self.chunk0 = SimpleNamespace(x=x, y=y)
        self.chunk1 = SimpleNamespace(x=x + 20, y=y)


class _FakeGfx:
    def __init__(self, x, y):
        self.head = SimpleNamespace(x=x, y=y)


def _pet(x=100, y=100):
    return SimpleNamespace(body=_FakeBody(x, y), gfx=_FakeGfx(x, y))


class RegionTests(unittest.TestCase):
    def test_pet_coords_are_scaled_to_overlay_pixels(self):
        rects = pet_rects(_pet(100, 100), 2.0)
        self.assertTrue(rects)
        # 头抓点 (100,100) 半径 11+7=18；缩放后应覆盖 (200,200)，而不是 (100,100)。
        self.assertTrue(any(r.contains(QPoint(200, 200)) for r in rects))
        self.assertFalse(any(r.contains(QPoint(100, 100)) for r in rects))

    def test_panel_coords_are_not_scaled(self):
        panel = SimpleNamespace(
            isVisible=lambda: True,
            geometry=lambda: QRect(10, 20, 30, 40),
        )
        region = interaction_region([_pet()], [], [panel], 2.0, 640, 480)
        self.assertTrue(region.contains(QPoint(10, 20)))
        self.assertTrue(region.contains(QPoint(39, 59)))
        self.assertFalse(region.contains(QPoint(60, 60)))  # 不在这块面板内，也不在缩放后的宠物头上

    def test_empty_region_is_outside_surface(self):
        region = interaction_region([], [], [], 2.0, 640, 480)
        self.assertEqual(region, QRegion(640, 480, 1, 1))

    def test_full_region_covers_surface(self):
        region = interaction_region([], [], [], 2.0, 640, 480, full=True)
        self.assertEqual(region, QRegion(0, 0, 640, 480))

    def test_item_pole_endpoints_are_interactive(self):
        pole = SimpleNamespace(ax=20.0, ay=30.0, bx=20.0, by=130.0)
        rects = item_rects(pole, 2.0)
        self.assertTrue(any(r.contains(QPoint(40, 60)) for r in rects))
        self.assertTrue(any(r.contains(QPoint(40, 260)) for r in rects))

    def test_set_input_region_requests_surface_commit(self):
        handle = Mock()
        handle.width.return_value = 640
        handle.height.return_value = 480
        with patch("slugcatpet.platform.wayland.input._window_handle", return_value=handle):
            ok = set_input_region(Mock(), QRegion(0, 0, 100, 100))
        self.assertTrue(ok)
        handle.setMask.assert_called_once_with(QRegion(0, 0, 100, 100))
        handle.requestUpdate.assert_called_once_with()

    def test_empty_input_region_becomes_outside_1x1(self):
        handle = Mock()
        handle.width.return_value = 640
        handle.height.return_value = 480
        with patch("slugcatpet.platform.wayland.input._window_handle", return_value=handle):
            set_input_region(Mock(), QRegion())
        handle.setMask.assert_called_once_with(QRegion(640, 480, 1, 1))
        handle.requestUpdate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
