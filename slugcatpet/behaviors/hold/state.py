"""定身状态：原地保持姿势，只留看向、眨眼、呼吸和尾巴。"""

from __future__ import annotations

from ...brain.state import T_HOLD, State
from ...planning.climbmap import locate, map_for
from ...planning.climbmoves import hold_tick, release

STAND, LIE, SLEEP = "stand", "lie", "sleep"
CURSOR, AROUND, LOCK = "cursor", "around", "lock"
ZEROG_DAMP = 0.85  # 失重没抓杆时每 tick 保留的速度比例
LOCK_DIST = 200.0  # 锁定朝向时注视点离头的距离


class HoldSpec:
    """定身设置：姿势 pose（None 为进入时按身体推断）、视线 gaze、锁定的视线方向 lock。"""

    def __init__(self):
        self.pose = None
        self.gaze = CURSOR
        self.lock = None


def pole_spot(fsm):
    """抓着的杆和姿势 (bar, kind)；不在杆上 None。"""
    if not fsm.body.on_pole:
        return None
    cm = map_for(fsm.win)
    here = locate(cm, fsm.win)
    if here is None or here[0] == "F":
        return None
    return cm.bars[here[1]], here[0]


class Hold(State):
    name = "Hold"
    tier = T_HOLD
    needs = False

    def __init__(self, fsm):
        super().__init__(fsm)
        self.spot = None  # 打断前记下的杆上位置

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        spot, self.spot = self.spot, None
        fsm.release_organs()
        b.stop_walk()
        spec = fsm.win.held
        if spec.pose is None:
            spec.pose = SLEEP if b.sleeping else (STAND if b.standing else LIE)
        self.bar = self.kind = None
        if spot is None and b.on_pole:
            spot = pole_spot(fsm)
            if spot is None:
                release(b)
        if spot is not None:
            self.bar, self.kind = spot
            hold_tick(b, self.bar, self.kind)  # 前一状态收尾时可能松了杆

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        spec = fsm.win.held
        if spec is None:
            self._leave()
            return
        if b.swimming:
            fsm._transition("Swimming")
            return
        self._look(spec, cursor)
        if self.bar is not None:
            if b.on_pole:
                hold_tick(b, self.bar, self.kind)
                return
            self.bar = None
        if b.zerog:
            if b.zerog_pole is not None:
                b.zerog_pole_intent = (0.0, 0.0)
            else:
                for c in (b.chunk0, b.chunk1):
                    c.vx *= ZEROG_DAMP
                    c.vy *= ZEROG_DAMP
            return
        b.stop_walk()
        b.set_posture(spec.pose == STAND)
        if spec.pose == SLEEP:
            fsm.gfx.sleeping = b.sleeping = True

    def _look(self, spec, cursor):
        fsm = self.fsm
        g = fsm.gfx
        if spec.gaze == CURSOR:
            g.look_at = cursor
        elif spec.gaze == AROUND:
            g.look_at = fsm._ambient_look(cursor)
        else:
            if spec.lock is None:
                spec.lock = g.look_dir
            dx, dy = spec.lock
            g.look_at = (g.head.x + dx * LOCK_DIST, g.head.y + dy * LOCK_DIST) if dx or dy else None

    def _leave(self):
        """解除：趴着、睡着的先起身。"""
        fsm = self.fsm
        b = fsm.body
        if self.bar is None and b.on_floor() and not b.standing and "WakeSequence" in fsm._states:
            fsm._transition("WakeSequence")
        else:
            fsm.settle()
