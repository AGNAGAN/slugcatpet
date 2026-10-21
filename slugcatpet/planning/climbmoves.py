"""杆网寻路的动作：按 climbmap 的一条边驱动身体，update() 返回 running / done / fail。"""

from __future__ import annotations

import math

from .climbmap import (
    BEAM_WALK,
    CLIMB_DOWN,
    CONN,
    CLIMB_UP,
    H_TOL,
    SHIMMY,
    STAND_HOVER,
    TIP_HOVER,
    TOUCH_R,
    V_TOL,
)

RUNNING, DONE, FAIL = "running", "done", "fail"
SIDE_OFF = 5.0  # 爬竖杆时头偏到杆的一侧
ARRIVE = 1.5
STAND_RESTART = 6.0  # 站横杆停下后离目标超过这么远才重新走
STAND_COAST = 2.8  # 站横杆走动时提前这么多倍速度松手，停下时滑行到目标附近
TILE = 20.0  # 一格
GRAVITY = 0.9
CLIMB_SLIDE = 2.2  # 往下滑时头的推力
CLIMB_ARRIVE = 3.0  # 爬到离目标这么近就停
STAND_HEAD_UP = 2.0  # 站横杆时头的上推力
TIP_HEAD_UP = 1.5  # 站杆尖时头的上推力
RUN_ACCEL = 1.2  # 跑动加速度
HANG_GAIT = 0.5  # 吊着挪动时臀部的晃动推力
HANG_ARRIVE = 2.0
PULL_BUTT_UP = 2.0  # 翻杆时臀部的上推力
PULL_BUTT_FWD = 0.5  # 往前推
PULLUP_SAFETY = 200
PULL_STUCK = 20  # 翻杆时臀这么久没再抬高就改成直着往上翻
PULL_STRAIGHT = 1.8  # 直着往上翻时头和臀朝目标的推力
PULL_STRAIGHT_LOST = 25.0  # 直着翻时头离目标超过这么远就松手
UPRIGHT = 0.85  # 头高出臀这么多倍身长算直起身
TIP_ARRIVE = 6.0  # 臀离杆尖站点这么近算站上去
HANG_BEFORE_PULL = 6  # 抓住横杆后先吊这么久再翻
REACH_SLACK = 10.0
REACH_LOST_TICKS = 20  # 目标离开够得着的范围这么久就重新找路
REACH_UP_TICKS = 10
REACH_UP_HOP = 8.0  # 伸手抓上面横杆时身子先上窜的距离
LAUNCH_EPS = 4.0  # 地上起跳点的容差
GRAB_V_REACH = 20.0  # 走到离竖杆这么近就能从地上抓
SETTLE_VX = 0.6
AIR_TIMEOUT = 260
MOVE_SLACK = 90  # 每个动作在预计耗时外再给这么多 tick


def grip(body, bar):
    """抓着 bar，记下抓的是哪根杆。"""
    body.on_pole = True
    body.pole_obj = bar.obj


def release(body):
    """离开杆，回到普通物理。"""
    body.chunk0.pinned = body.chunk1.pinned = False
    body.on_pole = False
    body.animation = None


class Move:
    budget = 120

    def __init__(self, nav, bar=None):
        self.nav = nav
        self.pet = nav.pet
        self.body = nav.pet.body
        self.bar = bar
        self.t = 0

    def update(self):
        self.t += 1
        if self.t > self.budget + MOVE_SLACK:
            return FAIL
        return self.step()


class AlongMove(Move):
    """沿一根杆走到一个采样点。下一步同样沿这根杆同向走时不在这里停下，走过就算到；
    下一步的位置被挡着时改回停在这里。"""

    act = None

    def __init__(self, nav, bar, target, pos):
        super().__init__(nav, bar)
        self.target = target
        d = target - pos
        self.dir = 1 if d > 0 else (-1 if d < 0 else 0)
        nxt = nav.next_act()
        self.through = (
            self.dir != 0
            and nxt is not None
            and nxt[0] == self.act
            and nav.cm.bars[nxt[1]] is bar
            and (nxt[2] - target) * self.dir > 0
        )

    def step(self):
        if self.through and not self.nav.next_open():
            self.through = False
        if not self.through:
            return DONE if self.toward() else RUNNING
        self.push(self.dir)
        return DONE if (self.target - self.pos()) * self.dir <= 0.0 else RUNNING


# 竖杆


def attach_vertical(body, bar, facing):
    """抓住竖杆。"""
    c0, c1 = body.chunk0, body.chunk1
    grip(body, bar)
    body.standing = True
    body.animation = "ClimbOnBeam"
    body.pole_x = bar.x
    body.facing = facing
    c0.pinned = c1.pinned = False
    c0.vx = c0.vy = 0.0


def climb_tick(body, bar, iy, clamp=True):
    """爬在竖杆上推一 tick：iy=1 往上爬，-1 往下滑，0 挂住。"""
    c0, c1 = body.chunk0, body.chunk1
    grip(body, bar)
    body.standing = True
    body.animation = "ClimbOnBeam"
    body.pole_x = bar.x
    body.pole_input = (0, iy)
    if iy == body.lane_hold:
        iy = 0
    g = GRAVITY * body.room_gravity
    tx = bar.x + (body.facing or 1) * SIDE_OFF
    c0.pinned = c1.pinned = False
    c0.vx = 0.0
    c0.x = (c0.x + tx) / 2.0
    c1.x = (c1.x * 7.0 + tx) / 8.0
    c0.vy *= 0.5
    if iy > 0:
        c0.vy -= body.stats.pole_fac * body.slow_fac(0.2)
        body.aerobic_increase(0.1 / 20.0)
        body.pole_frame += 1  # 往上爬时动画帧才走
        if body.pole_frame > 20:
            body.pole_frame = 0
    elif iy < 0:
        c0.vy += CLIMB_SLIDE * (0.2 + 0.8 * body.room_gravity)
    c0.vy -= 1.0 + g
    c1.vy += 1.0 - g
    if not clamp:
        return
    if c0.y < bar.lo:  # 头不越过杆的两端
        c0.y, c0.vy = bar.lo, max(c0.vy, 0.0)
    elif c0.y > bar.hi:
        c0.y, c0.vy = bar.hi, min(c0.vy, 0.0)


def climb_toward(body, bar, y):
    """往 y 爬一 tick，到了返回 True。"""
    dy = y - body.chunk0.y
    iy = 0 if abs(dy) <= CLIMB_ARRIVE else (1 if dy < 0 else -1)
    climb_tick(body, bar, iy)
    return iy == 0


class Climb(AlongMove):
    act = "climb"

    def __init__(self, nav, bar, y):
        super().__init__(nav, bar, y, nav.pet.body.chunk0.y)
        d = abs(y - self.body.chunk0.y)
        self.budget = int(d / min(CLIMB_UP, CLIMB_DOWN)) + 30

    def pos(self):
        return self.body.chunk0.y

    def push(self, d):
        climb_tick(self.body, self.bar, -d)

    def toward(self):
        return climb_toward(self.body, self.bar, self.target)


class GrabFromFloor(Move):
    """走到竖杆底下抓住。"""

    def __init__(self, nav, bar):
        super().__init__(nav, bar)
        self.budget = int(abs(bar.x - self.body.chunk1.x) / 2.0) + 60

    def step(self):
        b = self.body
        c1 = b.chunk1
        b.set_posture(True)  # 站着走过去抓杆
        if abs(c1.x - self.bar.x) > GRAB_V_REACH or not c1.on_floor:
            return RUNNING if b.walk_to(self.bar.x, GRAB_V_REACH) else FAIL
        b.stop_walk()
        attach_vertical(b, self.bar, 1 if b.chunk0.x >= self.bar.x else -1)
        return DONE


class StepOff(Move):
    """从竖杆底端下到地上。"""

    budget = 30

    def step(self):
        b = self.body
        if self.t == 1:
            release(b)
            b.standing = True
            b.chunk0.vy = 1.0
        return DONE if b.on_floor() else RUNNING


class TipUp(Move):
    """从杆顶爬上杆尖站直。"""

    budget = 90

    def step(self):
        b = self.body
        if b.animation == "BeamTip":
            tip_step(b, self.bar)
            return DONE if upright(b) else RUNNING
        return FAIL if tip_up_tick(b, self.bar) is None else RUNNING


def tip_up_tick(body, bar):
    """往杆尖上爬一 tick：站上去 True，还在爬 False，身子已不在杆顶上方那格时松手返回 None。"""
    c0, c1 = body.chunk0, body.chunk1
    if body.animation != "GetUpToBeamTip":
        if c0.y > bar.y0:
            climb_tick(body, bar, 1, clamp=False)
            return False
        body.animation = "GetUpToBeamTip"
    if not any(abs(c.x - bar.x) < TILE / 2 and bar.y0 - TILE <= c.y < bar.y0 for c in (c0, c1)):
        release(body)
        return None
    grip(body, bar)
    body.standing = True
    body.pole_x = bar.x
    c0.pinned = c1.pinned = False
    g = GRAVITY * body.room_gravity
    px, py = bar.x, bar.y0 - TIP_HOVER
    c0.vy -= g
    c1.vy -= g
    c0.x = (c0.x * 14.0 + px) / 15.0
    c1.x = (c1.x * 4.0 + px) / 5.0
    c0.vy -= 0.1
    c1.y = (c1.y * 4.0 + py) / 5.0
    if math.hypot(c1.x - px, c1.y - py) < TIP_ARRIVE:
        body.animation = "BeamTip"
        return True
    return False


def tip_step(body, bar, nudge=0.0):
    """站在杆尖上推一 tick；头掉到臀以下或臀离开杆尖那一格返回 False。"""
    c0, c1 = body.chunk0, body.chunk1
    if abs(c1.x - bar.x) > TILE / 2:
        return False
    grip(body, bar)
    body.standing = True
    body.animation = "BeamTip"
    body.pole_x = bar.x
    c0.pinned = c1.pinned = False
    c1.vx *= 0.5
    c1.vy *= 0.5
    c1.x = (c1.x + bar.x) / 2.0
    c1.y = (c1.y + bar.y0 - TIP_HOVER) / 2.0
    c0.vy -= TIP_HEAD_UP
    c0.vx += nudge
    return c0.y < c1.y


class TipDown(Move):
    """从杆尖松手掉回杆上抓住。"""

    budget = 30

    def step(self):
        b = self.body
        if self.t == 1:
            release(b)
            return RUNNING
        if b.chunk0.y >= self.bar.lo:
            attach_vertical(b, self.bar, b.facing or 1)
            return DONE
        return RUNNING


# 横杆


def grab_from_zerog(body, bar):
    """重力恢复时失重抓着的杆：竖杆转成爬着，横杆转成吊着。"""
    body.zerog_pole = None
    if bar.vertical:
        attach_vertical(body, bar, 1 if body.chunk0.x >= bar.x else -1)
    else:
        grab_beam(body, bar, body.chunk0.x)


def hang_tick(body, bar, ix):
    """吊在横杆下推一 tick：ix=±1 往那边挪，0 停住。"""
    c0, c1 = body.chunk0, body.chunk1
    grip(body, bar)
    body.standing = True
    body.animation = "HangFromBeam"
    body.pole_y = bar.y
    body.beam_span = (bar.x0, bar.x1)
    body.pole_input = (ix, 0)
    if ix == body.lane_hold:
        ix = 0
    c0.pinned, c1.pinned = True, False
    c0.vy = 0.0
    c0.vx *= 0.2
    if ix:
        body.facing = ix
        c0.vx += ix * SHIMMY / 1.25 * body.stats.pole_fac * body.slow_fac(0.5)
        body.pole_frame += 1
        if body.pole_frame > 20:
            body.pole_frame = 1
            body.aerobic_increase(0.05)
        gait = 0.5 + 0.5 * math.sin(body.pole_frame / 20.0 * 2.0 * math.pi)
        c1.vx -= body.facing * gait * HANG_GAIT
    elif body.pole_frame < 10:
        body.pole_frame += 1
    elif body.pole_frame > 10:
        body.pole_frame -= 1
    c0.x = min(max(c0.x + c0.vx, bar.x0 + 2.0), bar.x1 - 2.0)
    c0.y = bar.y
    body.pole_x = c0.x


def hang_toward(body, bar, x):
    """吊着往 x 挪一 tick，到了返回 True。"""
    d = x - body.chunk0.x
    ix = 0 if abs(d) <= HANG_ARRIVE else (1 if d > 0 else -1)
    hang_tick(body, bar, ix)
    return ix == 0


def grab_beam(body, bar, x):
    """在 x 处抓住横杆吊着。"""
    body.chunk0.x = min(max(x, bar.x0 + 2.0), bar.x1 - 2.0)
    body.chunk0.vx = 0.0
    hang_tick(body, bar, 0)


def run_accel(body, ix, cap):
    """跑动加速：头和臀各自加速，不超过 cap。"""
    if not ix:
        return
    for c in (body.chunk0, body.chunk1):
        add = min(RUN_ACCEL, cap - c.vx * ix)
        if add > 0.0:
            c.vx += ix * add


def stand_tick(body, bar, ix):
    """站在横杆上推一 tick：ix=±1 往那边走，0 站着。"""
    c0, c1 = body.chunk0, body.chunk1
    grip(body, bar)
    body.standing = True
    body.animation = "StandOnBeam"
    body.pole_y = bar.y
    body.pole_input = (ix, 0)
    if ix == body.lane_hold:
        ix = 0
    if ix:
        body.facing = ix
        body.pole_frame += 1  # 走一步换一次脚
        if body.pole_frame > 6:
            body.pole_frame = 0
    else:
        body.pole_frame = 0
    c0.pinned = c1.pinned = False
    c1.vx *= 0.5
    c1.vy = -GRAVITY * body.room_gravity  # 抵掉这一 tick 的重力，臀停在杆上
    c1.y = bar.y - STAND_HOVER
    c0.vy -= STAND_HEAD_UP
    run_accel(body, ix, BEAM_WALK * body.stats.runspeed_fac)
    lo, hi = bar.x0 + 2.0, bar.x1 - 2.0
    c1.x = min(max(c1.x, lo), hi)
    c1.vx = min(max(c1.vx, lo - c1.x), hi - c1.x)
    body.pole_x = c1.x


def stand_toward(body, bar, x):
    """站在横杆上往 x 走一 tick，停稳了返回 True。"""
    d = x - body.chunk1.x
    stopped = body.animation == "StandOnBeam" and body.pole_input[0] == 0
    reach = STAND_RESTART if stopped else max(ARRIVE, abs(body.chunk1.vx) * STAND_COAST)
    ix = 0 if abs(d) <= reach else (1 if d > 0 else -1)
    stand_tick(body, bar, ix)
    return ix == 0 and abs(body.chunk1.vx) < 0.2


class Shimmy(AlongMove):
    act = "shimmy"

    def __init__(self, nav, bar, x):
        super().__init__(nav, bar, x, nav.pet.body.chunk0.x)
        self.budget = int(abs(x - self.body.chunk0.x) / SHIMMY) + 20

    def pos(self):
        return self.body.chunk0.x

    def push(self, d):
        hang_tick(self.body, self.bar, d)

    def toward(self):
        return hang_toward(self.body, self.bar, self.target)


class BeamWalk(AlongMove):
    act = "beamwalk"

    def __init__(self, nav, bar, x):
        super().__init__(nav, bar, x, nav.pet.body.chunk1.x)
        self.budget = int(abs(x - self.body.chunk1.x) / BEAM_WALK) + 10

    def pos(self):
        return self.body.chunk1.x

    def push(self, d):
        stand_tick(self.body, self.bar, d)

    def toward(self):
        return stand_toward(self.body, self.bar, self.target)


class PullUpMotion:
    """翻上横杆：臀绕着扣住杆的头甩上去，高过头就站上杆；甩的那侧没杆或被挡住时直着往上翻。"""

    def __init__(self, body, bar, facing):
        self.body = body
        self.bar = bar
        self.x = body.chunk0.x
        face = facing or 1
        if not bar.x0 <= self.x + face * TILE <= bar.x1:
            face = -face
        self.straight = not bar.x0 <= self.x + face * TILE <= bar.x1
        self.facing = face
        self.t = 0
        self.best = body.chunk1.y
        self.since_best = 0

    def step(self):
        """推进一 tick：站上去 True，还在翻 False，翻不上去松手返回 None。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        bar = self.bar
        self.t += 1
        grip(b, bar)
        b.standing = True
        b.animation = "GetUpOnBeam"
        b.pole_x, b.pole_y = self.x, bar.y
        b.beam_span = (bar.x0, bar.x1)
        c0.pinned, c1.pinned = True, False
        c0.x, c0.y = self.x, bar.y
        c0.vx = c0.vy = 0.0
        c1.vy -= PULL_BUTT_UP
        c1.vx += self.facing * PULL_BUTT_FWD
        if self.t > PULLUP_SAFETY:
            release(b)
            return None
        if self.straight:
            return self._straight_step()
        if c1.y < self.best - 0.5:
            self.best, self.since_best = c1.y, 0
        else:
            self.since_best += 1
            if self.since_best > PULL_STUCK:
                self.straight = True
        if c1.y < c0.y:
            c1.y = bar.y - STAND_HOVER
            c1.vy = 0.0
            stand_tick(b, bar, 0)
            return True
        return False

    def _straight_step(self):
        """直着往上翻：头往杆上方一格、臀往杆上推，臀到杆上就站上去。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        bar = self.bar
        c0.pinned = False
        c0.vx = c0.vy = 0.0
        b.ghost = max(b.ghost, 2)  # 从挡住的猫身边穿上去
        ux, uy = self.x, bar.y - TILE
        for c, ty in ((c0, uy), (c1, bar.y)):
            dx, dy = ux - c.x, ty - c.y
            n = math.hypot(dx, dy) or 1.0
            c.vx += dx / n * PULL_STRAIGHT
            c.vy += dy / n * PULL_STRAIGHT
        if c1.y < bar.y + STAND_HOVER and bar.x0 <= c1.x <= bar.x1:
            c1.y = bar.y - STAND_HOVER
            c1.vy = 0.0
            stand_tick(b, bar, 0)
            return True
        if math.hypot(c0.x - ux, c0.y - uy) > PULL_STRAIGHT_LOST:
            release(b)
            return None
        return False


def upright(body):
    """站在杆上已经直起身。"""
    c0, c1 = body.chunk0, body.chunk1
    return c1.y - c0.y > UPRIGHT * CONN and abs(c0.vx) < 2.0


class PullUp(Move):
    """吊着停一下，再翻上横杆直起身。"""

    budget = HANG_BEFORE_PULL + PULLUP_SAFETY + 10

    def step(self):
        b = self.body
        if self.t <= HANG_BEFORE_PULL:
            hang_tick(b, self.bar, 0)
            return RUNNING
        if self.t == HANG_BEFORE_PULL + 1:
            face = self.nav.next_facing()
            self.motion = PullUpMotion(b, self.bar, face or b.facing)
        if self.motion is not None:
            r = self.motion.step()
            if r is None:
                return FAIL
            if r:
                self.motion = None
            return RUNNING
        stand_tick(b, self.bar, 0)
        return DONE if upright(b) else RUNNING


def hold_tick(body, bar, kind):
    """按姿势 kind（V / T / H / S）在杆上原地抓稳一 tick。"""
    if kind == "V":
        climb_tick(body, bar, 0)
    elif kind == "T":
        tip_step(body, bar)
    elif kind == "H":
        hang_tick(body, bar, 0)
    else:
        stand_tick(body, bar, 0)


class SwingUnderMotion:
    """从横杆上松脚掉下去，头经过杆时抓住吊着。"""

    def __init__(self, body, bar):
        self.body = body
        self.bar = bar
        self.t = 0

    def step(self):
        """推进一 tick：吊住了 True，还在落 False。"""
        b = self.body
        self.t += 1
        b.ghost = max(b.ghost, 2)  # 落的时候穿过杆上要过去的那只
        if self.t == 1:
            release(b)
            b.chunk0.vx = b.chunk1.vx = 0.0
            return False
        if b.chunk0.y >= self.bar.y:
            grab_beam(b, self.bar, b.chunk0.x)
            return True
        return False


class SwingUnder(Move):
    """从横杆上松脚下去吊着。"""

    budget = 40

    def step(self):
        if self.t == 1:
            self.motion = SwingUnderMotion(self.body, self.bar)
        return DONE if self.motion.step() else RUNNING


class ReachUp(Move):
    """站在横杆上伸手抓上面那根横杆。"""

    budget = REACH_UP_TICKS + 4

    def __init__(self, nav, bar, x):
        super().__init__(nav, bar)
        self.x = x

    def step(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        if self.t == 1:
            c0.pinned = c1.pinned = False
            c0.y -= REACH_UP_HOP
            c1.y -= REACH_UP_HOP
            c0.vx = c0.vy = c1.vx = c1.vy = 0.0
            b.animation = "HangFromBeam"
            return RUNNING
        c0.pinned = True
        c0.x += (self.x - c0.x) * 0.5
        c0.y += (self.bar.y - c0.y) * 0.5
        c0.vx = c0.vy = 0.0
        if abs(c0.y - self.bar.y) < 1.0 or self.t > REACH_UP_TICKS:
            grab_beam(b, self.bar, self.x)
            return DONE
        return RUNNING


class ToHang(Move):
    """从竖杆转到吊在交叉的横杆下。"""

    budget = 12

    def __init__(self, nav, bar, x):
        super().__init__(nav, bar)
        self.x = min(max(x, bar.x0), bar.x1)

    def step(self):
        grab_beam(self.body, self.bar, self.nav.cross_x(self.bar, self.x))
        return DONE


class ToStand(Move):
    """从竖杆踩到交叉的横杆上站直。"""

    budget = 40

    def __init__(self, nav, bar, x):
        super().__init__(nav, bar)
        self.x = x

    def step(self):
        b = self.body
        if self.t == 1:
            b.chunk1.x = self.nav.cross_x(self.bar, self.x)
        stand_tick(b, self.bar, 0)
        return DONE if upright(b) else RUNNING


class ToVertical(Move):
    """从横杆转到交叉的竖杆上爬着。"""

    budget = 12

    def __init__(self, nav, bar, y):
        super().__init__(nav, bar)
        self.y = y

    def step(self):
        b = self.body
        attach_vertical(b, self.bar, b.facing or 1)
        return DONE


# 起跳与空中


class Fly(Move):
    """起跳或松手，空中抓第一根碰到的杆（catch=False 不抓），落地也算到。"""

    budget = AIR_TIMEOUT

    def __init__(self, nav, launch, catch=True, skip=None):
        super().__init__(nav)
        self.launch = launch
        self.catch = catch
        self.skip = skip
        self.air = 0
        self.caught = None

    def step(self):
        b = self.body
        if self.t == 1:
            self._go()
            return RUNNING
        self.air += 1
        if self.catch and self.air >= 2:
            hit = self.nav.catch(self.skip)
            if hit is not None:
                self.caught = hit
                return DONE
        b.move_dir = self.md
        if b.swimming:
            return FAIL
        if b.on_floor() and self.air > 2:
            b.stop_walk()
            return DONE
        return RUNNING

    def _go(self):
        b = self.body
        kind = self.launch[0]
        release(b)
        if kind == "polejump":
            self.md = self.launch[1]
            b.pole_jump(self.md)
        elif kind == "standjump":
            _, hold, md = self.launch
            self.md = md
            b.tip_launch(hold_ticks=hold, move_dir=md)
        else:
            self.md = self.launch[1]
            b.release_to_air(move_dir=self.md)


class FloorFly(Fly):
    """走到地上的起跳点，停稳了起跳，空中抓杆。"""

    def __init__(self, nav, lx, launch):
        super().__init__(nav, launch)
        self.lx = lx
        self.phase = "walk"
        self.budget = int(abs(lx - self.body.chunk1.x) / 2.0) + AIR_TIMEOUT

    def step(self):
        b = self.body
        if self.phase == "walk":
            b.set_posture(True)
            c1 = b.chunk1
            if abs(c1.x - self.lx) > LAUNCH_EPS or not b.on_floor():
                return RUNNING if b.walk_to(self.lx, LAUNCH_EPS) else FAIL
            b.stop_walk()
            if abs(c1.vx) > SETTLE_VX or abs(b.chunk0.vx) > SETTLE_VX:
                return RUNNING
            _, hold, md = self.launch
            self.md = md
            b.request_jump("stand", hold_ticks=hold)
            b.move_dir = md
            self.phase = "air"
            return RUNNING
        self.air += 1
        hit = self.nav.catch(None) if self.air >= 2 else None
        if hit is not None:
            self.caught = hit
            return DONE
        b.move_dir = self.md
        if b.on_floor() and self.air > 4:
            b.stop_walk()
            return DONE
        return RUNNING


class Reach(Move):
    """到位后靠近目标伸手；抓没抓到由取东西的一方判断。"""

    budget = 10**9

    def __init__(self, nav):
        super().__init__(nav)
        spot = nav.spot
        self.kind = spot[0] if spot is not None else "F"
        self.bar = nav.cm.bars[spot[1]] if spot is not None and spot[1] >= 0 else None
        self.lost = 0

    def step(self):
        nav, b = self.nav, self.body
        gx, gy = nav.goal.pos()
        bar, k = self.bar, self.kind
        if bar is not None and nav.cm.reach_gap(k, bar, gx, gy) > TOUCH_R + REACH_SLACK:
            self.lost += 1
            if self.lost > REACH_LOST_TICKS:
                return FAIL  # 目标挪走了：从这里重新找路
        else:
            self.lost = 0
        if bar is not None:
            if k == "V":
                b.facing = 1 if gx >= bar.x else -1
                climb_toward(b, bar, min(max(gy, bar.lo), bar.hi))
            elif k == "H":
                hang_toward(b, bar, min(max(gx, bar.lo), bar.hi))
            elif k == "S":
                stand_toward(b, bar, min(max(gx, bar.lo), bar.hi))
            elif k == "T":
                tip_step(b, bar)
        from .reach import reach_assist

        reach_assist(self.pet, nav.goal, gx, gy)
        return RUNNING


class TouchFly(Fly):
    """起跳在空中够目标，落地结束。"""

    def step(self):
        b = self.body
        if self.t == 1:
            self._go()
            return RUNNING
        self.air += 1
        gx, gy = self.nav.goal.pos()
        from .reach import reach_assist

        reach_assist(self.pet, self.nav.goal, gx, gy)
        b.move_dir = self.md
        if b.on_floor() and self.air > 2:
            b.stop_walk()
            return DONE
        return RUNNING


def catch_in_air(nav, skip):
    """空中这一 tick 抓得到的杆：(位置, 摆好姿势)；抓不到 None。"""
    b, cm = nav.pet.body, nav.cm
    c0 = b.chunk0
    py = c0.last_y if hasattr(c0, "last_y") else c0.y - c0.vy
    for j, bar in enumerate(cm.bars):
        if bar.obj is skip:
            continue
        if bar.vertical:
            if abs(c0.x - bar.x) <= V_TOL and bar.y0 <= c0.y <= bar.y1:
                y = min(max(c0.y, bar.lo), bar.hi)
                attach_vertical(b, bar, 1 if c0.x >= bar.x else -1)
                b.chunk1.vx *= 0.3
                b.chunk1.vy *= 0.3
                return ("V", j, bar.snap(y))
        else:
            lo, hi = (py, c0.y) if py <= c0.y else (c0.y, py)
            if lo - 2.0 <= bar.y <= hi + 2.0 and bar.x0 - H_TOL <= c0.x <= bar.x1 + H_TOL:
                x = min(max(c0.x, bar.x0 + 2.0), bar.x1 - 2.0)
                grab_beam(b, bar, x)
                b.chunk1.vy *= 0.25
                return ("H", j, bar.snap(x))
    return None


def make(nav, act):
    """把 climbmap 的动作变成一个 Move。"""
    kind = act[0]
    bars = nav.cm.bars
    if kind == "climb":
        return Climb(nav, bars[act[1]], act[2])
    if kind == "grab_v":
        return GrabFromFloor(nav, bars[act[1]])
    if kind == "step_off":
        return StepOff(nav, bars[act[1]])
    if kind == "tip_up":
        return TipUp(nav, bars[act[1]])
    if kind == "tip_down":
        return TipDown(nav, bars[act[1]])
    if kind == "shimmy":
        return Shimmy(nav, bars[act[1]], act[2])
    if kind == "beamwalk":
        return BeamWalk(nav, bars[act[1]], act[2])
    if kind == "pullup":
        return PullUp(nav, bars[act[1]])
    if kind == "swing_under":
        return SwingUnder(nav, bars[act[1]])
    if kind == "reach_up":
        return ReachUp(nav, bars[act[1]], act[2])
    if kind == "v_to_hang":
        return ToHang(nav, bars[act[1]], act[2])
    if kind == "v_to_stand":
        return ToStand(nav, bars[act[1]], act[2])
    if kind in ("hang_to_v", "stand_to_v"):
        return ToVertical(nav, bars[act[1]], act[2])
    if kind == "fly":
        return Fly(
            nav, act[1], catch=True, skip=bars[nav.spot[1]].obj if nav.spot and nav.spot[1] >= 0 else None
        )
    if kind == "fall":
        return Fly(nav, act[1], catch=False)
    if kind == "floor_fly":
        return FloorFly(nav, act[1], act[2])
    if kind == "reach":
        return Reach(nav)
    if kind == "touchfly":
        return TouchFly(nav, act[1], catch=False)
    raise ValueError(kind)
