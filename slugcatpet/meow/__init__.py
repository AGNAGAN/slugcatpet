"""喵：照 Push to Meow 的按键喵。

- 按下后 LONG_S 内松开是短喵，按住过了 LONG_S 当场长喵；离上次按下不到 COOLDOWN_S 时，按着等冷却过去再算按下。
- 喵谁在按下时定下，之后光标移开、猫跑开都不影响。
- 一声喵：出声（猫种、幼崽、被光标拎着、水下定音高），抬头眨眼（矛大师不抬头、甩尾），
  扣肺里的空气（溪流不扣），水下冒泡（矛大师从尾巴冒）。死了不喵。
"""

from __future__ import annotations

import random
import time

from PySide6.QtCore import QObject, QTimer

from ..audio import sfx
from ..core.units import TICK_RATE
from .assets import import_meow_sounds, meow_sounds_dir
from .voice import SOUNDS, choose

LONG_S = 0.14
COOLDOWN_S = 0.24
POLL_MS = 10
VOLUME = 0.85  # 原版默认音量
LUNG_COST = 0.08  # 短喵扣这么多，长喵加倍
BUBBLES = 2  # 水下冒的泡，长喵多一个
SPEAR_TAIL_BUBBLE = 2  # 矛大师的泡从第几节尾巴冒
# 原版动画用毫秒计时器，这里按 tick 算
LOOK_DELAY_S = 0.033
LOOK_S = (0.16, 0.26)  # 短、长喵抬头多久
BLINK = (9, 11)  # 短、长喵眨眼的 tick
WIGGLE_DOWN_MS = (80, 139)  # 矛大师尾巴甩上去后多久甩下来
LOOK_FAR = 1e5


def _ticks(s):
    return max(1, round(s * TICK_RATE))


class MeowFx:
    """一声喵带的动作，挂在 pet.meow_fx 上，每 tick 在状态机之后、物理之前推进；做完返回 False。"""

    def __init__(self, short, look_up, wiggle, rng):
        i = 0 if short else 1
        self.t = 0
        self.look_from = _ticks(LOOK_DELAY_S)
        self.look_to = _ticks(LOOK_DELAY_S + LOOK_S[i])
        self.blink = BLINK[i]
        self.look_up = look_up
        self.wiggle_down = _ticks(rng.randint(*WIGGLE_DOWN_MS) / 1000.0) if wiggle else 0
        self.fling = 0.0
        self.rng = rng

    def wiggle(self, pet):
        """尾巴甩到背对朝向的一侧、往上翘，wiggle_down 个 tick 后甩下来。"""
        self.fling = -pet.body.facing * 2.0
        for i, seg in enumerate(pet.tail.segs):
            seg.vx = self.fling
            seg.vy = -self.rng.randint(3, 5) / 2.0 * (i - 1) * 1.5

    def tick(self, pet) -> bool:
        if pet.body.dead:
            return False
        g = pet.gfx
        self.t += 1
        if self.t == self.look_from:
            g.blink = max(g.blink, self.blink)
        if self.look_up and self.look_from <= self.t < self.look_to:
            g.look_at = (g.head.x, g.head.y - LOOK_FAR)
        if self.t == self.wiggle_down:
            for i, seg in enumerate(pet.tail.segs):
                seg.vx = self.fling
                seg.vy = self.rng.randint(4, 7) / 3.0 * (i - 1) * 1.5
        return self.t < max(self.look_to if self.look_up else self.look_from, self.wiggle_down)


class MeowService(QObject):
    """按键喵的入口：全局热键喵光标下（或控制中）的猫，控制面板的喵键喵控制中的猫。"""

    def __init__(self, window, params, muted=lambda: False, parent=None):
        super().__init__(parent)
        self._win = window
        self._params = params
        self._muted = muted
        self._rng = random.Random()
        self.bank = sfx.Bank(SOUNDS, meow_sounds_dir)
        self.has_sounds = import_meow_sounds()
        if self.has_sounds:
            sfx.set_listener_width(lambda: window._WL)
            sfx.warmup()
        self._pending = None  # [猫, 按着吗(), 按下时刻；冷却中为 None]
        self._last = -1e9
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

    @property
    def volume(self) -> float:
        return float(self._params.get("meow_volume", VOLUME))

    def set_volume(self, v: float) -> None:
        self._params["meow_volume"] = max(0.0, min(1.0, float(v)))

    def target(self):
        """光标下的猫（几只叠着取离光标最近的），没有就是控制中的猫。"""
        from ..control.mouse import is_over

        w = self._win
        cur = w.cursor_logical()
        over = [p for p in w.pets if is_over(p.body, p.gfx, cur, pad=6.0)]
        if over:
            return min(over, key=lambda p: (p.body.chunk0.x - cur[0]) ** 2 + (p.body.chunk0.y - cur[1]) ** 2)
        return next((p for p in w.pets if p.controlled), None)

    def press(self, pet, held) -> None:
        """按下喵键；held() 返回这个键还按着没有。"""
        if pet is None or self._pending is not None or self._win._freeze:
            return
        self._pending = [pet, held, None]
        self._poll()
        if self._pending is not None:
            self._timer.start()

    def _drop(self):
        self._pending = None
        self._timer.stop()

    def _poll(self):
        pet, held, t0 = self._pending
        if pet not in self._win.pets:
            self._drop()
            return
        now = time.monotonic()
        down = held()
        if t0 is None:
            if not down:
                self._drop()
            elif now - self._last >= COOLDOWN_S:
                self._pending[2] = self._last = now
            return
        if down and now - t0 > LONG_S:
            self.meow(pet, short=False)
            self._drop()
        elif not down:
            if now - t0 <= LONG_S:
                self.meow(pet, short=True)
            self._drop()

    def meow(self, pet, short: bool) -> None:
        b = pet.body
        if b.dead:
            return
        rng = self._rng
        spear = pet.cat.key == "spearmaster"
        if self.has_sounds and not self._muted():
            panic = pet.behavior is not None and pet.behavior.grab.active
            sid, pitch, vol = choose(pet.cat.key, pet.gfx.pup, short, panic, b.submerged, rng)
            self.bank.play(sid, b.chunk0, self.volume * vol, pitch, wait=True)
        fx = MeowFx(short, not spear, spear, rng)
        if spear:
            fx.wiggle(pet)
        pet.meow_fx = fx
        if not b.aquatic:
            b.air_in_lungs -= LUNG_COST * (1 if short else 2)
        if b.submerged and b.bubble_cb is not None:
            segs = pet.tail.segs
            src = segs[min(SPEAR_TAIL_BUBBLE, len(segs) - 1)] if spear else b.chunk0
            for _ in range(BUBBLES + (0 if short else 1)):
                b.bubble_cb(src.x, src.y, src.vx, src.vy)
