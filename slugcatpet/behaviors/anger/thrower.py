"""生气时捡武器朝光标扔的控制器：select → approach / grow → hold → throw，update() 返回下一步去向。"""

from __future__ import annotations

from ... import tuning
from ...brain.skills.throw import Pitch, WeaponPickup

HOLD_AIM_TICKS = 80  # 拿到武器后先盯光标这么久才扔
ABANDON_MIN = 400  # 一直等不到机会，过这么久就消气
ABANDON_MAX = 600


def can_grow_weapon(fsm, grow):
    """地上没武器时能不能从身上长一件：长出来的扎得进，和拿矛一样只在好感很低时。"""
    b = fsm.body
    return grow is not None and grow.ready() and not b.stats.spear_toss and b.temper < tuning.SPEAR_TEMPER


def weapon_score(fsm, obj, dist):
    """挑武器的排序值（小者优先）：好感很低时偏向扎得进的。"""
    if getattr(obj, "pierces", False) and fsm.body.temper < tuning.SPEAR_TEMPER:
        return dist * tuning.SPEAR_PREF
    return dist


class WeaponThrower:
    """keep=True 时捡到就收工（揣着），否则捡到后瞄准光标扔。"""

    def __init__(self, win, rng, fsm, keep=False):
        self.body = win.body
        self.rng = rng
        self.fsm = fsm
        self.keep = keep

        self.target = None
        self.phase = "select"
        self.timer = 0
        self.abandon_at = ABANDON_MAX
        self._pickup = WeaponPickup(fsm, lambda s, d: weapon_score(fsm, s, d), "AngryStone")
        self._grow = None if keep else fsm.win.skill("grow_weapon")
        self._pitch = None

    def start_with(self, stone):
        """手里已经有武器：直接进入瞄准。"""
        self.target = stone
        self._hold()

    def _hold(self):
        self._pitch = Pitch(self.fsm, self.target)
        self.phase = "hold"
        self.timer = 0
        self.abandon_at = self.rng.randint(ABANDON_MIN, ABANDON_MAX)

    def update(self, still_angry) -> str:
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return "idle"
        return m(still_angry)

    def _phase_select(self, still_angry):
        if not still_angry:
            return "idle"
        if not self._pickup.select():
            if can_grow_weapon(self.fsm, self._grow):
                self.phase = "grow"
                return "running"
            return "revert_wander"
        self.target = self._pickup.target
        self.timer = 0
        self.phase = "approach"
        return "running"

    def _phase_approach(self, still_angry):
        if not self._pickup.available():
            return "revert_wander" if still_angry else "idle"
        if not still_angry:
            return "idle"
        r = self._pickup.update()
        if r == "got":
            if self.keep:
                return "armed"
            self._hold()
        elif r == "failed":
            return "revert_wander"
        return "running"

    def _phase_grow(self, still_angry):
        if not still_angry:
            return "idle"
        r = self._grow.update()
        if r == "got":
            self.target = self._grow.weapon
            self._hold()
        elif r == "fail":
            return "revert_wander"
        return "running"

    def _phase_hold(self, still_angry):
        pitch = self._pitch
        if pitch.side() is None:
            return "revert_wander" if still_angry else "idle"
        self.body.stop_walk()
        cursor = self.fsm.cursor
        self.fsm.gfx.look_at = cursor
        if still_angry:
            if self.timer >= self.abandon_at:
                self.fsm.anger = 0
                return "revert_wander"
            if cursor is None:
                return "running"
            pitch.face(cursor)
            aimed = pitch.aim(cursor)
            if aimed and self.timer >= HOLD_AIM_TICKS and pitch.can_hit(cursor):
                pitch.release()
                self.phase = "throw"
        else:
            pitch.release_blind(1 if self.rng.random() < 0.5 else -1)
            self.phase = "throw"
        return "running"

    def _phase_throw(self, still_angry):
        return self._pitch.update(self.fsm.cursor)
