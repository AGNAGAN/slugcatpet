"""杆网够取：在杆网里找一条路线够到目标，并一步步走过去。"""

from __future__ import annotations

from .. import tuning
from .climbmap import locate, map_for
from .climbmoves import DONE as M_DONE
from .climbmoves import FAIL as M_FAIL
from .climbmoves import TouchFly, catch_in_air, make
from .reach import DONE, GIVEUP, RUNNING, Estimate, Reach

MAX_REPLANS = 4  # 跳歪、抓错杆后重新找路的次数
AIR_WAIT = 120  # 重新找路时人在空中，最多等这么久落定
PLAN_CACHE = 256
START_BUCKET = 40.0  # 从地上出发时按这么宽分桶复用路线
WAIT_WARM_PER_TICK = 8  # 等杆网算完时每 tick 帮着多算这么多个位置


class ClimbPathReach(Reach):
    key = "polepath"
    from_pole = True

    def __init__(self, pet):
        super().__init__(pet)
        self._last = {}  # 目标 → 上次现算的结果

    def _plan(self, goal, fresh=False):
        """够到 goal 的 (路线, 耗时)；fresh 时不受每 tick 的寻路额度限制。"""
        pet = self.pet
        b = pet.body
        if getattr(b, "zerog", False) or b.swimming:
            return None
        cm = map_for(pet)
        if not cm.bars or not cm.ready:
            return None  # 杆网刚变，后台还没算完
        start = locate(cm, pet)
        if start is None:
            return None
        gx, gy = goal.pos()
        where = (start[0], start[1], round(start[2] / START_BUCKET)) if start[0] == "F" else start
        rain = getattr(pet, "rain", None)
        rain = rain if rain is not None and rain.dangerous() else None
        key = (where, round(gx / 4.0), round(gy / 4.0), rain and rain.version)
        plans = cm.__dict__.setdefault("plans", {})
        if key not in plans:
            budget = getattr(pet, "_plan_budget", None)
            if not fresh and budget is not None and not budget.take_search():
                return self._last.get(goal.key())  # 这一 tick 额度满了，先按上次的结果答
            if len(plans) > PLAN_CACHE:
                plans.clear()
            plans[key] = cm.search(start, gx, gy, rain)
        if len(self._last) > PLAN_CACHE:
            self._last.clear()
        self._last[goal.key()] = plans[key]
        return plans[key]

    def can_touch(self, goal):
        res = self._plan(goal)
        if res is None:
            return None
        cost = res[1]
        return Estimate(cost, cost * tuning.PLAN_EN_RATE_VIGOROUS)

    def make_controller(self, goal):
        res = self._plan(goal, fresh=True)
        return ClimbController(self.pet, goal, map_for(self.pet), res[0] if res else [])


class ClimbController:
    """按路线一步步执行；跳歪了、抓错杆、动作失败时从当前位置重新找路。"""

    def __init__(self, pet, goal, cm, path):
        self.pet = pet
        self.goal = goal
        self.cm = cm
        self.path = list(path)
        self.i = 0
        self.move = None
        self.expect = None
        self.spot = locate(cm, pet)
        self.replans = 0
        self._wait = 0
        self._regrid = False

    def on_geometry(self):
        """杆网变了：做完这一步再重新找路；脚下的杆没了返回 False。"""
        if getattr(self.pet.body, "zerog", False):
            return False
        cm = map_for(self.pet)
        if cm is self.cm:
            return True
        alive = {id(b.obj) for b in cm.bars}
        on = self.cm.bars[self.spot[1]].obj if self.spot is not None and self.spot[1] >= 0 else None
        to = getattr(self.move, "bar", None)
        if (on is not None and id(on) not in alive) or (to is not None and id(to.obj) not in alive):
            return False
        self.cm = cm
        self.spot = locate(cm, self.pet)
        self.path, self.i = [], 0
        if self.move is None:
            self.move = _Wait(self)
        self._regrid = True
        return True

    def cross_x(self, bar, x):
        """竖杆和横杆交叉处的 x。"""
        b = self.pet.body
        px = getattr(b, "pole_x", x) if b.on_pole else x
        return min(max(px, bar.x0 + 2.0), bar.x1 - 2.0)

    def catch(self, skip):
        return catch_in_air(self, skip)

    def next_facing(self):
        """路线下一步往哪边走；看不出来 0。"""
        if self.i + 1 < len(self.path):
            act = self.path[self.i + 1][1]
            if act[0] in ("beamwalk", "shimmy"):
                d = act[2] - self.pet.body.chunk0.x
                return 0 if abs(d) < 1.0 else (1 if d > 0 else -1)
        return 0

    def update(self):
        if self.move is None:
            if self.i >= len(self.path):
                return self._path_end()
            self.expect, act = self.path[self.i]
            self.move = make(self, act)
        r = self.move.update()
        if r == RUNNING:
            return RUNNING
        mv, self.move = self.move, None
        if self._regrid:
            self._regrid = False
            self.spot = locate(self.cm, self.pet)
            return self._replan(count=False)
        if isinstance(mv, (_Wait, _WaitReady)):
            return self._replan(count=False)
        if r == M_FAIL:
            return self._replan(count=True)
        if isinstance(mv, TouchFly):
            return DONE
        caught = getattr(mv, "caught", None)
        actual = caught if caught is not None else locate(self.cm, self.pet)
        self.spot = actual
        self.i += 1
        if self._arrived_now():
            return DONE
        if r == M_DONE and actual == self.expect:
            return RUNNING
        same = actual is not None and self.expect is not None and actual[:2] == self.expect[:2]
        return self._replan(count=not same)

    def _replan(self, count):
        if count:
            self.replans += 1
            if self.replans > MAX_REPLANS:
                return GIVEUP
        start = locate(self.cm, self.pet)
        if start is None:
            self._wait += 1
            if self._wait > AIR_WAIT:
                return GIVEUP
            self.path, self.i = [], 0
            self.move = _Wait(self)
            return RUNNING
        self._wait = 0
        if not self.cm.ready:
            self.path, self.i = [], 0
            self.move = _WaitReady(self)
            return RUNNING
        res = self._search(start)
        if res is None:
            return GIVEUP
        self.path, self.i, self.spot = res[0], 0, start
        return RUNNING

    def _path_end(self):
        return GIVEUP  # 路走完了还没够着

    def _arrived_now(self):
        return False

    def _search(self, start):
        gx, gy = self.goal.pos()
        rain = getattr(self.pet, "rain", None)
        return self.cm.search(start, gx, gy, rain if rain is not None and rain.dangerous() else None)

    def cancel(self):
        """停下；还抓着杆就接着抓着，之后去哪由上层定。"""


class SpotController(ClimbController):
    """沿杆网走到指定位置，到了报 DONE 并留在那里。"""

    def __init__(self, pet, cm, target, path):
        super().__init__(pet, None, cm, path)
        self.target = target
        self._target_bar = cm.bars[target[1]].obj if target[1] >= 0 else None

    def arrived(self):
        s = locate(self.cm, self.pet)
        if s is None:
            return False
        t = self.target
        if t[0] == "F" and t[2] is None:
            return s[0] == "F"
        return s[:2] == t[:2] and abs(s[2] - t[2]) <= 1.0

    def _path_end(self):
        if self.arrived():
            return DONE
        return self._replan(count=True)

    def _arrived_now(self):
        return self.arrived()

    def _search(self, start):
        path = self.cm.route_to(start, self.target)
        return None if path is None else (path, 0.0)

    def on_geometry(self):
        ok = super().on_geometry()
        if ok and self.target[1] >= 0:
            # 按杆本身在新杆网里找回编号
            old = self._target_bar
            idx = next((j for j, b in enumerate(self.cm.bars) if b.obj is old), None)
            if idx is None:
                return False
            self.target = (self.target[0], idx, self.target[2])
        return ok


class _WaitReady:
    """杆网还没算完：原地等着，帮着多算一些。"""

    def __init__(self, nav):
        self.nav = nav

    def update(self):
        self.nav.cm.warm(WAIT_WARM_PER_TICK)
        return M_FAIL if self.nav.cm.ready else RUNNING


class _Wait:
    """在空中定不了位：等落定再找路。"""

    def __init__(self, nav):
        self.nav = nav

    def update(self):
        if locate(self.nav.cm, self.nav.pet) is not None:
            return M_FAIL
        self.nav._wait += 1
        return M_FAIL if self.nav._wait > AIR_WAIT else RUNNING
