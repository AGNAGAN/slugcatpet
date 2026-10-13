"""音乐：播放列表播放器和随场景切换的游戏配乐。"""

from __future__ import annotations

from PySide6.QtCore import QLoggingCategory

from .director import MusicDirector
from .player import AUDIO_EXTS, MODE_ONE, MODE_ORDER, MODE_SHUFFLE, MusicPlayer, scan_tracks

QLoggingCategory.setFilterRules("qt.multimedia.*=false")

__all__ = [
    "MusicPlayer",
    "MusicDirector",
    "scan_tracks",
    "AUDIO_EXTS",
    "MODE_ORDER",
    "MODE_SHUFFLE",
    "MODE_ONE",
]
