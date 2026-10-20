"""overlay 本地坐标与旧存档迁移的纯逻辑回归测试。"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QPoint, QRect

from slugcatpet.ui.overlay import clamp_local, migrate_ui_coords


class _Host:
    def __init__(self, width, height):
        self._w = width
        self._h = height

    def width(self):
        return self._w

    def height(self):
        return self._h


class OverlayCoordTests(unittest.TestCase):
    def test_clamp_local_keeps_card_inside_overlay(self):
        host = _Host(1440, 900)
        self.assertEqual(clamp_local(host, QPoint(-20, -10), 300, 200), QPoint(0, 0))
        self.assertEqual(clamp_local(host, QPoint(9999, 9999), 300, 200), QPoint(1140, 700))

    def test_migrates_global_coords_on_lower_output(self):
        overlay = QRect(0, 900, 1707, 1067)  # HDMI-A-1 在 eDP 下方
        params = {
            "hud_x": 120,
            "hud_y": 1000,
            "tab_y": 1100,
            "rain_timer": {"dial_pos": [1400, 1500]},
        }
        self.assertTrue(migrate_ui_coords(params, overlay))
        self.assertEqual((params["hud_x"], params["hud_y"]), (120, 100))
        self.assertEqual(params["tab_y"], 200)
        self.assertEqual(params["rain_timer"]["dial_pos"], [1400, 600])
        self.assertEqual(params["ui_coord_space"], "overlay")

    def test_keeps_coords_already_local_for_nonzero_origin(self):
        overlay = QRect(0, 900, 1707, 1067)
        params = {
            "hud_x": 120,
            "hud_y": 100,  # 已在上次 Phase 1 保存为本地坐标
            "tab_y": 220,
            "rain_timer": {"dial_pos": [1400, 500]},
        }
        migrate_ui_coords(params, overlay)
        self.assertEqual((params["hud_x"], params["hud_y"]), (120, 100))
        self.assertEqual(params["tab_y"], 220)
        self.assertEqual(params["rain_timer"]["dial_pos"], [1400, 500])

    def test_migration_is_idempotent(self):
        overlay = QRect(0, 900, 1707, 1067)
        params = {"hud_x": 120, "hud_y": 1000, "tab_y": 1100}
        migrate_ui_coords(params, overlay)
        before = (params["hud_x"], params["hud_y"], params["tab_y"])
        self.assertFalse(migrate_ui_coords(params, overlay))
        self.assertEqual((params["hud_x"], params["hud_y"], params["tab_y"]), before)


if __name__ == "__main__":
    unittest.main()
