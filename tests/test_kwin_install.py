"""KWin 持久安装/启用的纯逻辑测试（不依赖 Plasma 会话）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from slugcatpet.platform.wayland import kwin_install


class KWinrcTests(unittest.TestCase):
    def test_insert_into_existing_plugins_section(self):
        text = "[General]\nfoo=bar\n\n[Plugins]\notherEnabled=true\n\n[Effect]\nx=1\n"
        out = kwin_install.with_plugin_enabled(text, True)
        self.assertIn("[Plugins]\notherEnabled=true\nslugcatpetEnabled=true", out)
        self.assertIn("[Effect]\nx=1", out)
        self.assertEqual(out.count(kwin_install.PLUGIN_KEY), 1)

    def test_replace_and_disable_without_duplicate(self):
        text = "[Plugins]\nslugcatpetEnabled=true\notherEnabled=true\n"
        out = kwin_install.with_plugin_enabled(text, False)
        self.assertIn("slugcatpetEnabled=false", out)
        self.assertNotIn("slugcatpetEnabled=true", out)
        self.assertEqual(out.count(kwin_install.PLUGIN_KEY), 1)
        again = kwin_install.with_plugin_enabled(out, False)
        self.assertEqual(out, again)

    def test_create_section(self):
        out = kwin_install.with_plugin_enabled("[General]\nfoo=bar", True)
        self.assertTrue(out.startswith("[General]\nfoo=bar\n"))
        self.assertIn("[Plugins]\nslugcatpetEnabled=true", out)

    def test_read_value(self):
        self.assertTrue(kwin_install.read_plugin_enabled("[Plugins]\nslugcatpetEnabled=true\n"))
        self.assertTrue(kwin_install.read_plugin_enabled("[Plugins]\nslugcatpetEnabled = 1\n"))
        self.assertFalse(kwin_install.read_plugin_enabled("[Plugins]\nslugcatpetEnabled=false\n"))
        self.assertFalse(kwin_install.read_plugin_enabled("[Other]\nslugcatpetEnabled=true\n"))
        self.assertFalse(kwin_install.read_plugin_enabled(""))


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(
            os.environ,
            {
                "XDG_DATA_HOME": str(Path(self.tmp.name) / "data"),
                "XDG_CONFIG_HOME": str(Path(self.tmp.name) / "config"),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_install_enable_and_uninstall(self):
        self.assertFalse(kwin_install.is_installed())
        self.assertTrue(kwin_install.install("// rendered script\n"))
        self.assertTrue(kwin_install.is_installed())
        self.assertEqual(kwin_install.script_path().read_text(encoding="utf-8"), "// rendered script\n")
        self.assertTrue(kwin_install.metadata_path().is_file())
        self.assertEqual(kwin_install.state(), kwin_install.IntegrationState(True, False))

        self.assertTrue(kwin_install.set_enabled(True))
        self.assertTrue(kwin_install.is_enabled())
        self.assertEqual(kwin_install.state(), kwin_install.IntegrationState(True, True))

        self.assertTrue(kwin_install.uninstall())
        self.assertFalse(kwin_install.is_installed())
        self.assertFalse(kwin_install.is_enabled())
        self.assertFalse(kwin_install.install_dir().exists())

    def test_empty_source_is_rejected(self):
        self.assertFalse(kwin_install.install("   \n"))

    def test_bundled_metadata_is_a_kwin_script_package(self):
        import json

        data = json.loads(kwin_install.bundled_metadata())
        self.assertEqual(data["KPackageStructure"], "KWin/Script")
        self.assertEqual(data["KPlugin"]["Id"], kwin_install.PLUGIN_ID)


if __name__ == "__main__":
    unittest.main()
