"""舔光标。"""

from __future__ import annotations

from types import SimpleNamespace

from ...abilities.base import Param
from ...abilities.tongue.aim import tongue_of
from ... import tuning
from ...brain.fsm import _lerpmap
from ...brain.state import LIGHT, T_ACTIVITY
from ...items.base import CLIMBABLE
from ..base import Behavior
from .licker import BAND_HI, BAND_LO, CursorLicker


HPOLE_NEAR_Y = 20.0


def _horizontal_pole_near(fsm, cursor):
    if cursor is None:
        return None
    cx, cy = cursor
    for p in fsm.items(CLIMBABLE):
        if p.kind != "horizontal":
            continue
        lo, hi = (p.ax, p.bx) if p.ax <= p.bx else (p.bx, p.ax)
        if lo <= cx <= hi and abs(cy - p.ay) <= HPOLE_NEAR_Y:
            return p
    return None


class CursorLick(Behavior):
    key = "cursor_lick"
    title = {"zh": "舔光标", "en": "Cursor lick"}
    doc = "光标停在屏幕中下部、离猫够近够久：伸舌去舔（好感越高等得越短），舔到加好感。"
    requires = ("tongue",)
    params = {
        "dwell_ticks": Param(
            tuning.CURSOR_DWELL_TICKS, 1, 4000, "光标驻留基准 tick（好感 -1 时 ×1.5，+1 时 ×0.5）"
        ),
        "gate_frac": Param(1.0 / 3.0, 0.0, 1.0, "光标与猫水平距离 < 屏宽 × 此值才会舔"),
        "relick_cooldown": Param(60, 0, 100000, "舔完后的冷却 tick"),
        "temper_gain": Param(0.10, -1.0, 1.0, "成功舔到一次的好感变化"),
    }

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    lick = SimpleNamespace(licker=None, cooldown=0)

    def cool_down():
        if lick.cooldown > 0:
            lick.cooldown -= 1

    def enter():
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        fsm._dwell = 0
        lick.licker = CursorLicker(fsm.win, fsm.rng)

    def st_cursorlick(cursor, disturbed):
        if lick.licker is None:
            fsm._transition("IdleStand")
            return
        fsm.gfx.look_at = cursor
        status = lick.licker.update(cursor, fsm._cursor_speed)
        if status == "to_idle":
            if lick.licker.outcome == "licked_once":
                fsm.body.temper_shift(p.temper_gain)
            brk()
            fsm._transition("IdleStand")
        elif status == "to_airborne":
            brk()
            fsm._transition("Airborne")
        elif lick.licker.phase == "hang" and tongue_of(fsm.win).attached:
            pole = _horizontal_pole_near(fsm, cursor)
            if pole is not None:
                lick.licker = None
                fsm._dwell = 0
                lick.cooldown = p.relick_cooldown
                fsm.social.claim(fsm.win, "hpole", pole)
                fsm._transition("HPole")

    def brk():
        fsm.release_organs()
        fsm.body.stop_walk()
        lick.licker = None
        fsm._dwell = 0
        lick.cooldown = p.relick_cooldown

    def stun_brk():
        lick.licker = None

    fsm.register_ticker(cool_down)
    fsm.register_state(
        "CursorLick",
        enter=enter,
        tick=st_cursorlick,
        brk=brk,
        kill_break=brk,
        stun_break=stun_brk,
        tier=T_ACTIVITY,
        energy=LIGHT,
    )

    def lick_rule(cursor):
        need = _lerpmap(fsm.body.temper, -1.0, 1.0, p.dwell_ticks * 1.5, p.dwell_ticks * 0.5)
        if (
            fsm.state == "IdleStand"
            and not fsm.grab.active
            and not fsm.ask("exhausted")
            and not fsm._zerog()
            and lick.cooldown <= 0
            and fsm._dwell >= need
            and cursor is not None
            and fsm.HL * BAND_LO <= cursor[1] <= fsm.HL * BAND_HI
            and abs(fsm.body.chunk0.x - cursor[0]) < fsm.WL * p.gate_frac
        ):
            fsm._transition("CursorLick")

    fsm.register_rule(lick_rule)
