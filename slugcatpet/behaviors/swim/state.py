"""内置行为状态：游泳。"""

from __future__ import annotations

import math

from ... import tuning
from ...brain.state import EN_REC_IDLE, T_BODY, VIGOROUS, State
from ...brain.skills.motor import WALL_MARGIN


class Swimming(State):
    name = "Swimming"
    depth_max = 0.0  # 漂游最大深度（挂载时按性格设）
    tier = T_BODY
    energy = VIGOROUS

    def energy_delta(self, drain_fac):
        b = self.fsm.body
        if b.swim_resting:
            return EN_REC_IDLE * tuning.SWIM_REST_ENERGY_REC_FAC
        if b.swim_mode == "surface":
            return EN_REC_IDLE * tuning.SWIM_SURFACE_REST_FAC
        return super().energy_delta(drain_fac)

    def __init__(self, fsm):
        super().__init__(fsm)
        self._swim_goal = None
        self._swim_hold = 0

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(False)
        b.stop_walk()
        self._swim_goal = None
        self._swim_hold = 0

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        if not b.swimming:
            b.swim_target = None
            b.swim_resting = False
            fsm.settle()
            return
        fsm.gfx.look_at = fsm._ambient_look(cursor)
        ws = getattr(b, "water_surface", None)
        self._update_rest(ws)
        if b.air_frac < b.stats.drown_threshold and ws is not None:
            b.swim_target = (b.chunk0.x, ws.level_at(b.chunk0.x) - 20.0)
            return
        if b.swim_resting:
            b.swim_target = (b.chunk0.x, ws.level_at(b.chunk0.x) - tuning.SWIM_REST_ABOVE)
            return
        if fsm.run_tasks("swim"):
            return
        if self._swim_hold > 0:
            self._swim_hold -= 1
            b.swim_target = (b.chunk0.x, b.chunk0.y - 4.0)
            return
        g = self._swim_goal
        if g is not None and self._swim_reached(g):
            self._swim_goal = None
            self._swim_hold = fsm.rng.randint(tuning.SWIM_IDLE_HOLD_MIN, tuning.SWIM_IDLE_HOLD_MAX)
            b.swim_target = (b.chunk0.x, b.chunk0.y - 4.0)
            return
        if g is None:
            g = self._pick_swim_target(cursor, ws)
            self._swim_goal = g
        b.swim_target = g

    def brk(self):
        fsm = self.fsm
        fsm.body.swim_target = None
        fsm.body.swim_resting = False

    def _update_rest(self, ws):
        b = self.fsm.body
        if ws is None:
            b.swim_resting = False
        elif b.swim_resting:
            if b.energy > tuning.SWIM_REST_ENERGY_OUT and b.air_frac > 0.75:
                b.swim_resting = False
        elif b.energy < tuning.SWIM_REST_ENERGY_IN or b.air_frac < b.stats.drown_threshold:
            b.swim_resting = True

    def _pick_swim_target(self, cursor, ws):
        fsm = self.fsm
        if fsm.body.no_dive:
            x = fsm.rng.uniform(WALL_MARGIN, fsm.WL - WALL_MARGIN)
            if cursor is not None and fsm.rng.random() < 0.4:
                x = min(max(float(cursor[0]), WALL_MARGIN), fsm.WL - WALL_MARGIN)
            y = ws.level_at(x) - 8.0 if ws is not None else fsm.HL - WALL_MARGIN
            return (x, min(y, fsm.HL - WALL_MARGIN))
        if cursor is not None and fsm.rng.random() < 0.4:
            return (float(cursor[0]), float(cursor[1]))
        x = fsm.rng.uniform(WALL_MARGIN, fsm.WL - WALL_MARGIN)
        if ws is not None:
            y = ws.level_at(x) + fsm.rng.uniform(tuning.SWIM_DRIFT_DEPTH_MIN, self.depth_max)
            y = min(y, fsm.HL - WALL_MARGIN)
        else:
            y = fsm.rng.uniform(WALL_MARGIN, fsm.HL - WALL_MARGIN)
        return (x, y)

    def _swim_reached(self, g):
        fsm = self.fsm
        return math.hypot(g[0] - fsm.body.chunk0.x, g[1] - fsm.body.chunk0.y) < tuning.SWIM_ARRIVE_R
