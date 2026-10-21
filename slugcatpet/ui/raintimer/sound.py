"""表盘音效：原版 sounds.txt 里各事件对应的片段与音量，业力梯转轮循环音随滚动快慢变化。"""

from __future__ import annotations
import random

from PySide6.QtCore import QObject, QUrl

from ...gameassets import dial_sounds_dir

# 事件 → [(片名候选, 音量)]，同一事件的几条一起响
EVENTS = {
    "deselect": [(("karmaFuzz",), 0.4)],
    "start_moving": [(("karmaWheelC_1", "karmaWheelC_2", "karmaWheelC_3", "karmaWheelC_4"), 0.4)],
    "cap_hit": [(("capBell2",), 0.3)],
    "bump": [(("karmaRiseA",), 0.4), (("UIWoodHit",), 0.4)],
    "cap_bump": [(("karmaRiseA",), 0.4), (("UIWoodHit",), 0.4)],
    "tick": [(("tick",), 0.25)],
    "tock": [(("tock",), 0.25)],
}
LOOP_CLIP, LOOP_VOL = "karmaWheelLow", 0.5


class KarmaSounds(QObject):
    def __init__(self, muted=lambda: False, parent=None):
        super().__init__(parent)
        self._muted = muted
        self._fx = {}
        self._loop = None
        self._rng = random.Random()

    def _effect(self, name, loop=False):
        if name in self._fx:
            return self._fx[name]
        path = dial_sounds_dir() / f"{name}.wav"
        e = None
        if path.is_file():
            from PySide6.QtMultimedia import QSoundEffect

            e = QSoundEffect(self)
            e.setSource(QUrl.fromLocalFile(str(path)))
            if loop:
                e.setLoopCount(QSoundEffect.Loop.Infinite.value)
        self._fx[name] = e
        return e

    def play(self, event):
        if self._muted():
            return
        for names, vol in EVENTS.get(event, ()):
            e = self._effect(self._rng.choice(names))
            if e is not None:
                e.setVolume(vol)
                e.play()

    def set_motion(self, speed):
        """滚动速度 → 转轮循环音的音量；0 时停掉。"""
        v = 0.0 if self._muted() else min(1.0, speed / 0.01) * LOOP_VOL
        e = self._loop or self._effect(LOOP_CLIP, loop=True)
        self._loop = e
        if e is None:
            return
        if v > 0.0:
            e.setVolume(v)
            if not e.isPlaying():
                e.play()
        elif e.isPlaying():
            e.stop()
