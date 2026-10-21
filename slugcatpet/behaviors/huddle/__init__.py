"""挨着睡：要歇、要睡、懒着趴下时，先走到想亲近的、正趴着的猫身边，背靠背趴下。"""

from __future__ import annotations

from ...abilities.base import Param
from ...brain.social.bonds import LYING
from ...brain.social.space import LieMark, lie_extent
from ...brain.state import LIGHT, T_REST, State
from ...core.creature import WALK_STOP_EPS
from ..base import Behavior
from ..rest.states import lie_down

GAP = 2.0  # 臀离对方身子这么远


def _blocked(fsm, x, side):
    """在 x 背对对方趴下（臀朝对方、胸朝外）会压到别的猫占着或预约的地方，或者走不到 x。"""
    return (
        not fsm.social.space.free(fsm.win, *lie_extent(fsm.body, x, side))
        or fsm.body.reach(x, WALK_STOP_EPS) is None
    )


def pick_spot(fsm, p):
    """(对方, 位置 x, 在对方哪一侧)；没有合适的 None。"""
    b = fsm.body
    rain = fsm.win.rain
    r = b.chunk1.rad
    best = None
    for oc in fsm.social.space.mates(fsm.win, LYING):
        o = oc.pet
        span = o.body.lying_span()
        if span is None:
            continue
        w = fsm.social.pull(fsm.win, o)
        if w < p.min_pull or fsm.social.pull(o, fsm.win) < p.min_accept:
            continue
        for side in (-1, 1):
            x = span[0] - GAP - r if side < 0 else span[1] + GAP + r
            d = abs(x - b.chunk1.x)
            if (
                d > p.reach
                or not b.walk_min <= x <= b.walk_max
                or (rain.dangerous() and rain.keeps_out(x, b.chunk1.y))
                or _blocked(fsm, x, side)
            ):
                continue
            key = (-w, d)
            if best is None or key < best[0]:
                best = (key, o, x, side)
    return None if best is None else best[1:]


class SeekHuddle(State):
    name = "SeekHuddle"
    tier = T_REST
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self.partner = None
        self.x = 0.0
        self.side = 1
        self.why = None

    def enter(self):
        fsm = self.fsm
        fsm.body.set_posture(True)
        fsm.body.walk_to(self.x)
        fsm.social.claim(fsm.win, "lie", LieMark(self.x, fsm.body.chunk1.y, self.side), state=self.name)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        if fsm.social.state_of(self.partner) not in LYING:
            lie_down(fsm, self.why)  # 对方起来了：就地趴下
            return
        if not b.is_moving():  # 到了，或者走到一半路断了：就地趴下
            b.stop_walk()
            b.facing = self.side  # 背对对方，免得身子压上去
            lie_down(fsm, self.why)


class Huddle(Behavior):
    key = "huddle"
    title = {"zh": "挨着睡", "en": "Huddle"}
    doc = (
        "要歇一会、要睡、懒着趴下时，附近有想亲近、也不嫌弃自己的猫（看亲和和关系）正在地上趴着，"
        "就先走到它身边背靠背趴下。挨着趴的猫关系涨得快，暴风雪里变冷得慢。"
    )
    params = {
        "min_pull": Param(0.4, -1.0, 1.0, "想靠近对方至少这么多才去挨着（亲和与关系换算，见 social.pull）"),
        "min_accept": Param(0.0, -1.0, 1.0, "对方想靠近我至少这么多才肯让我挨着"),
        "reach": Param(700.0, 0.0, 5000.0, "只找这么远以内的"),
    }

    def mount(self, fsm):
        st = fsm.add_state(SeekHuddle)

        def settle(why):
            if fsm.grab.active or fsm._zerog() or fsm.body.swimming or not fsm.body.on_floor():
                return False
            spot = pick_spot(fsm, self.p)
            if spot is None:
                return False
            o, x, side = spot
            if fsm.rng.random() >= fsm.social.pull(fsm.win, o):
                return False
            st.partner, st.x, st.side, st.why = o, x, side, why
            fsm._transition("SeekHuddle")
            return True

        fsm.add_task("lie_down", settle)
