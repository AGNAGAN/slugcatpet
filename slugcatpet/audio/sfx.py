"""音效混音器：原版 room.PlaySound 的等价。

音量按 VirtualMicrophone.SetVolume 的公式；混音用自己的 QAudioSink 拉取式混音器，所以音高连续可调、同一片段可任意重叠、按 x 位置左右声道平衡。
各处的声音表（照原版 sounds.txt）用 Bank 包成可播放的一组。
"""

from __future__ import annotations

import queue
import random
import threading
import time
import wave

import numpy as np

# 原版 SoundLoader：Volume（AudioListener.volume）、Volume exponent；Options 默认 soundEffectsVolume
LISTENER_VOLUME = 6.0
VOLUME_EXPONENT = 1.8
EFFECTS_VOLUME = 0.8
MAX_VOICES = 16
UPKEEP_S = 0.15  # 约 6 个模拟 tick 没续命就停
PAN_RANGE = 0.6  # 原版声像铺满 -1..1；桌面屏幕很宽，收窄免得贴边时一侧全无声
SPECTRUM_WINDOW = 128  # GetSpectrumData(64 个采样) 对应的 FFT 窗口
SPECTRUM_BINS = 64

_rng = random.Random()
_lock = threading.RLock()
_muted = False


def _default_width() -> float:
    return 1920.0


_listener_width = _default_width


def set_muted(muted: bool) -> None:
    global _muted
    _muted = bool(muted)
    if _mix:
        _mix.clear()
        _mix.set_running(not _muted)


def is_muted() -> bool:
    return _muted


def set_listener_width(provider) -> None:
    """provider() 返回房间宽度（px），用来把 x 坐标换成声像。"""
    global _listener_width
    _listener_width = provider


class _Clip:
    def __init__(self, path):
        with wave.open(str(path), "rb") as w:
            ch, sw, self.rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
        if sw != 2:
            raise ValueError("仅支持 16 位 PCM")
        d = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        d = d.reshape(-1, ch)
        if ch == 1:
            d = np.repeat(d, 2, axis=1)
        elif ch > 2:
            d = d[:, :2]
        self.frames = d.shape[0]
        self.data = np.concatenate([d, np.zeros((2, 2), np.float32)])  # 末尾补零，插值取 i+1 不越界
        self.mono = d.mean(axis=1)


_clips: dict[str, _Clip] = {}  # 按文件路径
_failed: dict[str, float] = {}
_inflight: set[str] = set()
_queue: "queue.Queue[str]" = queue.Queue()
_loader_thread: threading.Thread | None = None
RETRY_S = 3.0


def _load(path: str):
    try:
        c = _clips[path] = _Clip(path)
    except Exception:
        _failed[path] = time.monotonic()
        return None
    _failed.pop(path, None)
    return c


def _loader() -> None:
    while True:
        path = _queue.get()
        try:
            _load(path)
        finally:
            _inflight.discard(path)


def _request(path: str) -> None:
    global _loader_thread
    if path in _inflight:
        return
    t = _failed.get(path)
    if t is not None and time.monotonic() - t < RETRY_S:
        return
    _inflight.add(path)
    if _loader_thread is None:
        _loader_thread = threading.Thread(target=_loader, name="sfx-loader", daemon=True)
        _loader_thread.start()
    _queue.put(path)


def _blackman_harris(n: int):
    k = np.arange(n)
    a = (0.35875, 0.48829, 0.14128, 0.01168)
    w = (
        a[0]
        - a[1] * np.cos(2 * np.pi * k / (n - 1))
        + a[2] * np.cos(4 * np.pi * k / (n - 1))
        - a[3] * np.cos(6 * np.pi * k / (n - 1))
    )
    return w.astype(np.float32)


_WINDOW = _blackman_harris(SPECTRUM_WINDOW)


class _Part:
    """一条正在播的指令：片段 + 触发器抽出的音量 / 音高。"""

    __slots__ = ("clip", "vol", "pitch", "pos", "gain", "vpos")

    def __init__(self, clip, vol, pitch):
        self.clip = clip
        self.vol = vol
        self.pitch = pitch
        self.pos = 0.0  # 混音器的读位置（片段帧）
        self.gain = None  # 上一块的增益，用于块内渐变
        self.vpos = 0.0  # 可视化用的虚拟播放位置（不依赖声卡）


class Handle:
    """room.PlaySound 返回的 ChunkSoundEmitter：volume / pitch 可随时改，stop() 停掉。"""

    def __init__(self, parts, vol, pitch, pan, loop=False, upkeep=False):
        self.parts = parts
        self.loop = loop
        self.upkeep = upkeep
        self._touch = time.perf_counter()
        self._vol = vol
        self._pitch = pitch
        self.pan = pan
        self.stopped = False
        self._t = time.perf_counter()

    def _advance(self):
        now = time.perf_counter()
        dt, self._t = now - self._t, now
        for p in self.parts:
            p.vpos += dt * self._pitch * p.pitch * p.clip.rate

    @property
    def volume(self) -> float:
        return self._vol

    @volume.setter
    def volume(self, v: float) -> None:
        self._vol = v

    @property
    def pitch(self) -> float:
        return self._pitch

    @pitch.setter
    def pitch(self, v: float) -> None:
        self._advance()
        self._pitch = v

    def set_pos(self, pos) -> None:
        self.pan = _pan(pos)

    def _expired(self) -> bool:
        """requireActiveUpkeep：超过 UPKEEP_S 没人续命就算停了。"""
        if self.upkeep and time.perf_counter() - self._touch > UPKEEP_S:
            self.stopped = True
        return self.stopped

    @property
    def alive(self) -> bool:
        """原版 slatedForDeletetion 取反：被停掉、没续命或（非循环）片段播完都算结束。"""
        if self._expired():
            return False
        self._advance()
        return self.loop or any(p.vpos < p.clip.frames for p in self.parts)

    @alive.setter
    def alive(self, v: bool) -> None:
        """原版 emitter.alive：每 tick 置 True 续命（upkeep=True 时必须），置 False 立即停。"""
        if v:
            self._touch = time.perf_counter()
        else:
            self.stopped = True

    def stop(self) -> None:
        self.stopped = True

    def spectrum(self) -> float:
        """原版 IntensityVisualizer 里 GetSpectrumData 的 64 个值的平均；没在播为 0。"""
        if not self.alive:
            return 0.0
        p = self.parts[0]
        i = int(p.vpos)
        seg = p.clip.mono[i : i + SPECTRUM_WINDOW]
        if seg.shape[0] < SPECTRUM_WINDOW:
            seg = np.pad(seg, (0, SPECTRUM_WINDOW - seg.shape[0]))
        mag = np.abs(np.fft.rfft(seg * _WINDOW))[:SPECTRUM_BINS] * (2.0 / SPECTRUM_WINDOW)
        return float(mag.mean())

    def _gain(self, p: _Part) -> float:
        v = max(0.0, self._vol * p.vol * EFFECTS_VOLUME)
        return min(1.0, v**VOLUME_EXPONENT)


def _pan(pos) -> float:
    if pos is None:
        return 0.0
    w = max(1.0, float(_listener_width()))
    return PAN_RANGE * (-1.0 + 2.0 * min(1.0, max(0.0, pos.x / w)))


class Bank:
    """一张声音表：SoundID → (PLAYALL, 触发器 (minVol, maxVol), 触发器 (minPitch, maxPitch), 指令列表)。

    指令 = (片名元组, minVol, maxVol, minPitch, maxPitch)；非 PLAYALL 时按片名数加权随机选一条。
    片段从 directory() 下的 <片名>.wav 读。
    """

    def __init__(self, sounds: dict, directory):
        self.sounds = sounds
        self._dir = directory

    def _path(self, name: str) -> str:
        return str(self._dir() / f"{name}.wav")

    def _clip(self, name: str, wait: bool = False):
        """已加载的片段；没加载好时 wait 为真就当场读，否则返回 None 并在后台线程请求加载。"""
        path = self._path(name)
        c = _clips.get(path)
        if c is None:
            if wait:
                return _load(path)
            _request(path)
        return c

    def _pick(self, sound_id: str):
        """原版 SoundTrigger.GetSoundData：返回 [(片名, 音量, 音高)]。"""
        spec = self.sounds.get(sound_id)
        if spec is None:
            return []
        play_all, (tv0, tv1), (tp0, tp1), instrs = spec
        if not play_all:
            weights = [len(i[0]) for i in instrs]
            instrs = [_rng.choices(instrs, weights)[0]]
        out = []
        for names, v0, v1, p0, p1 in instrs:
            name = _rng.choice(names)
            vol = (v0 + (v1 - v0) * _rng.random()) * (tv0 + (tv1 - tv0) * _rng.random())
            pitch = (p0 + (p1 - p0) * _rng.random()) * (tp0 + (tp1 - tp0) * _rng.random())
            out.append((name, vol, pitch))
        return out

    def has_sound(self, sound_id: str) -> bool:
        """原版 workingTriggers：sounds.txt 里有这个 SoundID 的有效条目。"""
        return sound_id in self.sounds

    def is_ready(self, sound_id: str) -> bool:
        """原版 workingTriggers：有条目且它用到的片段都能加载。"""
        spec = self.sounds.get(sound_id)
        return spec is not None and all(self._clip(n) is not None for ins in spec[3] for n in ins[0])

    def load_all(self, names) -> None:
        """同步加载这些片段，启动时在开始 tick 之前调，播放就不会因没加载而跳过。"""
        for n in names:
            path = self._path(n)
            if path not in _clips:
                _load(path)

    def play(
        self,
        sound_id: str,
        pos=None,
        vol: float = 1.0,
        pitch: float = 1.0,
        *,
        loop: bool = False,
        upkeep: bool = False,
        wait: bool = False,
    ) -> Handle | None:
        """sound_id 为原版 SoundID 名（如 "Lizard_Jaws_Grab_NPC"），pos 为房间坐标 V2 或 None。

        返回可调 volume / pitch 的句柄；原版里没有对应条目（被注释掉）或片段还没加载好时返回 None（不阻塞，
        并在后台请求加载）。短促音效没加载好就直接丢掉；叫声这类持续音由调用方下一 tick 再调 play，加载好后自然补上。
        wait=True 时没加载的片段当场读（单个片段几毫秒），给按键触发、不能丢的音效用。
        loop=True 循环播放直到 stop()；upkeep=True 对应原版 requireActiveUpkeep：要每 tick 置 h.alive = True 续命。
        持续音的用法：h = play(id, pos, loop=True, upkeep=True)；之后每 tick 改 h.volume / h.pitch、h.set_pos(pos)、h.alive = True。
        静音时照常返回句柄（叫声的口型可视化不依赖声卡），只是不进混音器。
        """
        parts = []
        for name, v, p in self._pick(sound_id):
            c = self._clip(name, wait)
            if c is not None:
                parts.append(_Part(c, v, p))
        if not parts:
            return None
        h = Handle(parts, vol, pitch, _pan(pos), loop, upkeep)
        if not _muted:
            e = _engine()
            if e is not None:
                e.add(h)
        return h


_mix = None  # _Engine，False 表示不可用


def _engine():
    """已建好的混音器；没建好返回 None，并在事件循环空闲时建（建设备要几百毫秒，不能卡在 tick 里）。"""
    global _mix
    if _mix is None:
        from PySide6.QtCore import QTimer

        _mix = False  # 占位，防止重复排队
        QTimer.singleShot(0, warmup)
        return None
    return _mix or None


def warmup() -> None:
    """建好音频设备并开始输出静音流；启动时调一次。"""
    global _mix
    if _mix:
        return
    try:
        _mix = _Engine()
    except Exception:
        _mix = False


def stop_all() -> None:
    if _mix:
        _mix.clear()


def shutdown() -> None:
    global _mix
    if _mix:
        _mix.close()
    _mix = False


def _make_device(engine):
    from PySide6.QtCore import QIODevice

    class Device(QIODevice):
        def __init__(self):
            super().__init__()
            self.open(QIODevice.OpenModeFlag.ReadOnly)

        def isSequential(self):
            return True

        def bytesAvailable(self):
            return 1 << 20

        def readData(self, maxlen):
            return engine.render(int(maxlen) // 4)

        def writeData(self, data):
            return -1

    return Device()


class _Engine:
    def __init__(self):
        from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

        dev = QMediaDevices.defaultAudioOutput()
        if dev.isNull():
            raise RuntimeError("没有音频输出设备")
        fmt = QAudioFormat()
        fmt.setSampleRate(44100)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt.setSampleRate(dev.preferredFormat().sampleRate())
            if not dev.isFormatSupported(fmt):
                raise RuntimeError("设备不支持 16 位立体声")
        self.rate = fmt.sampleRate()
        self.voices: list[tuple[Handle, _Part]] = []
        self.sink = QAudioSink(dev, fmt)
        self.sink.setBufferSize(self.rate // 12 * 4)  # 约 80ms
        self.device = _make_device(self)
        self.running = False
        self.set_running(not _muted)

    def set_running(self, on: bool) -> None:
        if on and not self.running:
            self.sink.start(self.device)
        elif not on and self.running:
            self.sink.stop()
        self.running = on

    def add(self, h: Handle) -> None:
        with _lock:
            for p in h.parts:
                self.voices.append((h, p))
            del self.voices[: max(0, len(self.voices) - MAX_VOICES)]

    def clear(self) -> None:
        with _lock:
            self.voices.clear()

    def close(self) -> None:
        self.set_running(False)

    def render(self, n: int) -> bytes:
        if not self.voices:
            return bytes(n * 4)
        out = np.zeros((n, 2), np.float32)
        ratio = 1.0 / self.rate
        ramp_t = np.arange(n, dtype=np.float64)
        with _lock:
            keep = []
            for h, p in self.voices:
                if h._expired():
                    continue
                step = h.pitch * p.pitch * p.clip.rate * ratio
                pos = p.pos + ramp_t * step
                if h.loop:
                    pos %= p.clip.frames
                i0 = pos.astype(np.int64)
                m = n if h.loop else int(np.searchsorted(i0, p.clip.frames))  # 片段范围内的点数
                if m == 0:
                    continue
                i0, fr = i0[:m], (pos[:m] - i0[:m]).astype(np.float32)[:, None]
                d = p.clip.data
                i1 = i0 + 1
                if h.loop:
                    i1 %= p.clip.frames
                s = d[i0] * (1.0 - fr) + d[i1] * fr
                g1 = h._gain(p)
                g0 = g1 if p.gain is None else p.gain
                p.gain = g1
                s *= np.linspace(g0, g1, n, dtype=np.float32)[:m, None]
                if h.pan > 0:
                    s[:, 0] *= 1.0 - h.pan
                elif h.pan < 0:
                    s[:, 1] *= 1.0 + h.pan
                out[:m] += s
                p.pos += n * step
                if h.loop:
                    p.pos %= p.clip.frames
                    keep.append((h, p))
                elif p.pos < p.clip.frames:
                    keep.append((h, p))
            self.voices = keep
        out *= LISTENER_VOLUME
        np.clip(out, -1.0, 1.0, out=out)
        return (out * 32767.0).astype("<i2").tobytes()
