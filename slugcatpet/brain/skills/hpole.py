"""上横杆控制器：抓杆、吊着、翻上去、站着；update() 返回 True 结束。"""

from __future__ import annotations

import math

from ...planning.climbmoves import PullUpMotion, hang_tick, release, stand_tick

RUNNING, GRIP, GIVEUP = "running", "grip", "giveup"  # hpole_mount.update(锚点) 的返回值

GRIP_DIST = 16.0
HANG_TICKS = 28
STAND_TICKS = 200
WALK_MARGIN = 14.0
JUMP_DOWN_VY = 2.0
AIRGRAB_TIMEOUT = 90


class _Beam:
    """横杆物件的杆上动作视图。"""

    def __init__(self, pole):
        self.obj = pole
        self.x0, self.x1 = min(pole.ax, pole.bx), max(pole.ax, pole.bx)
        self.y = pole.ay
        self.lo, self.hi = self.x0 + WALK_MARGIN, self.x1 - WALK_MARGIN


class HPoleController:
    def __init__(self, win, pole, rng=None):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.mount = win.skill("hpole_mount")
        self.pole = pole
        self.bar = _Beam(pole)
        self.rng = rng
        self.phase = "mount" if self.mount is not None else "airgrab"
        self.timer = 0
        self.giveup = False
        lo, hi = self.bar.x0, self.bar.x1
        if self.mount is not None:
            ax = self.mount.anchor_x((lo + hi) * 0.5)
        else:
            ax = self.body.chunk0.x
        self._anchor = (max(lo + 2.0, min(hi - 2.0, ax)), pole.ay)

    def update(self):
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return True
        return m()

    def _phase_airgrab(self):
        b = self.body
        ax = max(self.bar.x0 + 2.0, min(self.bar.x1 - 2.0, b.chunk0.x))
        ay = self.pole.ay
        if math.hypot(b.chunk0.x - ax, b.chunk0.y - ay) <= GRIP_DIST:
            self._anchor = (ax, ay)
            self._grip(ax)
            return False
        if self.timer > AIRGRAB_TIMEOUT:
            self.giveup = True
            return True
        return False

    def _phase_mount(self):
        r = self.mount.update(self._anchor)
        if r == GIVEUP:
            self.giveup = True
            return True
        if r == GRIP:
            self._grip(self._anchor[0])
        return False

    def _grip(self, ax):
        b = self.body
        self.win.release_organs()
        b.facing = 1 if b.chunk0.x >= b.chunk1.x else -1
        b.chunk0.x, b.chunk0.vx = ax, 0.0
        hang_tick(b, self.bar, 0)
        self.phase = "hang"
        self.timer = 0

    def _phase_hang(self):
        hang_tick(self.body, self.bar, 0)
        if self.timer > HANG_TICKS:
            face = 1 if (self.rng is None or self.rng.random() < 0.5) else -1
            self._motion = PullUpMotion(self.body, self.bar, face)
            self.phase = "pullup"
            self.timer = 0
        return False

    def _phase_pullup(self):
        r = self._motion.step()
        if r is None:
            self.giveup = True
            return True
        if r:
            self.phase = "stand"
            self.timer = 0
        return False

    def _phase_stand(self):
        b = self.body
        stand_tick(b, self.bar, 0)
        self.gfx.look_at = (b.chunk0.x + b.facing * 60.0, b.chunk0.y)
        if self.timer > STAND_TICKS:
            release(b)
            b.chunk0.vy += JUMP_DOWN_VY
            b.chunk1.vy += JUMP_DOWN_VY
            b.chunk0.vx += b.facing * 1.0
            self._reset_pose()
            return True
        return False

    def _reset_pose(self):
        self.gfx.hand_aim["l"] = None
        self.gfx.hand_aim["r"] = None

    def release(self):
        release(self.body)
        self.win.release_organs()
        self._reset_pose()
