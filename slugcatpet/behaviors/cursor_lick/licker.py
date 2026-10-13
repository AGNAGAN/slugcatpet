"""舔光标交互：三阶段状态机。"""
from __future__ import annotations
import math

from ... import tuning

BAND_LO = tuning.CURSOR_DWELL_BAND_LO
BAND_HI = tuning.CURSOR_DWELL_BAND_HI

# 舔光标力学/解除常量（px/tick）
LICK_IDEAL = 40.0
LICK_REEL = 3.0
REACH_K = 0.9
LIFT_GRACE = 30
GROUND_PERSIST = 6
SPEED_RELEASE = tuning.CURSOR_SPEED_RELEASE
WALK_TIMEOUT = 160
SHOOT_TIMEOUT = 60


class CursorLicker:
    def __init__(self, win, rng):
        self.win = win
        self.body = win.body
        self.tongue = win.tongue
        self.rng = rng
        self.phase = "walk_under"
        self.timer = 0
        self.attach_ticks = 0
        self.ground_ticks = 0
        self._intent = None
        self.outcome = None
        self.tongue.reset_config()

    def update(self, cursor, cursor_speed) -> str:
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return "to_idle"
        return m(cursor, cursor_speed)

    def _in_band(self, cursor) -> bool:
        if cursor is None:
            return False
        HL = self.win._HL
        return HL * BAND_LO <= cursor[1] <= HL * BAND_HI

    def _phase_walk_under(self, cursor, cursor_speed):
        if (cursor is None or not self._in_band(cursor)
                or cursor_speed > SPEED_RELEASE or self.timer > WALK_TIMEOUT):
            self.outcome = "walk_abort"
            return "to_idle"
        self.body.walk_to(cursor[0])
        if self.body.on_floor() and not self.body.is_moving():
            self.body.stop_walk()
            self.phase = "lick_shoot"
            self.timer = 0
            self._intent = None
        return "continue"

    def _phase_lick_shoot(self, cursor, cursor_speed):
        tg = self.tongue
        if self._intent is None:
            if (cursor is None or not self._in_band(cursor)
                    or cursor_speed > SPEED_RELEASE):
                self.outcome = "walk_abort"
                return "to_idle"
            if not tg.is_idle():
                return "continue"
            mox, moy = self.win.gfx.mouth_world()
            dist = math.hypot(cursor[0] - mox, cursor[1] - moy)
            if dist <= tg.total * REACH_K:
                tg.set_targets(ideal=LICK_IDEAL, reel_rate=LICK_REEL)
                self.win.fire_tongue_at(cursor[0], cursor[1])
                self._intent = "attach"
            else:
                self._fire_miss(mox, moy, cursor)
                self._intent = "miss"
            self.timer = 0
            return "continue"

        if self._intent == "attach":
            if tg.attached:
                self.phase = "hang"
                self.attach_ticks = 0
                self.ground_ticks = 0
                self.outcome = "hang"
                return "continue"
            if tg.is_idle() or self.timer > SHOOT_TIMEOUT:
                self.outcome = "missed"
                return "to_idle"
            return "continue"

        if tg.is_idle() or self.timer > SHOOT_TIMEOUT * 2:
            self.outcome = "missed"
            return "to_idle"
        return "continue"

    def _fire_miss(self, mox, moy, cursor):
        dx, dy = cursor[0] - mox, cursor[1] - moy
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        self.tongue.shoot(mox, moy, mox + ux * self.tongue.total,
                          moy + uy * self.tongue.total, hit=False)

    def _phase_hang(self, cursor, cursor_speed):
        tg = self.tongue
        self.attach_ticks += 1
        if cursor is None or cursor[1] < 0:
            self.outcome = "lost"
            return "to_airborne"
        if cursor_speed > SPEED_RELEASE:
            self.outcome = "released"
            return "to_airborne"
        if not tg.attached:
            self.outcome = "released"
            return "to_airborne"
        # 锚点跟随光标（tongue.update 早于 body.step）
        tg.anchor = (cursor[0], cursor[1])
        tg.set_targets(ideal=LICK_IDEAL, reel_rate=LICK_REEL)
        if self.body.on_floor():
            self.ground_ticks += 1
        else:
            self.ground_ticks = 0
        if self.attach_ticks > LIFT_GRACE and self.ground_ticks >= GROUND_PERSIST:
            self.outcome = "licked_once"
            return "to_idle"
        return "continue"
