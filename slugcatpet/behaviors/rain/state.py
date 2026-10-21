"""躲雨：走到最近的有遮挡的地面上。"""

from __future__ import annotations

from ..perch.choose import Mark
from ...brain.state import LIGHT, T_WARM, State
from ...planning import GIVEUP, HOLDING, MODE_STAY, PlanExecutor, point_goal
from ...planning.climbmoves import release
from ...world.rain import SHELTER_MARGIN

ARRIVE = 12.0
RETRY = 200  # 走不过去后多久再试
SPACING = 36.0  # 躲雨时和别的猫隔开的距离
SCAN_STEP = 4.0


def exposed(fsm) -> bool:
    """身上有一处淋得到（和雨砸的范围一样）。"""
    rain = fsm.win.rain
    b = fsm.body
    return rain.touches(b.chunk0) or rain.touches(b.chunk1)


def _taken(fsm):
    """别的猫已经躲着或预约了要去躲的位置。"""
    out = []
    for o in fsm.social.others(fsm.win):
        m = fsm.social.held(o, "shelter")
        if m is not None:
            out.append(m.x)
        elif not fsm.win.rain.exposed(o.body.chunk1.x, o.body.chunk1.y):
            out.append(o.body.chunk1.x)
    return out


def shelter_x(fsm):
    """离自己最近、和别的猫隔得开的躲雨位置；都站满了就挨着最近的。"""
    b = fsm.body
    lo = 0.0 if b.walk_min is None else b.walk_min
    hi = fsm.WL if b.walk_max is None else b.walk_max
    spans = fsm.win.rain.floor_spans(lo, hi, SHELTER_MARGIN)
    if not spans:
        return None
    x, taken = b.chunk1.x, _taken(fsm)
    best = None
    for a, c in spans:
        p = min(max(x, a), c)
        n = int((c - a) // SCAN_STEP) + 1
        for q in sorted((a + k * SCAN_STEP for k in range(n)), key=lambda q: abs(q - p)):
            if all(abs(q - t) >= SPACING for t in taken):
                if best is None or abs(q - x) < abs(best - x):
                    best = q
                break
    return best if best is not None else fsm.win.rain.nearest_shelter_x(x, lo, hi, SHELTER_MARGIN)


class SeekShelter(State):
    name = "SeekShelter"
    tier = T_WARM
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self._exec = None
        self.cooldown = 0

    def enter(self):
        fsm = self.fsm
        fsm.gfx.sleeping = False
        fsm.body.sleeping = False
        fsm.gfx.sleep_curl = 0.0
        fsm.body.set_posture(True)
        fsm._clear_hands()
        fsm.climb = None
        self._exec = None
        x = shelter_x(fsm)
        if x is None:
            return
        fsm.social.claim(fsm.win, "shelter", Mark(x, fsm.win._HL), state=self.name)
        g = point_goal(x, fsm.win._HL, radius=ARRIVE)
        if not fsm.planner.stay_candidates(g):
            self.cooldown = RETRY
            return
        self._exec = PlanExecutor(fsm.win, fsm.planner, g, mode=MODE_STAY)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if self._exec is None or not fsm.win.rain.dangerous():
            self._stop()
            fsm.settle()
            return
        status = self._exec.update()
        if status == GIVEUP:
            self.cooldown = RETRY
            self._stop()
            fsm.settle()
        elif status == HOLDING:
            self._stop()
            fsm.settle()

    def brk(self):
        self._stop()
        if self.fsm.body.on_pole:
            release(self.fsm.body)

    def kill_break(self):
        self.brk()

    def _stop(self):
        fsm = self.fsm
        if self._exec is not None:
            self._exec.cancel()
            self._exec = None
        fsm.social.release(fsm.win, "shelter")
        fsm.release_organs()
        fsm.body.stop_walk()
        fsm.climb = None
