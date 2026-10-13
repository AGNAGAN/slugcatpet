"""场景配乐：按用户配置在开屏、打开设置和各环境场景下放曲子，并提供试听。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer

INTRO_TRACK = "RW_8 - Sundown"
ZEROG_TRACK = "NA_41 - Random Gods"
# 提取并列进「游戏配乐」的曲子，按列表顺序
GAME_TRACKS = (INTRO_TRACK, ZEROG_TRACK, "RW_42 - Kayava", "RW_92 - Reclaiming Entropy")
_TITLES = {
    INTRO_TRACK: "Sundown",
    ZEROG_TRACK: "Random Gods",
    "RW_42 - Kayava": "Kayava",
    "RW_92 - Reclaiming Entropy": "Reclaiming Entropy",
}

SCENES = ("intro", "settings", "none", "blizzard", "zerog", "water")
ENV_SCENES = ("none", "blizzard", "zerog", "water")
MODE_LOOP = "loop"
MODE_ONCE = "once"
_DEFAULTS = {
    "intro": {"track": INTRO_TRACK, "mode": MODE_ONCE, "gain": 1.0},
    "zerog": {"track": ZEROG_TRACK, "mode": MODE_LOOP, "gain": 0.4},
}


def game_title(name: str) -> str:
    return _TITLES.get(name, name)


def track_title(track_id: str) -> str:
    """配置里的曲目标识（游戏配乐主名或文件路径）转成显示名。"""
    return game_title(Path(track_id).stem)


def scene_music(params: dict) -> dict:
    """读出 6 个场景的配置 {scene: {track, mode, gain}}，缺省项补默认。"""
    saved = params.get("scene_music")
    if not isinstance(saved, dict):
        saved = {}
        if not params.get("music_zerog_enabled", True):
            saved["zerog"] = {"track": None}
    out = {}
    for scene in SCENES:
        cfg = dict(_DEFAULTS.get(scene, {"track": None, "mode": MODE_ONCE, "gain": 1.0}))
        got = saved.get(scene)
        if isinstance(got, dict):
            track = got.get("track", cfg["track"])
            cfg["track"] = track if isinstance(track, str) and track else None
            if got.get("mode") in (MODE_LOOP, MODE_ONCE):
                cfg["mode"] = got["mode"]
            try:
                cfg["gain"] = max(0.0, min(1.0, float(got.get("gain", cfg["gain"]))))
            except (TypeError, ValueError):
                pass
        if scene == "intro":
            cfg["mode"] = MODE_ONCE
        out[scene] = cfg
    return out


class MusicDirector:
    """当前场景 = 设置窗开着且配了曲子时为 settings，否则为环境场景；开屏只在启动时。"""

    def __init__(self, player, params):
        self._player = player
        self._params = params if params is not None else {}
        self._cfg = scene_music(self._params)
        self._env = "none"
        self._settings_open = False
        self._at = "none"  # 已结算到的场景
        self._settle_pending = False
        self._intro = False  # 开屏曲正在放
        self._scene = None  # 自己放着的曲子属于哪个场景
        self._path = None  # 自己放着的曲子
        self._preview = None  # 试听中的曲子路径
        self._previewed = False  # 这次弹窗里试听过，结束时要恢复场景曲
        player.played_once.connect(self._on_played_once)

    @property
    def config(self) -> dict:
        return {k: dict(v) for k, v in self._cfg.items()}

    def set_config(self, cfg: dict):
        """保存新配置；当前场景的曲子没换就只调音量，换了按新配置重新放。"""
        self._release_preview()
        old = self._cfg[self._at]
        self._params["scene_music"] = {k: dict(v) for k, v in cfg.items()}
        self._params.pop("music_zerog_enabled", None)
        self._cfg = scene_music(self._params)
        if self._active() != self._at:
            self._switch(enter=True)
            return
        if self._intro:
            return
        new = self._cfg[self._at]
        same = (old["track"], old["mode"]) == (new["track"], new["mode"])
        if same and self._scene == self._at and self._owns_current():
            self._player.set_gain(new["gain"])
            return
        self._apply(enter=False, restart=True)

    def resolve(self, track_id):
        """曲目标识 → Track；文件丢失返回 None。"""
        if not track_id:
            return None
        p = Path(track_id)
        if p.is_absolute():
            try:
                if p.is_file():
                    from .player import Track

                    return Track(p)
            except OSError:
                pass
            return None
        return self._player.resolve_track(track_id)

    def start(self, env: str):
        """启动：先放开屏曲，放完再进环境场景（环境的「一次」不补放）。"""
        self._env = env if env in ENV_SCENES else "none"
        self._at = self._active()
        cfg = self._cfg["intro"]
        if self._can_play() and self._play(cfg, "intro", once=True):
            self._intro = True
            return
        self._apply(enter=False)

    def on_env(self, kind: str, on: bool):
        """环境切换是先关旧的再开新的，下一拍再结算，免得中间闪过「无环境」。"""
        if kind not in ENV_SCENES:
            return
        if on:
            self._env = kind
        elif kind == self._env:
            self._env = "none"
        if not self._settle_pending:
            self._settle_pending = True
            QTimer.singleShot(0, self._settle_env)

    def _settle_env(self):
        self._settle_pending = False
        self._switch(enter=True)

    def on_settings(self, visible: bool):
        if visible != self._settings_open:
            self._settings_open = visible
            self._switch(enter=visible)

    def _switch(self, enter: bool):
        if self._active() == self._at:
            return
        self._at = self._active()
        self._intro = False
        self._apply(enter=enter)

    def _active(self) -> str:
        if self._settings_open and self._cfg["settings"]["track"]:
            return "settings"
        return self._env

    def _apply(self, enter: bool, restart: bool = False):
        """切到当前场景：enter 为真才放「一次」的曲子；本场景的曲子已在放则不重来。"""
        if self._preview is not None:
            return
        scene = self._active()
        cfg = self._cfg[scene]
        playing_own = self._owns_current()
        if scene == self._scene and playing_own and not restart:
            return
        want = cfg["track"] and (cfg["mode"] == MODE_LOOP or enter) and self._can_play()
        if want and self._play(cfg, scene, once=cfg["mode"] == MODE_ONCE):
            return
        if playing_own:
            self._stop_own()

    def _can_play(self) -> bool:
        """静音或用户自己在放歌时不插入场景曲。"""
        p = self._player
        if p.muted:
            return False
        if self._owns_current():
            return True
        return not (p.manual or (p.is_playing() and not p.is_special_active))

    def _owns_current(self) -> bool:
        p = self._player
        if self._path is None or p.manual or not p.is_special_active:
            return False
        cur = p.current()
        return cur is not None and str(cur.path) == self._path

    def _play(self, cfg, scene, once: bool) -> bool:
        track = self.resolve(cfg["track"])
        if track is None:
            return False
        self._player.play_special_track(track, gain=cfg["gain"], loop=not once, stop_after_end=once)
        self._scene = scene
        self._path = str(track.path)
        return True

    def _stop_own(self):
        self._player.stop_ambient()
        self._scene = None
        self._path = None

    def _on_played_once(self):
        if self._preview is not None:
            self._preview = None
            return
        self._scene = None
        self._path = None
        if self._intro:
            self._intro = False
            self._apply(enter=False)

    # 试听：临时顶掉当前声音，结束后按当前场景重新判断
    def preview(self, track_id, gain: float) -> bool:
        track = self.resolve(track_id)
        if track is None:
            return False
        self._intro = False
        self._scene = None
        self._path = None
        self._player.play_special_track(track, gain=gain, loop=False, stop_after_end=True)
        self._preview = str(track.path)
        self._previewed = True
        return True

    def preview_active(self) -> bool:
        p = self._player
        cur = p.current()
        return self._preview is not None and cur is not None and str(cur.path) == self._preview

    def preview_playing(self) -> bool:
        return self.preview_active() and self._player.is_playing()

    def pause_preview(self):
        if self.preview_active():
            self._player.pause()

    def resume_preview(self):
        if self.preview_active():
            self._player.play()

    def set_preview_gain(self, gain: float):
        if self.preview_active():
            self._player.set_gain(gain)

    def stop_preview(self):
        """停掉试听，场景曲等 end_preview 再恢复。"""
        if self.preview_active():
            self._player.stop_ambient()
        self._preview = None

    def end_preview(self):
        """结束试听并按当前场景恢复配乐。"""
        if self._release_preview():
            self._apply(enter=False)

    def _release_preview(self) -> bool:
        """把还在的试听曲当成自己放的，交给 _apply 直接替换或停掉；返回这次是否试听过。"""
        if self.preview_active():
            self._path = self._preview
            self._scene = None
        self._preview = None
        used, self._previewed = self._previewed, False
        return used
