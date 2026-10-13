"""生气扔石头。"""

from __future__ import annotations

from ...items.base import THROWABLE
from ..base import Behavior
from .states import AngryStone, PostThrowStand, PostThrowWander

ANGRY_STATES = ("PostThrowWander", "PostThrowStand", "AngryStone")


def grounded_stone_available(fsm) -> bool:
    return any(
        s.state == "free"
        and not s.unfetchable
        and s.at_rest_on_ground(fsm.HL)
        and fsm.social.free_for(fsm.win, s)
        for s in fsm.items(THROWABLE)
    )


class Anger(Behavior):
    key = "anger"
    title = {"zh": "生气扔石头", "en": "Angry throwing"}
    doc = "被砸晕或惹急后生气：捡起能扔的东西瞄准光标扔，消气前一直盯着。"
    requires = (THROWABLE,)

    def mount(self, fsm):
        for cls in (PostThrowWander, PostThrowStand):
            fsm.add_state(cls)
        throw = fsm.add_state(AngryStone)

        def pick_up(cursor):
            if (
                fsm.state in ANGRY_STATES[:2]
                and fsm.anger > 0
                and not fsm.grab.active
                and grounded_stone_available(fsm)
            ):
                fsm._transition("AngryStone")

        def cool_down(cursor):
            if fsm.anger > 0 and fsm.state in ANGRY_STATES:
                fsm.anger -= 1

        def on_stun():
            throw.thrower = None

        fsm.register_rule(pick_up)
        fsm.register_rule(cool_down)
        fsm.on_stun(on_stun)
