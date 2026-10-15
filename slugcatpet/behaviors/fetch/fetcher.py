"""取果：选果和够取交给规划层，接触抓取、叼回、啃食在这里。"""

from __future__ import annotations
import math

from ... import tuning
from ...planning import GIVEUP, PlanExecutor, obj_goal
from ...planning.climbmap import locate, map_for
from ...planning.climbmoves import hold_tick
from ...characters.personality import NEUTRAL
from ...core.vecmath import _dist
from ...items.base import EDIBLE
from .chew import Chew

CARRY_FALL_TIMEOUT = 200

_EDIBLE_STATES = ("free", "hanging")


def _seg_point_dist(ax, ay, bx, by, px, py):
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    if d2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / d2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _edible_goal(obj):
    return obj_goal(obj, valid=lambda o: o.state in _EDIBLE_STATES, contact="grasp")


def fetch_candidates(planner, edibles, traits=NEUTRAL):
    """选果候选：可达且不冷却的 (obj, goal, 预估耗时)，按耗时升序。"""
    out = []
    for f in edibles:
        if f.state not in _EDIBLE_STATES:
            continue
        if not getattr(f, "fetch_ready", True):
            continue  # 飞行中蝙蝠够不到
        if not traits.eats(f):
            continue
        g = _edible_goal(f)
        if planner.in_cooldown(g):
            continue
        cands = planner.touch_candidates(g)
        if cands:
            out.append((f, g, traits.food_time(f, cands[0].time_est)))
    out.sort(key=lambda item: item[2])
    return out


def fetch_ready(planner, edibles, traits=NEUTRAL):
    """fetch_candidates 的简化版，只返回够得着的东西，给触发判断用。"""
    out = []
    for f in edibles:
        if f.state not in _EDIBLE_STATES:
            continue
        if not getattr(f, "fetch_ready", True):
            continue
        if not traits.eats(f):
            continue
        g = _edible_goal(f)
        if planner.in_cooldown(g):
            continue
        if planner.any_touch(g):
            out.append(f)
    return out


class _NoAssist:
    def update(self, goal):
        pass

    def abort(self):
        pass

    def reset(self):
        pass

    def holding(self):
        return False


def _fetch_assist(pet):
    return pet.skill("fetch_assist") or _NoAssist()


class FruitFetcher:
    """keep=True 时拿到落地就收工（留着待会儿吃），否则拿到就吃。"""

    def __init__(self, win, planner, traits=NEUTRAL, keep=False, hands=None, state="FetchFruit"):
        self.win = win
        self.state = state  # 占用登记在哪个状态名下
        self.body = win.body
        self.planner = planner
        self.traits = traits
        self.keep = keep
        self.hands = hands

        self.target = None
        self.phase = "select"
        self.giveup = False
        self.timer = 0
        self.grab_side = "r"
        self.chew = Chew()
        self._hold = None  # 在杆上吃时抓着的 (杆, 姿势)
        self._executor = None
        self._giveup_pending = False
        self._goal = None
        self._snatch = _fetch_assist(win)
        self.social = win.social

    def _chunk0(self):
        return self.body.chunk0

    def _grab_dist(self):
        f = self.target
        c0 = self._chunk0()
        d = _seg_point_dist(c0.last_x, c0.last_y, c0.x, c0.y, f.x, f.y)
        hx, hy = self.body._carry_pos(self.grab_side)
        d = min(d, _dist(hx, hy, f.x, f.y))
        return d

    def _try_grab(self):
        side = self.body.free_hand(self.grab_side)
        if side is not None and self._grab_dist() < tuning.GRAB_REACH:
            if getattr(self.target, "stuck_pos", None) is not None:
                self.target.stuck_pos = None  # 抓取瞬间剥离黏菌
            self.body.grab(self.target, side)
            self.social.release(self.win, "food")
            self.phase = "grabbed"
            self.timer = 0
            return True
        return False

    def _pick_grab_side(self):
        return "r" if self.target.x >= self._chunk0().x else "l"

    def _drop_executor(self):
        if self._executor is not None:
            self._executor.cancel()
            self._executor = None

    def release(self):
        self._snatch.abort()
        self._drop_executor()
        self.chew.stop(self.body)
        self.social.release(self.win, "food")

    def _free(self):
        hands = self.hands
        return [
            f
            for f in self.win.items_affording(EDIBLE)
            if self.social.free_for(self.win, f)
            and (hands is None or not hands.forbidden(f))
            and not self.win.rain.keeps_out(f.x, f.y)
            and not (self.keep and getattr(f, "carcass", False))
        ]

    def start_with(self, f):
        """手里已经有吃的：落地就开吃。"""
        self.target = f
        self.grab_side = self.body.hand_of(f)
        self.phase = "carry_fall"
        self.timer = 0

    def update(self) -> bool:
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return True
        return m()

    def _phase_select(self):
        cands = fetch_candidates(self.planner, self._free(), self.traits)
        if not cands:
            self.giveup = self._giveup_pending
            return True
        self.target, goal, _ = cands[0]
        self.social.claim(self.win, "food", self.target, self.state)
        self.grab_side = self._pick_grab_side()
        self._giveup_pending = False
        self._goal = goal
        self._snatch.reset()
        self._executor = PlanExecutor(self.win, self.planner, goal)
        self.timer = 0
        self.phase = "approach"
        return False

    def _phase_approach(self):
        f = self.target
        if f.state not in _EDIBLE_STATES or self.social.taken(self.win, f):
            self._snatch.abort()
            self._drop_executor()
            self.phase = "select"
            return False
        self.grab_side = self._pick_grab_side()
        if self._try_grab():
            self._snatch.abort()
            self._drop_executor()
            return False
        self._snatch.update(self._goal)
        if self._snatch.holding():
            # 补救的舌头还粘着时不推进执行器，免得它直接收舌
            return False
        if self._executor.update() == GIVEUP:
            self._snatch.abort()
            self._executor = None
            self.target = None
            self._giveup_pending = True
            self.phase = "select"
        return False

    def held_target(self):
        """抓到手里的目标；不在手里返回 None。"""
        return self.target if self.body.hand_of(self.target) is not None else None

    def _phase_grabbed(self):
        """抓到后停一 tick 再开吃（在空中就先落地）。"""
        self.phase = "carry_fall"
        self.timer = 0
        return False

    def _phase_carry_fall(self):
        f = self.held_target()
        if f is None:
            self.phase = "select"
            return False
        # 挂在果柄上悬空太久就扯断果柄
        if self.timer > CARRY_FALL_TIMEOUT and f.stalk is not None:
            f.stalk = None
        perch = self._perch()
        if perch is not None:
            hold_tick(self.body, *perch)
        if self.body.on_floor() or perch is not None:
            if self.keep:
                return True
            self._hold = perch
            self.phase = "eat"
            self.timer = 0
            self.chew.reset()
        return False

    def _perch(self):
        """在杆上：(杆, 姿势)；不在杆上 None。"""
        if not self.body.on_pole:
            return None
        cm = map_for(self.win)
        here = locate(cm, self.win)
        if here is None or here[0] == "F":
            return None
        return cm.bars[here[1]], here[0]

    def _phase_eat(self):
        f = self.held_target()
        if f is None:
            self.phase = "select"
            return False
        b = self.body
        if self._hold is not None and b.on_pole:
            hold_tick(b, *self._hold)
        else:
            b.stop_walk()
            b.move_dir = 0
        if self.chew.step(self.win, f):
            if self.body.food >= self.body.food_max:
                return True
            self.phase = "select"
            self.timer = 0
        return False
