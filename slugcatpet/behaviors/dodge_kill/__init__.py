"""舌头躲杀。"""

from __future__ import annotations

from types import SimpleNamespace

from ...abilities.base import Param
from ...brain.state import T_REFLEX, VIGOROUS
from ..base import Behavior
from .dodger import KillDodger


class DodgeKill(Behavior):
    key = "dodge_kill"
    title = {"zh": "舌头躲杀", "en": "Kill dodge"}
    doc = "杀死弹窗出现时用舌头点「取消」（够不到就先爬墙）；游泳中不躲。被这样取消会扣好感。"
    requires = ("tongue",)
    params = {
        "cancel_temper": Param(-0.20, -1.0, 1.0, "自己用舌头取消杀死弹窗时的好感变化"),
    }

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    dodge = SimpleNamespace(ctl=None)

    def release():
        if dodge.ctl is not None:
            dodge.ctl.release()
            dodge.ctl = None

    def enter():
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None
        fsm.body.set_posture(True)
        fsm.body.stop_walk()
        dodge.ctl = KillDodger(fsm.win, fsm.rng)

    def st_dodgekill(cursor, disturbed):
        if getattr(fsm.win, "_kill_dialog", None) is None:
            brk()
            fsm.settle()
            return
        if fsm.grab.active:
            brk()
            fsm._transition("Dragged")
            return
        if dodge.ctl is None:
            brk()
            fsm._transition("IdleStand")
            return
        done = dodge.ctl.update()
        if done:
            brk()
            fsm.settle()

    def brk():
        release()
        fsm.release_organs()
        fsm.body.stop_walk()
        fsm.gfx.hand_aim["l"] = None
        fsm.gfx.hand_aim["r"] = None

    fsm.register_state(
        "DodgeKill",
        enter=enter,
        tick=st_dodgekill,
        brk=brk,
        kill_break=brk,
        stun_break=release,
        tier=T_REFLEX,
        energy=VIGOROUS,
    )

    def respond():
        if fsm.body.swimming:
            return False
        fsm._transition("DodgeKill")
        return True

    fsm.add_threat_responder(respond)
    fsm.kill_cancel_temper = p.cancel_temper
