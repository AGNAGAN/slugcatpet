"""场景配乐：启动和无重力时放从游戏里提取的曲子。"""

from __future__ import annotations

INTRO_TRACK = "RW_8 - Sundown"
ZEROG_TRACK = "NA_41 - Random Gods"
SCENE_TRACKS = (INTRO_TRACK, ZEROG_TRACK)
# 提取并列进「游戏配乐」的曲子，按列表顺序
GAME_TRACKS = (*SCENE_TRACKS, "RW_42 - Kayava", "RW_92 - Reclaiming Entropy")
_TITLES = {
    INTRO_TRACK: "Sundown",
    ZEROG_TRACK: "Random Gods",
    "RW_42 - Kayava": "Kayava",
    "RW_92 - Reclaiming Entropy": "Reclaiming Entropy",
}
ZEROG_GAIN = 0.4


def game_title(name: str) -> str:
    return _TITLES.get(name, name)


class MusicDirector:
    def __init__(self, player, params):
        self._player = player
        self._params = params if params is not None else {}
        self._zerog_path = None

    def play_intro(self):
        """启动时放一遍，放完就停。"""
        if self._player.muted:
            return
        track = self._player.resolve_track(INTRO_TRACK)
        if track is not None:
            self._player.play_special_track(track, loop=False, stop_after_end=True)

    def on_zerog(self, on: bool):
        if on:
            if not self._enabled("music_zerog_enabled"):
                return
            self._zerog_path = self._play(ZEROG_TRACK, ZEROG_GAIN)
        else:
            self._stop_if(self._zerog_path)
            self._zerog_path = None

    def _enabled(self, key: str) -> bool:
        return bool(self._params.get(key, True)) and not self._player.muted

    def _play(self, filename: str, gain: float):
        track = self._player.resolve_track(filename)
        if track is None:
            return None
        self._player.play_special_track(track, gain=gain, loop=True, stop_after_end=False)
        return track.path

    def _stop_if(self, path):
        """只在正放的就是这首时才停。"""
        if path is None or self._player.manual:
            return
        cur = self._player.current()
        if cur is not None and cur.path == path and self._player.is_special_active:
            self._player.stop_ambient()
