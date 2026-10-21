"""Rain World 配乐扫描与选择性导入的纯逻辑测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slugcatpet.gameassets import (
    game_music_imported,
    game_music_names,
    is_game_install,
    remember_install,
)


def _game(root: Path) -> Path:
    songs = root / "RainWorld_Data" / "StreamingAssets" / "music" / "songs"
    songs.mkdir(parents=True)
    (songs / "RW_2 - Second.mp3").write_bytes(b"second")
    (songs / "RW_10 - Tenth.mp3").write_bytes(b"tenth")
    return root


class GameMusicTests(unittest.TestCase):
    def test_names_are_natural_sorted_and_include_bundle_only_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _game(Path(tmp))
            with patch(
                "slugcatpet.gameassets._bundle_clip_names",
                return_value={"NA_1 - Extra", "RW_10 - Tenth"},
            ):
                names = game_music_names(root)
        self.assertEqual(names, ["NA_1 - Extra", "RW_2 - Second", "RW_10 - Tenth"])

    def test_names_exclude_empty_loose_placeholder_missing_from_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _game(Path(tmp))
            (root / "RainWorld_Data/StreamingAssets/music/songs/Deprecated.mp3").write_bytes(b"")
            with patch(
                "slugcatpet.gameassets._bundle_clip_names",
                return_value={"RW_2 - Second", "RW_10 - Tenth"},
            ):
                names = game_music_names(root)
        self.assertNotIn("Deprecated", names)
        self.assertIn("RW_2 - Second", names)

    def test_game_music_imported_ignores_empty_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "Empty.mp3").write_bytes(b"")
            self.assertFalse(game_music_imported("Empty", out))
            (out / "Good.ogg").write_bytes(b"ogg")
            self.assertTrue(game_music_imported("Good", out))

    def test_extract_to_out_dir_copies_selected_track_and_skips_second_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _game(Path(tmp) / "game")
            out = Path(tmp) / "Rain World"
            progress = []
            from slugcatpet.gameassets import extract_music

            written = extract_music(
                root,
                ["RW_2 - Second"],
                out_dir=out,
                progress=lambda done, total, name: progress.append((done, total, name)),
            )
            self.assertEqual(written, ["RW_2 - Second"])
            self.assertEqual((out / "RW_2 - Second.mp3").read_bytes(), b"second")
            self.assertEqual(progress, [(1, 1, "RW_2 - Second")])
            self.assertFalse((out / ".format").exists())

            progress.clear()
            self.assertEqual(extract_music(root, ["RW_2 - Second"], out_dir=out), [])
            self.assertEqual(progress, [])

    def test_extract_falls_back_to_bundle_for_zero_byte_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _game(Path(tmp) / "game")
            (root / "RainWorld_Data/StreamingAssets/music/songs/RW_2 - Second.mp3").write_bytes(b"")
            out = Path(tmp) / "Rain World"
            from slugcatpet.gameassets import extract_music

            with (
                patch("slugcatpet.gameassets._bundle_clips", return_value={"RW_2 - Second": b"fsb"}),
                patch("slugcatpet.audio.fsbogg.fsb_to_ogg", return_value=b"ogg-data"),
            ):
                written = extract_music(root, ["RW_2 - Second"], out_dir=out)
            self.assertEqual(written, ["RW_2 - Second"])
            self.assertEqual((out / "RW_2 - Second.ogg").read_bytes(), b"ogg-data")

    def test_extract_falls_back_to_decoded_wav_for_unknown_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _game(Path(tmp) / "game")
            (root / "RainWorld_Data/StreamingAssets/music/songs/RW_2 - Second.mp3").write_bytes(b"")
            out = Path(tmp) / "Rain World"
            from slugcatpet.gameassets import extract_music

            with (
                patch("slugcatpet.gameassets._bundle_clips", return_value={"RW_2 - Second": b"fsb"}),
                patch(
                    "slugcatpet.audio.fsbogg.fsb_to_ogg",
                    side_effect=ValueError("unknown vorbis setup"),
                ),
                patch(
                    "slugcatpet.gameassets._bundle_decoded",
                    return_value={"RW_2 - Second": (".wav", b"wav-data")},
                ),
            ):
                written = extract_music(root, ["RW_2 - Second"], out_dir=out)
            self.assertEqual(written, ["RW_2 - Second"])
            self.assertEqual((out / "RW_2 - Second.wav").read_bytes(), b"wav-data")

    def test_remember_install_writes_game_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _game(Path(tmp) / "game")
            home = Path(tmp) / "home"
            with patch.dict(os.environ, {"SLUGCATPET_HOME": str(home)}):
                remember_install(root)
                saved = (home / "assets" / "game_path.txt").read_text(encoding="utf-8")
            self.assertEqual(saved, str(root.resolve()))

    def test_is_game_install_accepts_songs_or_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _game(Path(tmp))
            self.assertTrue(is_game_install(root))
            bare = Path(tmp) / "bare"
            bare.mkdir()
            self.assertFalse(is_game_install(bare))


if __name__ == "__main__":
    unittest.main()
