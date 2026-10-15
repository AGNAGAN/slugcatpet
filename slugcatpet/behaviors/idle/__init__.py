"""发呆，闲下来时挑下一件事。"""

from __future__ import annotations

from ... import tuning
from ...brain.desire import MoodContext
from ...brain.intent import smooth
from ..base import Behavior
from .state import IdleStand


def listless(fsm):
    """饿着又没吃的时少动的系数。"""
    b = fsm.body
    need = max(1, b.food_hibernate)
    short = max(0.0, need - b.food) / need
    if short <= 0.0 or fsm.ask("food_ready"):
        return 1.0
    return 1.0 - tuning.HUNGRY_PLAY_DAMP * short


class Idle(Behavior):
    key = "idle"
    title = {"zh": "发呆", "en": "Idle"}
    doc = "默认状态：站着发呆、东张西望、踱步、对视；无重力时漂浮。闲待一阵后按需求和性格随机挑下一件事。"
    essential = True

    def mount(self, fsm):
        fsm.add_state(IdleStand)
        b = fsm.body
        fsm.provide("listless", lambda: listless(fsm))

        def ctx():
            return MoodContext(b.energy, b.temper, cold=b.cold, submerged=b.swimming)

        def want_play():
            if not fsm.mood.eligible(ctx()):
                return 0.0
            return (
                tuning.PLAY_UTIL
                * fsm.traits.activity
                * smooth(0.25, 0.6, b.energy)
                * (1.0 - 0.6 * smooth(0.5, 0.9, b.sleepiness))
                * listless(fsm)
            )

        def start_play():
            entry = fsm._mood_entries.get(fsm.mood.select(ctx()))
            if entry is None:
                return False
            state, before = entry
            if before is not None:
                before()
            fsm._transition(state)
            return True

        fsm.intents.add("hang", lambda: tuning.HANG_UTIL, lambda: False)
        fsm.intents.add("play", want_play, start_play)
