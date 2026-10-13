"""找横杆：低杆直接舌钩，高杆先到墙脚舌爬再钩，钩住后交 HPole。"""

from __future__ import annotations

import math

from ...abilities.base import Param
from ...abilities.tongue.climb import TongueClimber
from ...brain.desire import _lerp
from ...brain.state import LIGHT, T_ACTIVITY, State
from ...items.base import CLIMBABLE
from ..base import Behavior, mood_candidate, mood_params

T_HPOLE_TIMEOUT = 1600
HPOLE_MAX_CLIMBS = 3
HPOLE_REACH_FRAC = 0.85
HPOLE_GRAB_REACH = 0.60


class SeekHPole(State):
    name = "SeekHPole"
    mood = "hpole"
    tier = T_ACTIVITY
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self._hp = None
        self._hp_climbs = None
        self._hp_hi = None
        self._hp_kind = None
        self._hp_lo = None
        self._hp_phase = None
        self._hp_side = None
        self._hp_tries = None
        self._hp_ux = None

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(True)
        fsm._clear_hands()
        fsm.climb = None
        self._hp_tries = 0
        self._hp_climbs = 0
        p = self._pick_hpole() if fsm.win.tongue is not None else None
        self._hp = p
        if p is None:
            self._hp_phase = "done"
            return
        self._hp_lo = min(p.ax, p.bx)
        self._hp_hi = max(p.ax, p.bx)
        mox, moy = fsm.gfx.mouth_world()
        reach = fsm.win.tongue.total * HPOLE_REACH_FRAC
        if p.ay >= moy - reach:
            self._hp_kind = "low"
            self._hp_ux = max(self._hp_lo + 8.0, min(self._hp_hi - 8.0, b.chunk1.x))
            self._hp_phase = "walk_under"
            b.walk_to(self._hp_ux)
        else:
            self._hp_kind = "high"
            self._hp_side = -1 if p.ax < fsm.WL * 0.5 else 1
            self._hp_phase = "to_wall"
            b.walk_to(b.walk_max if self._hp_side > 0 else b.walk_min)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        p = self._hp
        if p is None or p not in fsm.items(CLIMBABLE) or fsm.timer > T_HPOLE_TIMEOUT:
            self._seekhpole_break()
            fsm.settle()
            return
        lo, hi = self._hp_lo, self._hp_hi
        fsm.gfx.look_at = ((lo + hi) * 0.5, p.ay)
        ph = self._hp_phase

        if ph == "walk_under":
            if not b.is_moving() or abs(b.chunk1.x - self._hp_ux) < 8.0:
                b.stop_walk()
                self._hp_phase = "lick_low"
            return

        if ph == "lick_low":
            prog = self._try_grab_pole(p)
            if fsm.state != "SeekHPole":
                return
            if prog and self._hp_tries < 4:
                return
            self._seekhpole_break()
            fsm._transition("IdleStand")
            return

        if ph == "to_wall":
            tx = b.walk_max if self._hp_side > 0 else b.walk_min
            if not b.is_moving() or abs(b.chunk1.x - tx) < 8.0:
                b.stop_walk()
                fsm.climb = None
                self._hp_phase = "climb"
            return

        if ph == "climb":
            mox, moy = fsm.gfx.mouth_world()
            if math.hypot(mox - p.ax, moy - p.ay) <= fsm.win.tongue.total * HPOLE_GRAB_REACH:
                fsm._break_tongue()
                fsm.climb = None
                self._hp_phase = "grab"
                self._hp_tries = 0
                return
            wall_x = 0.0 if self._hp_side < 0 else fsm.WL
            if fsm.climb is None:
                fsm.climb = TongueClimber(fsm.win, self._hp_side, target=(wall_x, p.ay), stop_dist=40.0)
            done = fsm.climb.update()
            if getattr(fsm.climb, "giveup", False):
                self._hp_reclimb(b)
            elif done:
                fsm._break_tongue()
                fsm.climb = None
                self._hp_phase = "grab"
                self._hp_tries = 0
            return

        if ph == "grab":
            prog = self._try_grab_pole(p)
            if fsm.state != "SeekHPole":
                return
            if prog and self._hp_tries < 5:
                return
            self._hp_reclimb(b)
            return

        self._seekhpole_break()
        fsm._transition("IdleStand")

    def brk(self):
        self._seekhpole_break()

    def kill_break(self):
        self._seekhpole_break()

    def stun_break(self):
        fsm = self.fsm
        fsm.body.stop_walk()
        self._hp = None
        self._hp_phase = None

    def _hp_reclimb(self, b):
        """高杆够不着→回墙脚重爬(限次)；低杆/超限→放弃回 idle。"""
        fsm = self.fsm
        fsm._break_tongue()
        fsm.climb = None
        self._hp_tries = 0
        self._hp_climbs += 1
        if self._hp_kind == "high" and self._hp_climbs <= HPOLE_MAX_CLIMBS:
            self._hp_phase = "to_wall"
            b.walk_to(b.walk_max if self._hp_side > 0 else b.walk_min)
        else:
            self._seekhpole_break()
            fsm._transition("IdleStand")

    def _pick_hpole(self):
        fsm = self.fsm
        best = None
        hx = fsm.body.chunk1.x
        for p in fsm.items(CLIMBABLE):
            if p.kind != "horizontal":
                continue
            midx = (p.ax + p.bx) * 0.5
            if best is None or abs(midx - hx) < abs((best.ax + best.bx) * 0.5 - hx):
                best = p
        return best

    def _seekhpole_break(self):
        fsm = self.fsm
        fsm._break_tongue()
        fsm.body.stop_walk()
        fsm.climb = None
        self._hp = None
        self._hp_phase = None
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None

    def _try_grab_pole(self, p):
        fsm = self.fsm
        tg = fsm.win.tongue
        lo, hi = self._hp_lo, self._hp_hi
        if tg.attached:
            ax, ay = tg.anchor if tg.anchor is not None else (None, None)
            if ax is not None and abs(ay - p.ay) < 24.0 and lo - 6.0 <= ax <= hi + 6.0:
                fsm.social.claim(fsm.win, "hpole", p)
                self._hp = None
                fsm._transition("HPole")
            return True
        if tg.is_idle():
            mox, moy = fsm.gfx.mouth_world()
            tx = max(lo + 6.0, min(hi - 6.0, mox))
            if math.hypot(mox - tx, moy - p.ay) <= tg.total * HPOLE_REACH_FRAC:
                fsm.win.fire_tongue_at(tx, p.ay)
                self._hp_tries += 1
                return True
            return False
        return True


class SeekHPoleBehavior(Behavior):
    key = "seek_hpole"
    mood = "hpole"
    title = {"zh": "找横杆", "en": "Seek pole"}
    doc = "场上有横杆时，想玩就用舌头钩上去（高杆先爬墙再钩），之后横杆玩耍。"
    requires = ("tongue",)
    params = mood_params(
        1.00,
        0.72,
        0.30,
        0.30,
        0.0035,
        0.00060,
        energy_fac_fresh=Param(1.30, 0.0, 10.0, "体力满时的权重系数"),
        energy_fac_tired=Param(0.10, 0.0, 10.0, "体力空时的权重系数"),
    )

    def mount(self, fsm):
        p = self.p
        fsm.add_state(SeekHPole)
        fsm.register_mood_entry("hpole", "SeekHPole")
        gate = fsm.traits.play_gate

        def has_hpole(ctx):
            return (
                any(pl.kind == "horizontal" for pl in fsm.items(CLIMBABLE))
                and ctx.energy >= gate
                and not ctx.submerged
            )

        mood_candidate(
            fsm,
            "hpole",
            p,
            gate=has_hpole,
            energy_factor=lambda e: _lerp(e, 0.0, 1.0, p.energy_fac_tired, p.energy_fac_fresh),
            before="idle",
        )
