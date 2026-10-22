"""音乐列表按文件名自然排序的回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from slugcatpet.audio.player import scan_tracks


class MusicSortTests(unittest.TestCase):
    def test_scan_orders_numbers_naturally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("100 - end.mp3", "11 - eleven.mp3", "2 - two.mp3", "1 - one.mp3", "10 - ten.mp3"):
                (root / name).write_bytes(b"")
            names = [t.path.name for t in scan_tracks([root], recursive=False)]
        self.assertEqual(
            names,
            ["1 - one.mp3", "2 - two.mp3", "10 - ten.mp3", "11 - eleven.mp3", "100 - end.mp3"],
        )

    def test_scan_sorts_folder_names_naturally_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ("Disc 10", "Disc 2"):
                d = root / folder
                d.mkdir()
                (d / "1.mp3").write_bytes(b"")
            paths = [t.path for t in scan_tracks([root])]
        self.assertEqual([p.parent.name for p in paths], ["Disc 2", "Disc 10"])


if __name__ == "__main__":
    unittest.main()
