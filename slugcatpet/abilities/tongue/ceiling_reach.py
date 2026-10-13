"""吊顶落体够取：吊顶横移到目标上方→松舌落体；代价最贵，作兜底。"""
from __future__ import annotations

from ... import tuning
from ...core.units import clampf
from ...planning.reach import Reach, Estimate, RUNNING, DONE, GIVEUP, reach_assist, walk_band
from ...planning.jump_arc import get_drop_arc

CEIL_RELEASE_Y = 50.0
CEIL_MARGIN = 20.0
CEIL_ALIGN_EPS = 8.0
CEIL_WALL_ARRIVE = 12.0


def _drop_ticks(arc, dy):
    """落体弧下落到相对深度 dy 所需 tick（首个 py≥dy），无则采样长度。"""
    for i, (px, py) in enumerate(arc.points):
        if py >= dy:
            return i + 1
    return len(arc.points)


class CeilingDropReach(Reach):
    key = "ceildrop"

    def _feasible(self, goal):
        pet = self.pet
        if pet.tongue is None:
            return None
        gx, gy = goal.pos()
        if not (CEIL_MARGIN <= gx <= pet._WL - CEIL_MARGIN):
            return None
        if gy <= CEIL_RELEASE_Y:
            return None
        return gx, gy

    def can_touch(self, goal):
        f = self._feasible(goal)
        if f is None:
            return None
        gx, gy = f
        pet = self.pet
        stats = pet.cat.stats
        side_x = 0.0 if gx < pet._WL * 0.5 else pet._WL
        climb_t = pet._HL / tuning.PLAN_CLIMB_SPEED
        traverse_t = abs(gx - side_x) / tuning.PLAN_WALK_SPEED
        drop_t = _drop_ticks(get_drop_arc(stats, 0), gy - CEIL_RELEASE_Y)
        t = climb_t + traverse_t + drop_t + 2.0 * tuning.PLAN_STARTUP_TICKS
        e = ((climb_t + traverse_t) * tuning.PLAN_EN_RATE_VIGOROUS
             + drop_t * tuning.PLAN_EN_RATE_LIGHT)
        return Estimate(t, e)

    def make_controller(self, goal):
        return CeilingDropController(self.pet, goal)


class CeilingDropController:

    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        self.climber = None
        self.phase = "approach"
        self._side = 1
        self._airborne = False

    def update(self):
        pet = self.pet
        body = pet.body
        gx, gy = self.goal.pos()
        if pet.tongue is None:
            return GIVEUP
        if self.phase == "approach":
            self._side = -1 if gx < pet._WL * 0.5 else 1
            wall_x = 0.0 if self._side < 0 else pet._WL
            xmin, xmax = walk_band(pet)
            fx = clampf(wall_x, xmin, xmax)
            if body.on_floor() and abs(body.chunk1.x - fx) <= CEIL_WALL_ARRIVE:
                self.phase = "hang"
            else:
                body.walk_to(fx)
            return RUNNING
        if self.phase == "hang":
            if self.climber is None:
                from .climb import TongueClimber
                self.climber = TongueClimber(pet, self._side, target=(gx, 0.0))
            self.climber.target = (gx, 0.0)
            if self.climber.update():                 # True=已吊顶且锚点对准
                from .reach import reset_tongue
                reset_tongue(pet)
                body.release_to_air(move_dir=0)
                self.phase = "air"
            elif self.climber.giveup:
                return GIVEUP
            return RUNNING
        reach_assist(pet, self.goal, gx, gy)
        if not body.on_floor():
            self._airborne = True
            dx = gx - body.chunk0.x
            body.move_dir = 0 if abs(dx) < CEIL_ALIGN_EPS else (1 if dx > 0 else -1)
        elif self._airborne:
            body.stop_walk()
            return DONE
        return RUNNING

    def cancel(self):
        if self.climber is not None:
            from .reach import reset_tongue
            reset_tongue(self.pet)
            self.climber = None
        self.pet.body.stop_walk()
