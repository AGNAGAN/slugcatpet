"""生气扔石头 / 矛。"""

from __future__ import annotations

from ... import tuning
from ...brain.hands import WEAPON, can_wield
from ...items.base import THROWABLE
from ..base import Behavior, mood_candidate, mood_params
from .states import AngryStone, ArmStone, PostThrowStand, PostThrowWander

ANGRY_STATES = ("PostThrowWander", "PostThrowStand", "AngryStone")


def grounded_weapon_available(fsm) -> bool:
    return any(
        s.state == "free"
        and not s.unfetchable
        and s.at_rest_on_ground(fsm.HL)
        and fsm.social.free_for(fsm.win, s)
        and not fsm.hands.forbidden(s)
        and can_wield(fsm.body, s)
        and fsm.body.can_hold(s)
        for s in fsm.items(THROWABLE)
    )


class Anger(Behavior):
    key = "anger"
    title = {"zh": "生气扔石头", "en": "Angry throwing"}
    doc = "被砸晕或惹急后生气：捡起能扔的东西瞄准光标扔，消气前一直盯着。好感很低时偏向拿矛。"
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
                and (fsm.hands.held(WEAPON) is not None or grounded_weapon_available(fsm))
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


class ArmStoneBehavior(Behavior):
    key = "arm_stone"
    title = {"zh": "揣块石头", "en": "Carry a stone"}
    doc = "好感低时捡块石头揣在手里（好感很低时偏向拿矛），生气时直接拿它扔；好感回升后放下。"
    requires = (THROWABLE,)
    mood = "arm_stone"
    params = mood_params(1.00, 0.70, 0.30, 0.60, 0.0040, 0.00045)

    def mount(self, fsm):
        st = fsm.add_state(ArmStone)
        b = fsm.body

        def gate(ctx):
            return (
                ctx.temper < tuning.ARM_TEMPER
                and not ctx.submerged
                and fsm.hands.held(WEAPON) is None
                and b.free_hand() is not None
                and grounded_weapon_available(fsm)
            )

        def on_stun():
            st.thrower = None

        mood_candidate(fsm, "arm_stone", self.p, gate)
        fsm.register_mood_entry("arm_stone", "ArmStone")
        fsm.on_stun(on_stun)
