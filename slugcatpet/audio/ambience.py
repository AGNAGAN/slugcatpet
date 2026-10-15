"""雨声：轻、重两条循环随雨强变化，露天少时换成室内的闷响。"""

from __future__ import annotations
import math

from PySide6.QtCore import QObject, QTimer, QUrl

from .. import tuning
from ..core.units import clampf
from ..gameassets import rain_sounds_dir
from ..world.rain import inv_lerp

# (片名, 音量)：室外轻、室外重、室内轻、室内重
CLIPS = (
    ("shortLightRainLoop", 0.7),
    ("rainHeavy1", 0.6),
    ("rainLightUnderground1", 0.7),
    ("rainMedUnderground1", 0.5),
)
UPDATE_MS = 100
EASE = 0.3  # 每次更新音量向目标靠近的比例
OPEN_FULL = 0.6  # 露天面积到这个比例就全按室外听
SILENT = 0.002


def light_curve(i):
    if i <= 0.0:
        return 0.0
    return 0.1 + 0.9 * max(0.0, math.sin(inv_lerp(0.001, 0.7, i) * math.pi)) ** 1.5


def heavy_curve(i):
    return inv_lerp(0.12, 0.5, i) ** 0.85


class RainAmbience(QObject):
    def __init__(self, window, player, params, parent=None):
        super().__init__(parent)
        self._win = window
        self._player = player
        self._params = params
        self.volume = clampf(float(params.get("rain_volume", tuning.RAIN_VOLUME)), 0.0, 1.0)
        self._fx = None
        self._vol = [0.0] * len(CLIPS)
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

    def _effects(self):
        """四条循环；素材未就绪时返回 None。"""
        if self._fx is None:
            d = rain_sounds_dir()
            if not all((d / f"{n}.wav").is_file() for n, _ in CLIPS):
                return None
            from PySide6.QtMultimedia import QSoundEffect

            fx = []
            for name, _ in CLIPS:
                e = QSoundEffect(self)
                e.setSource(QUrl.fromLocalFile(str(d / f"{name}.wav")))
                e.setLoopCount(QSoundEffect.Loop.Infinite.value)
                e.setVolume(0.0)
                fx.append(e)
            self._fx = fx
        return self._fx

    def _targets(self):
        w = self._win
        rain = w.rain
        if self._player.muted or not w.isVisible() or not rain.active:
            return [0.0] * len(CLIPS)
        i = rain.intensity
        out = min(1.0, rain.open_frac / OPEN_FULL)
        mix = (out, out, 1.0 - out, 1.0 - out)
        curve = (light_curve(i), heavy_curve(i)) * 2
        return [c * v * m * self.volume for c, (_, v), m in zip(curve, CLIPS, mix)]

    def _update(self):
        targets = self._targets()
        fx = self._effects()
        if fx is None:
            if not any(targets):
                self._timer.stop()
            return
        for k, (e, tgt) in enumerate(zip(fx, targets)):
            v = self._vol[k] + (tgt - self._vol[k]) * EASE
            if abs(v - tgt) < SILENT:
                v = tgt
            self._vol[k] = v
            if v > 0.0:
                e.setVolume(v)
                if not e.isPlaying():
                    e.play()
            elif e.isPlaying():
                e.stop()
        if not any(self._vol) and not self._win.rain_on:
            self._timer.stop()
