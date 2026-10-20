"""Phase 4 的平台功能测试：XDG 自启和输出选择辅助。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from slugcatpet.platform import autostart
from slugcatpet.platform.appid import DESKTOP_FILE_NAME


@unittest.skipIf(sys.platform == "win32", "Linux XDG autostart")
class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_enable_disable_and_sync(self):
        self.assertFalse(autostart.is_enabled())
        self.assertTrue(autostart.set_enabled(True))
        path = Path(self.tmp.name) / "autostart" / f"{DESKTOP_FILE_NAME}.desktop"
        self.assertTrue(path.is_file())
        self.assertTrue(autostart.is_enabled())
        text = path.read_text(encoding="utf-8")
        self.assertIn("[Desktop Entry]", text)
        self.assertIn("Type=Application", text)
        self.assertIn("Icon=slugcatpet", text)
        self.assertIn("Exec=", text)

        path.write_text("[Desktop Entry]\nExec=/old/path\n", encoding="utf-8")
        autostart.sync_path()
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("Exec=/old/path", text)
        self.assertIn(f"Exec={autostart._linux_launch_command()}", text)

        self.assertTrue(autostart.set_enabled(False))
        self.assertFalse(path.exists())
        self.assertFalse(autostart.is_enabled())

    def test_exec_quoting(self):
        self.assertEqual(autostart._exec_quote("/tmp/a b"), '"/tmp/a b"')
        self.assertEqual(autostart._exec_quote('a"b'), '"a\\"b"')
        self.assertEqual(autostart._exec_quote("/tmp/100%"), '"/tmp/100%%"')

    def test_sync_without_file_is_noop(self):
        autostart.sync_path()
        self.assertFalse(autostart.is_enabled())


if __name__ == "__main__":
    unittest.main()
