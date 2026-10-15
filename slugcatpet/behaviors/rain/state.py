"""躲雨：走到最近的有遮挡的地面上。"""

from __future__ import annotations

from ...brain.state import LIGHT, T_WARM, State
from ...planning import GIVEUP, HOLDING, MODE_STAY, PlanExecutor, point_goal
from ...planning.climbmoves import release
from ...world.rain import SHELTER_MARGIN

ARRIVE = 12.0
RETRY = 200  # 走不过去后多久再试


def exposed(fsm) -> bool:
    rain = fsm.win.rain
    b = fsm.body
    return rain.exposed(b.chunk0.x, b.chunk0.y) or rain.exposed(b.chunk1.x, b.chunk1.y)


def shelter_x(fsm):
    b = fsm.body
    lo = 0.0 if b.walk_min is None else b.walk_min
    hi = fsm.WL if b.walk_max is None else b.walk_max
    return fsm.win.rain.nearest_shelter_x(b.chunk1.x, lo, hi, SHELTER_MARGIN)


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
        fsm.release_organs()
        fsm.body.stop_walk()
        fsm.climb = None
