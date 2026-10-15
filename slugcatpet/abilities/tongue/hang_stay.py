"""舌吊驻留：在左墙、右墙、天花板、目标物四种锚点里挑代价最低的，吊在目标旁不动。"""

from __future__ import annotations
import math

from ... import tuning
from . import consts
from ...core.chunkphys import DIST_STAND
from ...core.units import clampf
from ...planning.reach import Reach, Estimate, RUNNING, GIVEUP, HOLD, walk_band
from .reach import mouth_pos, reset_tongue
from .aim import fire_at, tongue_of

WALL_ARRIVE = 12.0
ATTACH_TIMEOUT = 120
DROP_TIMEOUT = 200
DROP_ALIGN_EPS = 8.0
SETTLE_VX_EPS = 0.35  # 松手前横向速度要低于此值，免得被摆荡甩开
SETTLE_DX_EPS = 60.0  # 松手前离目标的水平距离要在此以内，免得停在摆动端点时误判到位
SETTLE_TIMEOUT = 400

_IDEALS = {
    "wall_l": consts.PLAN_HANG_WALL_IDEAL,
    "wall_r": consts.PLAN_HANG_WALL_IDEAL,
    "ceiling": consts.PLAN_HANG_CEIL_IDEAL,
    "entity": consts.PLAN_HANG_BULB_IDEAL,
}


def _anchor_kinds(goal):
    kinds = ["wall_l", "wall_r", "ceiling"]
    if goal.obj is not None:
        kinds.append("entity")
    return kinds


def _anchor_coord(pet, goal, kind):
    """锚点世界坐标，每 tick 按 goal.pos() 重算，跟着会动的目标走。"""
    gx, gy = goal.pos()
    if kind == "wall_l":
        return (0.0, gy)
    if kind == "wall_r":
        return (pet._WL, gy)
    if kind == "ceiling":
        return (gx, 0.0)
    return (gx, gy)


def _side_for(pet, goal, kind):
    """从哪面墙上去：墙锚就是那面墙，天花板和物体锚取近的一面。"""
    if kind == "wall_l":
        return -1
    if kind == "wall_r":
        return 1
    gx, _ = goal.pos()
    return -1 if gx < pet._WL * 0.5 else 1


def _settle_dist(pet, goal, kind):
    """吊稳后臀部离目标的估计距离，臀部约在锚点正下方 ideal + DIST_STAND 处。"""
    ax, ay = _anchor_coord(pet, goal, kind)
    sx, sy = ax, ay + _IDEALS[kind] + DIST_STAND
    gx, gy = goal.pos()
    return math.hypot(sx - gx, sy - gy)


def _cost(pet, goal, kind):
    gx, gy = goal.pos()
    ax, ay = _anchor_coord(pet, goal, kind)
    c0, c1 = pet.body.chunk0, pet.body.chunk1
    xmin, xmax = walk_band(pet)
    attach_t = consts.PLAN_HANG_ATTACH_TICKS
    en_l, en_v = tuning.PLAN_EN_RATE_LIGHT, tuning.PLAN_EN_RATE_VIGOROUS
    if kind in ("wall_l", "wall_r"):
        walk_t = abs(c1.x - clampf(ax, xmin, xmax)) / tuning.PLAN_WALK_SPEED
        climb_t = max(0.0, c0.y - ay) / tuning.PLAN_CLIMB_SPEED
        t = walk_t + climb_t + attach_t
        e = walk_t * en_l + climb_t * en_v + attach_t * en_l
        return Estimate(t, e)
    wall_x = 0.0 if gx < pet._WL * 0.5 else pet._WL
    walk_t = abs(c1.x - clampf(wall_x, xmin, xmax)) / tuning.PLAN_WALK_SPEED
    climb_t = c0.y / tuning.PLAN_CLIMB_SPEED
    traverse_t = abs(gx - wall_x) / tuning.PLAN_WALK_SPEED
    drop_t = (gy / tuning.PLAN_CLIMB_SPEED) if kind == "entity" else 0.0
    t = walk_t + climb_t + traverse_t + drop_t + attach_t
    e = walk_t * en_l + (climb_t + traverse_t) * en_v + drop_t * en_l + attach_t * en_l
    return Estimate(t, e)


def _best(pet, goal):
    r = goal.radius
    best = None
    for kind in _anchor_kinds(goal):
        if _settle_dist(pet, goal, kind) > r:
            continue
        est = _cost(pet, goal, kind)
        if best is None or est.time_est < best[1].time_est:
            best = (kind, est)
    return best


class TongueHangStay(Reach):
    key = "tonguehang"

    def can_touch(self, goal):
        return None

    def can_stay(self, goal):
        if tongue_of(self.pet) is None:
            return None
        b = _best(self.pet, goal)
        return None if b is None else b[1]

    def make_controller(self, goal):
        return TongueHangController(self.pet, goal)


class TongueHangController:
    def __init__(self, pet, goal):
        self.pet = pet
        self.goal = goal
        b = _best(pet, goal)
        self.kind = b[0] if b is not None else "entity"
        self.side = _side_for(pet, goal, self.kind)
        self.phase = "approach"
        self.climber = None
        self.reclimbs = 0
        self.timer = 0

    def update(self):
        if tongue_of(self.pet) is None:
            return GIVEUP
        ax, ay = _anchor_coord(self.pet, self.goal, self.kind)
        if self.phase == "approach":
            return self._approach(ax, ay)
        if self.phase == "attach":
            return self._attach(ax, ay)
        if self.phase == "settle":
            return self._settle()
        if self.phase == "drop":
            return self._drop()
        return self._hold()

    def _approach(self, ax, ay):
        pet = self.pet
        body = pet.body
        from .climb import TongueClimber

        if self.climber is None:
            wall_x = pet._WL if self.side > 0 else 0.0
            xmin, xmax = walk_band(pet)
            fx = clampf(wall_x, xmin, xmax)
            if body.on_floor() and abs(body.chunk1.x - fx) > WALL_ARRIVE:
                body.walk_to(fx)
                return RUNNING
            body.stop_walk()
            stop = (
                self.goal.radius * consts.PLAN_HANG_WALL_STOP_FRAC
                if self.kind in ("wall_l", "wall_r")
                else None
            )
            self.climber = TongueClimber(pet, self.side, target=(ax, ay), stop_dist=stop)
            return RUNNING
        self.climber.target = (ax, ay)
        done = self.climber.update()
        if self.climber.giveup:
            reset_tongue(pet)
            self.climber = None
            return self._retry()
        if done:
            self.climber = None
            if self.kind == "ceiling":
                self.phase = "hold"
            elif self.kind == "entity":
                self.phase = "settle"  # 先等摆荡平息再松手，否则会被甩开
                self.timer = 0
            else:
                self.phase = "attach"
                self.timer = 0
        return RUNNING

    def _attach(self, ax, ay):
        pet = self.pet
        tg = tongue_of(pet)
        self.timer += 1
        if tg.attached:
            tg.set_targets(ideal=consts.PLAN_HANG_WALL_IDEAL, reel_rate=consts.PLAN_HANG_REEL_RATE)
            self.phase = "hold"
            return RUNNING
        if tg.is_idle():
            mox, moy = mouth_pos(pet)
            if math.hypot(ax - mox, ay - moy) <= tg.total:
                tg.set_targets(
                    shoot_v=consts.PLAN_HANG_SHOOT_V,
                    ideal=consts.PLAN_HANG_WALL_IDEAL,
                    reel_rate=consts.PLAN_HANG_REEL_RATE,
                )
                fire_at(pet, ax, ay)
                return RUNNING
            if pet.body.on_floor():
                return self._retry()
        if self.timer > ATTACH_TIMEOUT:
            return self._retry()
        return RUNNING

    def _settle(self):
        """吊在天花板上，等对准目标且晃停了再松手；climber 完成只说明锚点对准了。"""
        pet = self.pet
        tg = tongue_of(pet)
        body = pet.body
        self.timer += 1
        if not tg.attached:
            return self._retry()
        tg.set_targets(ideal=consts.PLAN_HANG_CEIL_IDEAL, reel_rate=consts.PLAN_HANG_REEL_RATE)
        gx, _ = self.goal.pos()
        c0 = body.chunk0
        calm = abs(c0.vx) <= SETTLE_VX_EPS and abs(c0.x - gx) <= SETTLE_DX_EPS
        if calm or self.timer > SETTLE_TIMEOUT:
            reset_tongue(pet)
            body.release_to_air(move_dir=0)
            self.phase = "drop"
            self.timer = 0
        return RUNNING

    def _drop(self):
        pet = self.pet
        tg = tongue_of(pet)
        body = pet.body
        self.timer += 1
        gx, gy = self.goal.pos()
        if tg.attached:
            tg.set_targets(ideal=consts.PLAN_HANG_BULB_IDEAL, reel_rate=consts.PLAN_HANG_REEL_RATE)
            self.phase = "hold"
            return RUNNING
        if not body.on_floor():
            dx = gx - body.chunk0.x
            body.move_dir = 0 if abs(dx) < DROP_ALIGN_EPS else (1 if dx > 0 else -1)
        if tg.is_idle():
            mox, moy = mouth_pos(pet)
            if math.hypot(mox - gx, moy - gy) <= tg.total * 0.95:
                tg.set_targets(
                    shoot_v=consts.PLAN_HANG_SHOOT_V,
                    ideal=consts.PLAN_HANG_BULB_IDEAL,
                    reel_rate=consts.PLAN_HANG_REEL_RATE,
                )
                fire_at(pet, gx, gy)  # 钉在定点上不粘物体，免得弹簧把物体拽过来
                return RUNNING
            if body.on_floor():
                return self._retry()
        if self.timer > DROP_TIMEOUT:
            return self._retry()
        return RUNNING

    def _hold(self):
        pet = self.pet
        tg = tongue_of(pet)
        if not tg.attached or pet.body.on_floor():
            reset_tongue(pet)
            return self._retry()
        tg.set_targets(ideal=_IDEALS[self.kind], reel_rate=consts.PLAN_HANG_REEL_RATE)
        return HOLD

    def _retry(self):
        self.reclimbs += 1
        if self.reclimbs > consts.PLAN_HANG_MAX_RECLIMB:
            reset_tongue(self.pet)
            self.pet.body.stop_walk()
            return GIVEUP
        self.climber = None
        self.timer = 0
        self.phase = "approach"
        return RUNNING

    def cancel(self):
        reset_tongue(self.pet)
        self.pet.body.stop_walk()
        self.climber = None
