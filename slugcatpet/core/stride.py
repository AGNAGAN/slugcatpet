"""通行插进走路里的一串小动作：走到某处、等、起跳；由身体在走路时自己执行，到第一跳落地为止。"""

from __future__ import annotations

TO, WAIT, HOP = "to", "wait", "hop"
WALK, STAND = "walk", "stand"  # 起跳时走着还是站定
ARRIVE = 2.0  # 走到离点这么近（或走过了）就算到
BRAKE_V = 0.5  # 起跳前往反方向的速度超过这个就先停


class Stride:
    """steps：[(to, x) / (wait,) / (hop, 持跳 tick, 方向, 预计落点 x, 落在 floor 还是 cat, walk 走着跳 / stand 站定跳)]；
    go 为真时 wait 才放行；plan 是照着走的那份走法（含要等着让开的猫），walking 是不是走着过来的那份，给通行看。"""

    def __init__(self, steps, plan, walking):
        self.steps = list(steps)
        self.i = 0
        self.go = False
        self.plan, self.walking = plan, walking
        self._dir = 0
        self._jumped = False
        self._airborne = False
        self.braking = False  # 这一 tick 在起跳前停住

    @property
    def step(self):
        return self.steps[self.i] if self.i < len(self.steps) else None

    @property
    def done(self):
        return self.i >= len(self.steps)

    @property
    def jumped(self):
        """已经起跳（还没落地）。"""
        return self._jumped

    @property
    def stop_x(self):
        """要在那停下的位置：走到某处、接着不是走着起跳；没有 None。"""
        s, nxt = self.step, self.steps[self.i + 1] if self.i + 1 < len(self.steps) else None
        walk_on = nxt is not None and nxt[0] == HOP and nxt[5] == WALK
        return s[1] if s is not None and s[0] == TO and not walk_on else None

    @property
    def waiting(self):
        s = self.step
        return s is not None and s[0] == WAIT and not self.go

    def move(self, body):
        """这一 tick 往哪走（-1 / 0 / 1）；要起跳时给身体挂上跳。"""
        self.braking = False
        while not self.done:
            s = self.step
            c1 = body.chunk1
            if s[0] == WAIT:
                if not self.go:
                    return 0
                self._next()
                continue
            if s[0] == TO:
                dx = s[1] - c1.x
                if not self._dir:
                    self._dir = 1 if dx > 0 else -1
                if dx * self._dir <= ARRIVE:
                    self._next()
                    continue
                return self._dir
            _, hold, d = s[:3]
            run = s[5]
            if not self._jumped:
                if body.on_floor() and ((c1.vx * d < -BRAKE_V) or (run == STAND and abs(c1.vx) > BRAKE_V)):
                    self.braking = True
                    return 0  # 站定跳或还在往反方向走：先停住再起跳；猫背上停不住，落上就跳
                if body.on_floor() or body.on_support():
                    body.request_jump("stand", hold_ticks=hold)
                    self._jumped = True
                return d
            if not (body.on_floor() or body.on_support()):
                self._airborne = True
                return d
            if not self._airborne:
                return d  # 还没离地
            self._next()
        return None

    def _next(self):
        self.i += 1
        self._dir = 0
        self._jumped = self._airborne = False
