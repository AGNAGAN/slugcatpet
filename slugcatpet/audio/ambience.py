"""雨声：照原版几条循环随雨强变化（轻雨、大雨、致命雨、轰鸣），露天少时换成室内的闷响；大雨时零星的雨点砸地声。"""

from __future__ import annotations
import math
import random

from PySide6.QtCore import QObject, QTimer, QUrl

from .. import tuning
from ..core.units import clampf
from ..gameassets import rain_sounds_dir
from ..world.rain import inv_lerp, smooth, storm, visual

UPDATE_MS = 100
EASE = 0.3  # 每次更新音量向目标靠近的比例
OPEN_FULL = 0.6  # 露天面积到这个比例就全按室外听
SILENT = 0.002
DRIP_CLIP, DRIP_VOL = "click1A", 0.4  # 雨点砸地（原版 Bullet_Drip_Strike）
DRIP_VOICES = 6  # 同时能响几颗
DRIP_RATE = 22.0  # 最密时每秒几颗


def light_curve(g):
    if g <= 0.0:
        return 0.0
    return 0.1 + 0.9 * max(0.0, math.sin(inv_lerp(0.001, 0.7, g) * math.pi)) ** 1.5


def death_curve(g):
    return inv_lerp(0.35, 0.75, g) ** 0.8


def heavy_curve(g):
    return inv_lerp(0.12, 0.5, g) ** 0.85 * (1.0 - death_curve(g)) ** 0.3


def rumble_curve(g):
    return smooth(storm(g))


def drip_density(g):
    """雨点砸地的密度：快到暴雨时最密，满雨时还剩一些。"""
    return smooth(inv_lerp(0.35, 0.6, g)) * (1.0 - 0.6 * smooth(inv_lerp(0.8, 1.0, g)))


# (片名, 原版音量, 音量曲线, 在哪听)：out 露天、in 室内
CLIPS = (
    ("shortLightRainLoop", 0.7, light_curve, "out"),
    ("rainHeavy1", 0.6, heavy_curve, "out"),
    ("shortDeathRainLoop", 0.6, death_curve, "out"),
    ("rainLightUnderground1", 0.7, light_curve, "in"),
    ("rainMedUnderground1", 0.5, heavy_curve, "in"),
    ("RWTW_RainRumble_LOOP", 0.5, rumble_curve, "both"),
)


class RainAmbience(QObject):
    def __init__(self, window, player, params, parent=None):
        super().__init__(parent)
        self._win = window
        self._player = player
        self._params = params
        self.volume = clampf(float(params.get("rain_volume", tuning.RAIN_VOLUME)), 0.0, 1.0)
        self._fx = None  # 片名 → QSoundEffect，素材缺的那条为 None
        self._vol = [0.0] * len(CLIPS)
        self._drips = None
        self._drip_next = 0
        self._rng = random.Random(0xD21B)
        self._timer = QTimer(self)
        self._timer.setInterval(UPDATE_MS)
        self._timer.timeout.connect(self._update)
        window.env_listeners.append(self._on_env)
        if window.rain_on:
            self._timer.start()

    def set_volume(self, v):
        self.volume = self._params["rain_volume"] = clampf(float(v), 0.0, 1.0)

    def _on_env(self, kind, on):
        if kind == "rain" and on and not self._timer.isActive():
            self._timer.start()

    def _effect(self, name, loop=True):
        d = rain_sounds_dir()
        if not (d / f"{name}.wav").is_file():
            return None
        from PySide6.QtMultimedia import QSoundEffect

        e = QSoundEffect(self)
        e.setSource(QUrl.fromLocalFile(str(d / f"{name}.wav")))
        if loop:
            e.setLoopCount(QSoundEffect.Loop.Infinite.value)
        e.setVolume(0.0)
        return e

    def _effects(self):
        """各条循环；一条素材都没有时返回 None。"""
        if self._fx is None:
            fx = {name: self._effect(name) for name, *_ in CLIPS}
            if not any(fx.values()):
                return None
            self._fx = fx
            drips = [self._effect(DRIP_CLIP, loop=False) for _ in range(DRIP_VOICES)]
            self._drips = [e for e in drips if e is not None]
        return self._fx

    def _quiet(self):
        w = self._win
        return self._player.muted or not w.isVisible() or not w.rain.active

    def _targets(self):
        if self._quiet():
            return [0.0] * len(CLIPS), 0.0
        rain = self._win.rain
        g = visual(rain.intensity)
        out = min(1.0, rain.open_frac / OPEN_FULL)
        place = {"out": out, "in": 1.0 - out, "both": 1.0}
        vols = []
        for _, base, curve, where in CLIPS:
            v = curve(g) * base * place[where]
            if where == "both":  # 室内听致命雨就是这条闷响
                v = max(v, death_curve(g) * base * (1.0 - out))
            vols.append(v * self.volume)
        return vols, out

    def _update(self):
        targets, out = self._targets()
        fx = self._effects()
        if fx is None:
            if not any(targets):
                self._timer.stop()
            return
        for k, ((name, *_), tgt) in enumerate(zip(CLIPS, targets)):
            e = fx[name]
            v = self._vol[k] + (tgt - self._vol[k]) * EASE
            if abs(v - tgt) < SILENT:
                v = tgt
            self._vol[k] = v
            if e is None:
                continue
            if v > 0.0:
                e.setVolume(v)
                if not e.isPlaying():
                    e.play()
            elif e.isPlaying():
                e.stop()
        self._drip_tick(out)
        if not any(self._vol) and not self._win.rain_on:
            self._timer.stop()

    def _drip_tick(self, out):
        """这 100ms 里随机落几颗雨点，各自错开一点时间响。"""
        if not self._drips or self._quiet() or out <= 0.0:
            return
        rate = DRIP_RATE * drip_density(visual(self._win.rain.intensity))
        n = rate * UPDATE_MS / 1000.0
        count = int(n) + (self._rng.random() < n - int(n))
        for _ in range(count):
            vol = DRIP_VOL * self._rng.uniform(0.4, 1.0) * out * self.volume
            QTimer.singleShot(self._rng.randrange(UPDATE_MS), lambda v=vol: self._drip(v))

    def _drip(self, vol):
        e = self._drips[self._drip_next]
        self._drip_next = (self._drip_next + 1) % len(self._drips)
        e.setVolume(vol)
        e.play()
