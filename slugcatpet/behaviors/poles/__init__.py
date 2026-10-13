"""爬杆。"""

from __future__ import annotations

from ... import tuning
from ...brain.desire import Candidate, _lerp
from ...items.base import CLIMBABLE
from ..base import Behavior
from .states import HPole, PoleClimb, pole_free


class Poles(Behavior):
    key = "poles"
    title = {"zh": "爬杆", "en": "Poles"}
    doc = "无聊时去爬竖杆、站杆顶；横杆上吊挂和行走的状态也在这里。"
    requires = (CLIMBABLE,)

    def mount(self, fsm):
        climb = fsm.add_state(PoleClimb)
        hang = fsm.add_state(HPole)
        gate_e = fsm.traits.play_gate

        def vertical_pole():
            return any(
                p.kind == "vertical" and p.grounded and pole_free(fsm, p) for p in fsm.items(CLIMBABLE)
            )

        fsm.mood.add(
            Candidate(
                "pole_climb",
                base=tuning.POLE_BASE * fsm.traits.mood_weight("pole_climb"),
                start=tuning.POLE_START,
                quit=tuning.POLE_QUIT,
                decay=tuning.POLE_DECAY,
                recover=tuning.POLE_RECOVER,
                gate=lambda ctx: vertical_pole() and ctx.energy >= gate_e and not ctx.submerged,
                energy_factor=lambda e: _lerp(e, 0.0, 1.0, tuning.POLE_SF_TIRED, tuning.POLE_SF_FRESH),
                temper_factor=lambda t: 1.0,
                one_shot=True,
                init=tuning.POLE_INIT,
            )
        )
        fsm.register_mood_entry("pole_climb", "PoleClimb")

        def on_stun():
            fsm.social.leave_tips(fsm.win)
            if climb.climber is not None:
                b = fsm.body
                b.chunk0.pinned = False
                b.chunk1.pinned = False
                b.on_pole = False
                b.animation = None
                climb.climber = None
            if hang.ctl is not None:
                hang.ctl.release()
                hang.ctl = None

        fsm.on_stun(on_stun)
