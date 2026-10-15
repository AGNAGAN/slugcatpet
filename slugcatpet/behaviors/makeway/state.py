"""让路状态：让别的猫过去。"""

from __future__ import annotations

from ...brain.social.traffic import CONTACT
from ...brain.state import LIGHT, T_ACTIVITY, State
from ...planning.climbmap import locate, map_for
from ...planning.climbmoves import PullUpMotion, SwingUnderMotion, climb_tick, release, tip_up_tick

LIE_MIN = 36  # 趴下至少趴这么久
LIE_HASTE = 2.0  # 让路时趴下比平时快这么多倍
TIMEOUT = 300
STEP_OFF_H = 34.0  # 竖杆上臀离地这么近就下到地上
CALM = 15  # 竖杆上对方这么久不再逼近才算让完
CROSS_VX = 0.5  # 对方横向速度超过此值才算正从身上跨过


class MakeWay(State):
    name = "MakeWay"
    tier = T_ACTIVITY
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self.kind = None
        self.by = None  # 要过去的那只
        self.dir = 0  # 它在通道上的去向
        self.bar = None
        self.motion = None
        self.calm = 0

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        o = fsm.social.order(fsm.win)
        self.kind, self.by, self.dir = o.kind, o.by, o.dir
        self.bar = self.motion = None
        self.calm = 0
        if self.kind == "lie":
            b.stop_walk()
            b.set_posture(False)
            b.lie_haste = LIE_HASTE
            return
        if self.kind == "stop":
            self._done()
            return
        cm = map_for(fsm.win)
        here = locate(cm, fsm.win)
        if here is None or here[0] not in ("H", "S", "V") or (self.kind == "clear") != (here[0] == "V"):
            self.kind = None  # 已经不在下指令时的那条通道上
            return
        self.bar = cm.bars[here[1]]
        if self.kind == "swap":
            if here[0] == "H":
                self.motion = PullUpMotion(b, self.bar, b.facing or 1)
            else:
                self.motion = SwingUnderMotion(b, self.bar)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        o = fsm.social.order(fsm.win)
        if o is not None:
            self.by, self.dir = o.by, o.dir
        ob = self.by.body
        fsm.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
        if self.kind is None or fsm.timer > TIMEOUT:
            self._done()
        elif self.kind == "lie":
            self._lie(o, ob)
        elif self.kind == "swap":
            if self.motion.step() is not False:
                self._done()
        else:
            self._clear(o)

    def _lie(self, o, ob):
        """趴着等对方走过去；对方正从身上跨过时不起来。"""
        b = self.fsm.body
        b.move_dir = 0
        if self.dir:
            b.facing = self.dir
        crossing = not ob.on_pole and abs(ob.chunk1.vx) > CROSS_VX
        over = crossing and abs(ob.chunk1.x - b.chunk1.x) < CONTACT["F"]
        if o is None and not over and self.fsm.timer >= LIE_MIN:
            self._done()

    def _clear(self, o):
        """顺着竖杆往对方去的方向挪：往上到顶杆尖空着就站上去，往下到底就下到地上。"""
        fsm = self.fsm
        b = fsm.body
        if b.animation == "GetUpToBeamTip" or (
            self.dir < 0 and b.chunk0.y <= self.bar.lo + 1.0 and fsm.social.traffic.tip_free(fsm.win)
        ):
            if tip_up_tick(b, self.bar) is not False:
                self._done()
            return
        if o is None:
            climb_tick(b, self.bar, 0)
            self.calm += 1
            if self.calm > CALM:
                self._done()
            return
        self.calm = 0
        if self.dir > 0 and fsm.HL - b.chunk1.y < STEP_OFF_H:
            release(b)
            fsm.settle()
            return
        climb_tick(b, self.bar, -self.dir)

    def _done(self):
        self.fsm.settle()

    def brk(self):
        b = self.fsm.body
        if b.on_pole:
            release(b)
