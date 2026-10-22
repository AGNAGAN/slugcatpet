"""音乐播放：扫描目录、封装 QMediaPlayer，支持顺序、随机、单曲循环。"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

AUDIO_EXTS = (
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".m4a",
    ".aac",
    ".wma",
    ".opus",
    ".aiff",
    ".aif",
)

MODE_ORDER = "order"
MODE_SHUFFLE = "shuffle"
MODE_ONE = "one"

_MODES = (MODE_ORDER, MODE_SHUFFLE, MODE_ONE)

_FADE_MS = 350
_FADE_TICK_MS = 20


@dataclass(slots=True)
class Track:
    path: Path

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def folder(self) -> str:
        return self.path.parent.name


def _natural_key(text: str) -> tuple[tuple[int, int | str], ...]:
    """自然排序键：数字段按整数比较，文本段按大小写不敏感比较。"""
    return tuple(
        (0, int(part)) if part.isascii() and part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", text)
    )


def _track_sort_key(track: Track):
    """先按目录、再按文件名自然排序；名称完全相同时用完整路径兜底。"""
    return (
        _natural_key(str(track.path.parent)),
        _natural_key(track.path.name),
        track.path.name.casefold(),
        str(track.path),
    )


def _norm(path) -> str:
    """规范化的小写路径，用于去重和比对隐藏曲目。"""
    try:
        return str(Path(path).resolve()).lower()
    except (TypeError, OSError):
        return str(path).lower()


def scan_tracks(dirs, recursive: bool = True) -> list[Track]:
    found: dict[str, Path] = {}
    for d in dirs:
        try:
            root = Path(d)
        except TypeError:
            continue
        if not root.is_dir():
            continue
        it = root.rglob("*") if recursive else root.glob("*")
        for p in it:
            try:
                if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
                    found[_norm(p)] = p
            except OSError:
                continue
    tracks = [Track(p) for p in found.values()]
    tracks.sort(key=_track_sort_key)
    return tracks


def fmt_time(ms: int) -> str:
    ms = max(0, int(ms))
    sec = ms // 1000
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _load_media_classes():
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    return QMediaPlayer, QAudioOutput


def _quiet_ffmpeg():
    """媒体后端自带的 FFmpeg 不往控制台打日志。"""
    import ctypes
    import PySide6

    for f in Path(PySide6.__file__).parent.glob("avutil-*.dll"):
        try:
            ctypes.CDLL(str(f)).av_log_set_level(8)  # AV_LOG_FATAL
        except (OSError, AttributeError):
            pass


class MusicPlayer(QObject):
    """volume 为用户音量 0..100，gain 为每曲乘数 0..1；输出 = 静音 ? 0 : volume/100 * gain。"""

    track_changed = Signal(object)  # 当前曲目（Track 或 None）
    playing_changed = Signal(bool)
    mode_changed = Signal(str)
    volume_changed = Signal(int)  # 音量 0..100
    mute_changed = Signal(bool)
    list_changed = Signal()
    position_changed = Signal(int, int)  # 当前位置/总长（毫秒）
    failed = Signal(str)  # 播放出错（曲目路径）
    played_once = Signal()

    def __init__(self, params: dict | None = None, on_change=None, theme_dirs=(), parent=None):
        super().__init__(parent)
        self._params = params if params is not None else {}
        self._theme_dirs = list(theme_dirs)  # 只用来找场景曲的目录，不进列表
        self._on_change = on_change
        self._tracks: list[Track] = []
        # 用户移出列表的曲目，重扫时跳过
        self._hidden: set[str] = {p for p in (self._params.get("music_hidden") or []) if isinstance(p, str)}
        # 用户导入的路径，重扫时据此重建列表
        self._sources: list[Path] = [
            Path(p) for p in (self._params.get("music_sources") or []) if isinstance(p, str)
        ]
        self._index = -1
        self._mode = self._params.get("music_mode", MODE_ORDER)
        if self._mode not in _MODES:
            self._mode = MODE_ORDER
        self._volume = int(self._params.get("music_volume", 70))
        self._volume = max(0, min(100, self._volume))
        self._gain = 1.0
        self._mute = bool(self._params.get("mute_all", False))
        self._order: list[int] = []  # 随机模式的播放次序（索引）
        self._available = True
        self._stop_after_end = False
        self._loop_current = False
        self._special_track: Track | None = None  # 当前特供曲，可以不在列表里
        self._manual = False  # 当前特供曲是用户在「游戏配乐」里点播的
        self._resume_ms = 0  # 恢复的播放位置，play 时应用一次
        self._pending_seek = None  # 媒体载入后要跳到的位置（ms）
        self._fade = 1.0
        self._fade_target = 1.0
        self._fade_done = None
        self._switch = None  # 切歌渐弱结束后执行的切换
        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(_FADE_TICK_MS)
        self._fade_timer.timeout.connect(self._fade_step)
        try:
            QMediaPlayer, QAudioOutput = _load_media_classes()
            self._out = QAudioOutput()
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._out)
            _quiet_ffmpeg()
        except Exception:
            self._available = False
            self._out = None
            self._player = None
        self._apply_output_volume()
        if self._player is not None:
            self._player.mediaStatusChanged.connect(self._on_status)
            self._player.playbackStateChanged.connect(self._on_playback_state)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.errorOccurred.connect(self._on_error)
        self._last_duration = 0

    @property
    def available(self) -> bool:
        return self._available

    @property
    def tracks(self) -> list[Track]:
        return self._tracks

    @property
    def index(self) -> int:
        return self._index

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def gain(self) -> float:
        return self._gain

    @property
    def muted(self) -> bool:
        return self._mute

    @property
    def looping(self) -> bool:
        return self._loop_current

    @property
    def is_special_active(self) -> bool:
        """是否在放特供曲，含播完即停但还没收尾的。"""
        return self._special_track is not None or self._loop_current or self._stop_after_end

    @property
    def manual(self) -> bool:
        return self._manual and self._special_track is not None

    def current(self) -> Track | None:
        if self._special_track is not None:
            return self._special_track  # 特供曲优先于列表选中
        if 0 <= self._index < len(self._tracks):
            return self._tracks[self._index]
        return None

    def is_playing(self) -> bool:
        if self._player is None:
            return False
        from PySide6.QtMultimedia import QMediaPlayer

        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def position(self) -> int:
        """当前播放位置（毫秒）。"""
        if self._player is None:
            return 0
        return int(self._player.position())

    def find(self, filename: str) -> int | None:
        target = Path(filename).name.lower()
        for i, t in enumerate(self._tracks):
            if t.path.name.lower() == target:
                return i
        return None

    def resolve_track(self, filename: str) -> Track | None:
        """按文件名找场景曲（不带扩展名时按主名匹配）：先找列表，再找导入来源、音乐目录和场景曲目录。"""
        name = Path(filename).name.lower()

        def hit(p: Path) -> bool:
            return (p.stem if name == Path(name).stem else p.name).lower() == name

        for t in self._tracks:
            if hit(t.path):
                return t
        from .._paths import user_music_dir

        seen: set[str] = set()
        for root in [*self._sources, user_music_dir(), *self._theme_dirs]:
            key = _norm(root)
            if key in seen:
                continue
            seen.add(key)
            try:
                rp = Path(root)
                if rp.is_file():
                    if hit(rp) and rp.stat().st_size > 0:
                        return Track(rp)
                elif rp.is_dir():
                    for f in rp.glob("*"):
                        try:
                            if hit(f) and f.is_file() and f.stat().st_size > 0:
                                return Track(f)
                        except OSError:
                            continue
            except OSError:
                continue
        return None

    def game_tracks(self) -> list[Track]:
        """从游戏提取的曲子，按固定顺序，只含存在且非空的文件。"""
        from .director import GAME_TRACKS

        out = []
        for name in GAME_TRACKS:
            for d in self._theme_dirs:
                f = Path(d) / f"{name}.ogg"
                try:
                    if f.is_file() and f.stat().st_size > 0:
                        out.append(Track(f))
                        break
                except OSError:
                    continue
        return out

    def play_game_track(self, track: Track):
        """点播一首游戏配乐：之后按播放模式在游戏配乐之间切换，不混进自己的歌。"""
        self._start_track(track, 1.0, False, False)
        self._manual = True

    def restore_state(self, path, position_ms: int = 0):
        """恢复上次选中的曲目和进度，不自动播放。"""
        if not path:
            return
        key = _norm(path)
        for i, t in enumerate(self._tracks):
            if _norm(t.path) == key:
                self._index = i
                self._resume_ms = max(0, int(position_ms))
                self._select(i)
                return

    @property
    def hidden(self) -> list[str]:
        return sorted(self._hidden)

    @property
    def sources(self) -> list[str]:
        return [str(p) for p in self._sources]

    def add_paths(self, paths, record: bool = True) -> int:
        """加入文件或目录，返回加进来的曲目数；record 为真时记下来源供重扫。"""
        files: list[Path] = []
        dirs: list[Path] = []
        for p in paths:
            try:
                pp = Path(p)
            except TypeError:
                continue
            if pp.is_dir():
                dirs.append(pp)
            elif pp.is_file():
                files.append(pp)
        if record:
            known = {_norm(p) for p in self._sources}
            for d in dirs + files:
                if _norm(d) not in known:
                    known.add(_norm(d))
                    self._sources.append(d)
        existing = {_norm(t.path) for t in self._tracks}
        added = 0
        for t in scan_tracks(dirs):
            key = _norm(t.path)
            if key not in existing and key not in self._hidden:
                existing.add(key)
                self._tracks.append(t)
                added += 1
        for f in files:
            if f.suffix.lower() not in AUDIO_EXTS:
                continue
            key = _norm(f)
            if key not in existing and key not in self._hidden:
                existing.add(key)
                self._tracks.append(Track(f))
                added += 1
        if added:
            self._tracks.sort(key=_track_sort_key)
            self._index = self._reindex_after_sort()
            self._rebuild_order()
            self.list_changed.emit()
            self._changed()
        return added

    def load_dirs(self, dirs) -> int:
        self._tracks = scan_tracks(dirs)
        self._index = 0 if self._tracks else -1
        self._rebuild_order()
        self.list_changed.emit()
        self.track_changed.emit(self.current())
        self._changed()
        return len(self._tracks)

    def remove_index(self, i: int):
        """移出列表，不删文件；正在放的会停下。"""
        if not (0 <= i < len(self._tracks)):
            return
        cur = self.current()
        removed = self._tracks.pop(i)
        self._hidden.add(_norm(removed.path))
        if removed is cur:
            self.stop()
            self._special_track = None
        elif i < self._index:
            self._index -= 1
        self._index = min(self._index, len(self._tracks) - 1)
        self._rebuild_order()
        self.list_changed.emit()
        self.track_changed.emit(self.current())
        self._changed()

    def rescan(self) -> int:
        """重扫导入来源与音乐目录：新文件加进来，删掉的文件去掉，移出列表的不回来。"""
        from .._paths import user_music_dir

        dirs: list[Path] = []
        files: list[Path] = []
        seen: set[str] = set()
        for p in [*self._sources, user_music_dir()]:
            key = _norm(p)
            if key in seen:
                continue
            seen.add(key)
            try:
                if p.is_dir():
                    dirs.append(p)
                elif p.is_file():
                    files.append(p)
            except OSError:
                continue
        found = scan_tracks(dirs)
        for f in files:
            if f.suffix.lower() in AUDIO_EXTS:
                found.append(Track(f))
        kept = [t for t in found if _norm(t.path) not in self._hidden]
        kept.sort(key=_track_sort_key)
        cur = self.current()
        cur_key = _norm(cur.path) if cur is not None else None
        self._tracks = kept
        if cur_key is not None:
            self._index = next(
                (i for i, t in enumerate(kept) if _norm(t.path) == cur_key),
                -1,
            )
        else:
            self._index = -1
        if self._player is not None and cur_key is not None and self._index < 0:
            self.stop()
        self._rebuild_order()
        self.list_changed.emit()
        self._changed()
        return len(kept)

    def set_index(self, i: int, autoplay: bool = True):
        """选中第 i 首，autoplay 时播放；算用户操作，清掉特供曲。"""
        if not (0 <= i < len(self._tracks)):
            return
        self._clear_special()
        if autoplay:
            self._start_track(self._tracks[i], 1.0, False, False, list_index=i)
        else:
            self._select(i)

    def play(self):
        """播放当前曲目；无选中则从首曲开始，自己的列表为空时放游戏配乐。"""
        if self._player is None:
            return
        if self._special_track is not None:
            self._resume()
            return
        if not self._tracks:
            games = self.game_tracks()
            if games:
                self.play_game_track(games[0])
            return
        if self._index < 0:
            self._index = self._shuffle_first() if self._mode == MODE_SHUFFLE else 0
        cur = QUrl.fromLocalFile(str(self._tracks[self._index].path))
        if self._player.source() != cur:
            self._select(self._index)
        if self._resume_ms:
            pos = self._resume_ms
            self._resume_ms = 0
            self._player.setPosition(pos)  # 已就绪直接定位
            self._pending_seek = pos  # 未就绪则媒体载入后补定位
        self._resume()

    def _resume(self):
        if self.is_playing():
            self._start_fade(1.0)  # 正在渐弱暂停时拉回
        else:
            self._set_full_volume()
        self._player.play()

    def pause(self):
        if self._player is None:
            return
        if self._finish_switch():
            self._player.pause()
            return
        if self.is_playing():
            self._start_fade(0.0, self._player.pause)
        else:
            self._player.pause()

    def toggle(self):
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self):
        if self._player is None:
            return
        if self._finish_switch():
            self._player.stop()
            return
        if self.is_playing():
            self._start_fade(0.0, self._player.stop)
        else:
            self._player.stop()

    def next(self):
        self._step(1)

    def prev(self):
        """上一首；正在播放且超过 3 秒时先回到开头。"""
        if self._player is not None and self.is_playing() and self._player.position() > 3000:
            self._player.setPosition(0)
            return
        self._step(-1)

    def _step(self, step: int):
        """用户切歌：在正放的那组里走；没在放游戏配乐、自己的列表又为空时走游戏配乐。"""
        if self.manual or (not self._tracks and self.game_tracks()):
            self._advance_game(step, user=True)
            return
        if not self._tracks:
            return
        self._clear_special()
        self._advance(step, user=True)

    def seek(self, ms: int):
        if self._player is not None:
            self._player.setPosition(max(0, int(ms)))

    def relative_seek(self, delta_ms: int):
        """进度偏移 delta_ms 毫秒，限制在 0 到总时长之间。"""
        if self._player is None:
            return
        target = self._player.position() + int(delta_ms)
        target = max(0, target)
        if self._last_duration > 0:
            target = min(target, self._last_duration)
        self._player.setPosition(target)

    def set_mode(self, mode: str):
        if mode not in _MODES or mode == self._mode:
            return
        self._mode = mode
        self._rebuild_order()
        self.mode_changed.emit(mode)
        self._changed()

    def cycle_mode(self) -> str:
        order = (MODE_ORDER, MODE_SHUFFLE, MODE_ONE)
        cur = order.index(self._mode) if self._mode in order else 0
        nxt = order[(cur + 1) % len(order)]
        self.set_mode(nxt)
        return nxt

    def set_volume(self, v: int):
        v = max(0, min(100, int(v)))
        if v == self._volume:
            return
        self._volume = v
        self._apply_output_volume()
        self.volume_changed.emit(v)
        self._changed()

    def set_gain(self, g: float):
        """设当前曲目的音量乘数 0..1，不存盘，换曲时复原。"""
        g = max(0.0, min(1.0, float(g)))
        if abs(g - self._gain) < 1e-6:
            return
        self._rescale_fade(self._gain, g)
        self._gain = g
        self._apply_output_volume()

    def set_mute(self, on: bool):
        on = bool(on)
        if on == self._mute:
            return
        self._mute = on
        self._apply_output_volume()
        self.mute_changed.emit(on)
        self._changed()

    def play_special_track(
        self,
        track,
        gain: float = 1.0,
        loop: bool = True,
        stop_after_end: bool = False,
    ):
        """播放特供曲，不改列表选中。"""
        if not isinstance(track, Track):
            track = Track(Path(track))
        self._start_track(track, gain, loop, stop_after_end)
        return track

    def stop_ambient(self):
        self._clear_special()
        self.stop()

    def _start_track(
        self,
        track: Track,
        gain: float,
        loop_current: bool,
        stop_after_end: bool,
        list_index: int | None = None,
    ):
        """切到 track：list_index 为 None 时作为特供曲，否则作为列表第 list_index 首。"""
        if track is None:
            return
        self._manual = False
        self._loop_current = loop_current
        self._stop_after_end = stop_after_end
        was_playing = self.is_playing()

        def do_switch():
            self._switch = None
            if list_index is None:
                self._special_track = track
            else:
                self._special_track = None
                self._index = list_index
            new_gain = max(0.0, min(1.0, float(gain)))
            self._rescale_fade(self._gain, new_gain)
            self._gain = new_gain
            if self._player is not None:
                url = QUrl.fromLocalFile(str(track.path))
                same = self._player.source() == url
                self._pending_seek = None
                if not same:
                    self._player.setSource(url)
                self._player.setPosition(0)
                self._player.play()
            self.track_changed.emit(self.current())
            self._apply_output_volume()
            self._start_fade(1.0)

        if self._player is not None and was_playing:
            self._switch = do_switch
            self._start_fade(0.0, do_switch)
        else:
            self._set_full_volume()
            do_switch()

    def _finish_switch(self) -> bool:
        """切歌渐变中途被暂停 / 停止：先把曲目切过去，再按原操作处理。"""
        if self._switch is None:
            return False
        self._switch()
        self._set_full_volume()
        return True

    def _set_full_volume(self):
        self._fade_timer.stop()
        self._fade = self._fade_target = 1.0
        self._fade_done = None
        self._apply_output_volume()

    def _start_fade(self, target: float, done=None):
        self._fade_target = max(0.0, min(1.0, target))
        self._fade_done = done
        if abs(self._fade - self._fade_target) < 1e-3:
            self._fade = self._fade_target
            self._fade_done = None
            self._apply_output_volume()
            if done is not None:
                done()
            return
        self._fade_timer.start(_FADE_TICK_MS)

    def _fade_step(self):
        target = self._fade_target
        step = _FADE_TICK_MS / float(_FADE_MS)
        if self._fade < target:
            self._fade = min(target, self._fade + step)
        elif self._fade > target:
            self._fade = max(target, self._fade - step)
        if abs(self._fade - target) < 1e-3:
            self._fade = target
            self._fade_timer.stop()
            done = self._fade_done
            self._fade_done = None
            self._apply_output_volume()
            if done is not None:
                done()
        else:
            self._apply_output_volume()

    def _select(self, i: int):
        """切换音源和选中索引并通知，不改播放状态，清掉特供曲。"""
        self._index = i
        self._special_track = None
        track = self.current()
        if self._player is not None and track is not None:
            self._player.setSource(QUrl.fromLocalFile(str(track.path)))
        self.track_changed.emit(track)

    def _clear_special(self):
        self._stop_after_end = False
        self._loop_current = False
        self._special_track = None
        self._manual = False
        if self._gain != 1.0:
            # 先换算渐变系数再复原增益，免得音量跳变
            self._rescale_fade(self._gain, 1.0)
            self._gain = 1.0
            self._apply_output_volume()

    def _rescale_fade(self, old_gain: float, new_gain: float):
        """换增益时按 fade * old_gain / new_gain 调整渐变系数，保持输出音量连续。"""
        if self._fade > 1e-3 and old_gain > 0 and new_gain > 0:
            self._fade = min(1.0, self._fade * old_gain / new_gain)

    def _apply_output_volume(self):
        if self._out is None:
            return
        if self._mute:
            v = 0.0
        else:
            v = (self._volume / 100.0) * self._gain * self._fade
        self._out.setVolume(max(0.0, min(1.0, v)))

    def _rebuild_order(self):
        """重建随机播放次序，保留当前曲目为起点。"""
        n = len(self._tracks)
        idx = list(range(n))
        random.shuffle(idx)
        if 0 <= self._index < n:
            idx.remove(self._index)
            idx.insert(0, self._index)
        self._order = idx

    def _shuffle_first(self) -> int:
        if self._order:
            return self._order[0]
        return 0

    def _advance(self, step: int, user: bool = False):
        """按模式推进 step 首并播放；顺序播放到头后回到第一首。"""
        n = len(self._tracks)
        if n == 0:
            return
        if self._mode == MODE_ONE and not user:
            self.set_index(self._index, autoplay=True)
            return
        if self._mode == MODE_SHUFFLE:
            if not self._order:
                self._rebuild_order()
            try:
                pos = self._order.index(self._index)
            except ValueError:
                pos = 0
            pos = (pos + step) % n
            self.set_index(self._order[pos], autoplay=True)
            return
        self.set_index((self._index + step) % n, autoplay=True)

    def _advance_game(self, step: int, user: bool = False):
        games = self.game_tracks()
        if not games:
            return
        cur = self._special_track if self.manual else None
        i = next((k for k, g in enumerate(games) if cur is not None and g.path == cur.path), -1)
        if i < 0:
            i = 0 if step > 0 else len(games) - 1
        elif self._mode == MODE_ONE and not user:
            pass
        elif self._mode == MODE_SHUFFLE and len(games) > 1:
            i = random.choice([k for k in range(len(games)) if k != i])
        else:
            i = (i + step) % len(games)
        self.play_game_track(games[i])

    def _reindex_after_sort(self) -> int:
        cur = self.current()
        if cur is None:
            return -1
        for i, t in enumerate(self._tracks):
            if t.path == cur.path:
                return i
        return min(self._index, len(self._tracks) - 1)

    def _apply_seek(self, ms: int):
        if self._player is None:
            return
        self._player.setPosition(max(0, int(ms)))

    def _changed(self):
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                pass

    def _on_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer

        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            if self._pending_seek is not None:
                # 媒体就绪前定位会被忽略，就绪后再延后一拍
                pos = self._pending_seek
                self._pending_seek = None
                QTimer.singleShot(60, lambda p=pos: self._apply_seek(p))
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._loop_current:
            self._player.setPosition(0)
            self._player.play()
        elif self._stop_after_end:
            self.stop()
            self._clear_special()
            self.playing_changed.emit(False)
            self.played_once.emit()
        elif self._mode == MODE_ONE:
            self._player.setPosition(0)
            self._player.play()
        elif self.manual:
            self._advance_game(1)
        else:
            self._advance(1, user=False)

    def _on_playback_state(self, state):
        from PySide6.QtMultimedia import QMediaPlayer

        self.playing_changed.emit(state == QMediaPlayer.PlaybackState.PlayingState)

    def _on_position(self, pos):
        self.position_changed.emit(int(pos), int(self._last_duration))

    def _on_duration(self, dur):
        self._last_duration = dur
        self.position_changed.emit(int(self._player.position()), int(dur))

    def _on_error(self, *_args):
        track = self.current()
        if track is not None:
            self.failed.emit(str(track.path))
