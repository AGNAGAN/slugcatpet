"""超度：业力满且好感疏远时触发。"""

from __future__ import annotations

from types import SimpleNamespace

from ...abilities.ascension.effect import Ascension
from ...abilities.base import Param
from ...brain.state import T_LOCKED
from ..base import Behavior


class Ascend(Behavior):
    key = "ascend"
    title = {"zh": "超度", "en": "Ascend"}
    doc = (
        "业力满且好感 ≤ temper_gate 时：杀死弹窗出现、被拎住 grab_ticks、被砸晕醒来，都会超度（比躲杀优先）。"
    )
    requires = ("ascension",)
    params = {
        "temper_gate": Param(-0.20, -1.0, 1.0, "好感 ≤ 此值（且业力满）才会超度"),
        "grab_ticks": Param(200, 1, 100000, "被光标拎住这么久（tick）且满足条件 → 超度"),
    }

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    asc = SimpleNamespace(effect=None)

    def ready():
        return fsm.body.karma >= fsm.body.karma_max and fsm.body.temper <= p.temper_gate

    def enter():
        fsm.grab.force_release()
        fsm.body.suspended = False
        asc.effect = Ascension(fsm.win)
        fsm.gfx.ascension = asc.effect

    def st_ascension(cursor, disturbed):
        done = asc.effect.update(cursor) if asc.effect else True
        if done:
            asc.effect = None
            fsm.gfx.ascension = None
            fsm._transition("Airborne")

    def kill_brk():
        if asc.effect is not None:
            asc.effect.abort()
            asc.effect = None
        fsm.gfx.ascension = None
        fsm.body.suspended = False

    def drag_takeover(frames):
        if frames >= p.grab_ticks and ready():
            fsm._transition("Ascension")
            return True
        return False

    def stun_takeover():
        if ready():
            fsm._transition("Ascension")
            return True
        return False

    def respond():
        if not ready():
            return False
        fsm._dismiss_kill_dialog()
        fsm._transition("Ascension")
        return True

    fsm.register_state(
        "Ascension", enter=enter, tick=st_ascension, kill_break=kill_brk, fx=lambda: asc.effect, tier=T_LOCKED
    )
    fsm.drag_takeover = drag_takeover
    fsm.stun_takeover = stun_takeover
    fsm.add_threat_responder(respond)
    fsm.block_interaction("Ascension")
