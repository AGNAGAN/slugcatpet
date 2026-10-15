"""竖杆攀爬控制器：走到杆下抓住，爬上杆尖站着；update() 返回 True 结束。"""

from __future__ import annotations

from ...planning.climbmoves import attach_vertical, climb_tick, release, tip_step, tip_up_tick

ARRIVE_EPS = 26.0
APPROACH_TIMEOUT = 400
CLIMB_TIMEOUT = 1200
HELD_GIVEUP = 120  # 被杆上别的猫挡住这么久就爬回去
STEP_OFF_H = 34.0  # 往回爬到臀离地这么近再下杆
FALL_PUSH = 3.5  # 从杆尖掉下时的横向速度


class _Pole:
    """竖杆物件的杆上动作视图。"""

    def __init__(self, pole):
        self.obj = pole
        self.x = pole.x
        self.y0 = pole.top_y


class PoleClimber:
    def __init__(self, win, pole):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.pole = pole
        self.bar = _Pole(pole)
        self.phase = "approach"
        self.timer = 0
        self.giveup = False
        self.social = win.social

    def update(self, want_dismount=False):
        self.timer += 1
        b = self.body
        c1 = b.chunk1

        if self.phase == "approach":
            b.walk_to(self.pole.x)
            if abs(c1.x - self.pole.x) < ARRIVE_EPS and c1.on_floor:
                b.stop_walk()
                attach_vertical(b, self.bar, 1 if b.chunk0.x >= self.pole.x else -1)
                self.phase = "climb"
            elif self.timer > APPROACH_TIMEOUT:
                self.giveup = True
                return True
            return False

        if self.phase == "back":
            if self.win._HL - c1.y < STEP_OFF_H:
                self.giveup = True
                self.release()
                return True
            climb_tick(b, self.bar, -1, clamp=False)
            return False

        if self.phase == "climb":
            if self.social.traffic.held.get(self.win, 0) > HELD_GIVEUP:
                self.phase = "back"
                return False
            r = tip_up_tick(b, self.bar)
            if r is None:
                self._reset_pose()
                return True
            if r:
                self.pole.has_been_climbed = True
                self.phase = "tip"
            elif self.timer > CLIMB_TIMEOUT:
                self.giveup = True
                self.release()
                return True
            return False

        if self.phase == "tip":
            if not tip_step(b, self.bar):
                self._fall(1.0 if b.chunk0.x >= self.pole.x else -1.0)
                return True
        return False

    def _fall(self, side):
        b = self.body
        release(b)
        b.chunk0.vx += side * FALL_PUSH
        b.chunk1.vx += side * FALL_PUSH * 0.4
        self._reset_pose()

    def _reset_pose(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    def release(self):
        release(self.body)
        self._reset_pose()
