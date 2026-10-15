"""爬架状态：走到落脚点待着，再换地方或下来。"""

from __future__ import annotations

import math

from ... import tuning
from ...brain.state import EN_DRAIN_LIGHT, EN_DRAIN_VIGOROUS, EN_REC_IDLE, LIGHT, T_IDLE, State
from ...planning.climb_reach import SpotController
from ...planning.climbmap import locate, map_for
from ...planning.climbmoves import release
from ...planning.reach import DONE, GIVEUP
from .choose import Mark, pick
from .dwell import Dwell

FLOOR = ("F", -1, None)
JUMP_DOWN_VY = 2.0  # 从杆上跳下时的下压速度
TIRED_ON_ARMS = 0.25  # 吊着、爬着时体力低于这里就下来
FLOOR_INTENTS = ("hang", "play", "sleep", "rest", "hunt", "warm")  # 下来以后能做的事
POLE_INTENTS = ("eat",)  # 在杆上就地能做的事


class Perch(State):
    name = "Perch"
    tier = T_IDLE  # 别的猫要过时让得开
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self.want = None  # 去爬架的意愿，由行为挂上
        self._reset()

    def _reset(self):
        self.phase = None
        self.ctl = None
        self.dwell = None
        self.bar = None
        self.left = 0
        self.rounds = 0  # 这一趟已经待了几处
        self.gv = None  # 上次看到的杆网版本
        self.stuck = False  # 这里没有不吓人的路下去

    def energy_delta(self, drain_fac):
        if self.phase in ("travel", "down"):
            return -EN_DRAIN_VIGOROUS * 0.5 * drain_fac
        if self.dwell is not None and self.dwell.kind in ("H", "V"):
            return -EN_DRAIN_LIGHT * drain_fac
        return EN_REC_IDLE

    def enter(self):
        fsm = self.fsm
        fsm.gfx.hand_aim["l"] = fsm.gfx.hand_aim["r"] = None
        self._reset()
        self.gv = getattr(fsm.win, "geometry_version", 0)
        cm = map_for(fsm.win)
        here = locate(cm, fsm.win)
        if here is not None and here[0] != "F":
            self._dwell_at(cm, here)  # 已经在杆上
        elif not self._choose(cm, here):
            self._leave()

    def _choose(self, cm, here, bar=None, exclude=None):
        fsm = self.fsm
        if here is None:
            return False
        res = pick(fsm, cm, here, bar, exclude)
        if res is None or res[1] is None:
            return False
        spot, path = res
        hx, hy = cm.head(spot)
        fsm.social.claim(fsm.win, "perch", Mark(hx, hy), "Perch")
        self.ctl = SpotController(fsm.win, cm, spot, path)
        self.phase = "travel"
        if self.dwell is not None:
            self.dwell.done()
            self.dwell = None
        return True

    def _dwell_at(self, cm, spot):
        fsm = self.fsm
        self.ctl = None
        self.bar = cm.bars[spot[1]]
        self.dwell = Dwell(fsm, self.bar, spot)
        hx, hy = cm.head(spot)
        fsm.social.claim(fsm.win, "perch", Mark(hx, hy), "Perch")
        k = 0.5 if spot[0] in ("H", "V") else 1.0
        self.left = int(fsm.rng.randint(tuning.PERCH_DWELL_MIN, tuning.PERCH_DWELL_MAX) * k)
        self.phase = "dwell"
        self.rounds += 1
        self.stuck = False

    def _geometry_ok(self):
        """杆网变了：接着走或换成同一根杆；脚下的杆没了返回 False。"""
        gv = getattr(self.fsm.win, "geometry_version", 0)
        if gv == self.gv:
            return True
        self.gv = gv
        if self.phase in ("travel", "down"):
            return self.ctl.on_geometry()
        if self.dwell is not None:
            bar = next((b for b in map_for(self.fsm.win).bars if b.obj is self.bar.obj), None)
            if bar is None:
                return False
            self.bar = self.dwell.bar = bar
        return True

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if not self._geometry_ok():
            self._leave()
            return
        if self.phase in ("travel", "down"):
            r = self.ctl.update()
            if r == DONE:
                if self.phase == "down":
                    self._leave()
                    return
                cm = self.ctl.cm
                here = locate(cm, fsm.win)
                if here is None or here[0] == "F":
                    self._leave()
                    return
                self._dwell_at(cm, here)
            elif r == GIVEUP:
                self._hold_on()
            return
        if self.phase != "dwell":
            self._leave()
            return
        self.dwell.step(cursor)
        if self.dwell.fell:
            self._release()
            fsm.settle()
            return
        self.left -= 1
        tired = self.dwell.kind in ("H", "V") and fsm.body.energy < TIRED_ON_ARMS
        if self.left <= 0 or (tired and not self.stuck):
            self._decide(tired)

    def _decide(self, tired):
        """待够了：换个地方，或者下来做地上最想做的事。"""
        fsm = self.fsm
        u = fsm.intents.utilities()
        options = {
            "move": 0.0
            if tired
            else (self.want() if self.want is not None else 0.0) * tuning.PERCH_BORED**self.rounds,
            "down": max(u.get(k, 0.0) for k in FLOOR_INTENTS) + (1.0 if tired else 0.0),
        }
        for k in POLE_INTENTS:
            options[k] = u.get(k, 0.0)
        top = max(options.values())
        w = {k: math.exp((v - top) / tuning.INTENT_TEMP) for k, v in options.items()}
        r = fsm.rng.random() * sum(w.values())
        choice = "down"
        for k, wk in w.items():
            r -= wk
            if r <= 0.0:
                choice = k
                break
        if choice in POLE_INTENTS and fsm.intents.start(choice):
            return
        cm = map_for(fsm.win)
        here = locate(cm, fsm.win)
        if choice == "move" and here is not None:
            if fsm.rng.random() < tuning.PERCH_NEARBY and self._choose(cm, here, here[1], here):
                return
            if self._choose(cm, here, exclude=here):
                return
        self._go_down(cm, here)

    def _go_down(self, cm, here):
        """沿杆网下到地上；没有不吓人的路就接着待着。"""
        fsm = self.fsm
        if here is None:
            self._let_go()
            return
        path = cm.route_to(here, FLOOR)
        if path is None:
            self.left = fsm.rng.randint(tuning.PERCH_DWELL_MIN, tuning.PERCH_DWELL_MAX)
            self.stuck = True
            return
        if self.dwell is not None:
            self.dwell.done()
            self.dwell = None
        self.ctl = SpotController(fsm.win, cm, FLOOR, path)
        self.phase = "down"

    def _let_go(self):
        b = self.fsm.body
        standing = b.animation in ("StandOnBeam", "BeamTip")
        self._release()
        if standing:
            b.chunk0.vy += JUMP_DOWN_VY
            b.chunk1.vy += JUMP_DOWN_VY
            b.chunk0.vx += (b.facing or 1) * 1.0
        self.fsm.settle()

    def _hold_on(self):
        """路走不通：还抓着杆就原地待着，否则落下。"""
        cm = map_for(self.fsm.win)
        here = locate(cm, self.fsm.win)
        if self.fsm.body.on_pole and here is not None and here[0] != "F":
            self._dwell_at(cm, here)
        else:
            self._leave()

    def _leave(self):
        fsm = self.fsm
        self._release()
        fsm.settle()

    def _release(self):
        fsm = self.fsm
        if self.dwell is not None:
            self.dwell.done()
        fsm.social.release(fsm.win, "perch")
        b = fsm.body
        if b.on_pole:
            release(b)
        self._reset()

    def brk(self):
        self._release()

    def kill_break(self):
        self._release()
