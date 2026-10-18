"""投掷技能：捡地上的武器、朝一点瞄准、出手；生气、打猎等行为共用。"""

from __future__ import annotations
import math

from ...items.base import THROWABLE
from ...items.stone.model import GRAVITY as STONE_GRAVITY
from ..hands import can_wield

GRAB_REACH = 18.0
REACH_GATE_K = 2.0
APPROACH_TIMEOUT = 240
MAX_FAILS = 5
ABANDON_FAILS = 3
THROW_FRAMES = 5
# 横向投掷的目标角度范围（度）
THROW_BAND_LO = -28.0
THROW_BAND_HI = 18.0

AIM_DEADBAND = 10.0  # 目标越过身体这么远才转向
AIM_REACH = 14.0  # 瞄准时手离肩的距离

THROW_SPEED_FRAC = 0.06
THROW_SPEED_MIN = 30.0
THROW_RECOIL = 0.35


def throw_speed(win):
    """出手水平基准速度，随窗口宽度。"""
    return max(THROW_SPEED_MIN, win._WL * THROW_SPEED_FRAC)


def aim_vy(body, target, dir_x, base):
    """从出手点水平速 base 扔向 target 所需的竖直初速；够不着返回 None。"""
    sx, sy = body.throw_origin(dir_x)
    dx = abs(target[0] - sx)
    dy = target[1] - sy
    vx = body.chunk0.vx * 0.2 + dir_x * base
    if dx < 1.0 or abs(vx) < 1e-3:
        return None
    n = dx / abs(vx)
    return dy / n - 0.5 * STONE_GRAVITY * body.room_gravity * (n + 1.0)  # 逐 tick 积分的闭式解


def wieldable(fsm, s, hunting=False):
    """地上一件可以捡来当武器的东西：静止、没判 unfetchable、没被占、不是刚放下的、肯用、拿得下。"""
    return (
        s.state == "free"
        and not s.unfetchable
        and s.at_rest_on_ground(fsm.win._HL)
        and fsm.social.free_for(fsm.win, s)
        and not fsm.hands.forbidden(s)
        and can_wield(fsm.body, s, hunting=hunting)
        and fsm.body.can_hold(s)
    )


def wieldable_items(fsm, hunting=False, use=THROWABLE):
    return [s for s in fsm.items(use) if wieldable(fsm, s, hunting)]


def in_band(body, point):
    """目标在横向投掷角度带内。"""
    c0 = body.chunk0
    horiz = abs(point[0] - c0.x)
    above = c0.y - point[1]  # y↓：>0 目标在上方
    if horiz < 1e-6:
        return False
    ang = math.degrees(math.atan2(above, horiz))
    return THROW_BAND_LO <= ang <= THROW_BAND_HI


class WeaponPickup:
    """选一件地上提供 use 的东西（默认是能扔的武器）走过去拿起；update() 返回 running / got / lost / failed。"""

    def __init__(self, fsm, score, claim_state, hunting=False, accept=None, use=THROWABLE, slot="stone"):
        self.fsm = fsm
        self.body = fsm.body
        self.score = score
        self.accept = accept  # 只挑这个函数认可的武器
        self.claim_state = claim_state
        self.hunting = hunting
        self.use = use
        self.slot = slot
        self.target = None
        self.grab_side = "r"
        self.timer = 0
        self.fails = 0

    def select(self):
        """挑 score 最小的一件并占住；没有可拿的返回 False。"""
        stones = wieldable_items(self.fsm, self.hunting, self.use)
        if self.accept is not None:
            stones = [s for s in stones if self.accept(s)]
        if not stones:
            return False
        c0 = self.body.chunk0
        self.target = min(stones, key=lambda s: self.score(s, math.hypot(c0.x - s.x, c0.y - s.y)))
        self.fsm.social.claim(self.fsm.win, self.slot, self.target, self.claim_state)
        self.grab_side = self._pick_side()
        self.fails = 0
        self.timer = 0
        return True

    def _pick_side(self):
        return "r" if self.target.x >= self.body.chunk0.x else "l"

    def _grab_dist(self):
        """上身或拿东西的手到目标边缘的距离。"""
        s = self.target
        c0 = self.body.chunk0
        d = math.hypot(c0.x - s.x, c0.y - s.y)
        hx, hy = self.body._carry_pos(self.grab_side)
        return max(0.0, min(d, math.hypot(hx - s.x, hy - s.y)) - s.rad)

    def available(self):
        return self.target is not None and wieldable(self.fsm, self.target, self.hunting)

    def update(self):
        self.timer += 1
        b, s = self.body, self.target
        self.grab_side = self._pick_side()
        b.walk_to(s.x)
        if self._grab_dist() < b.arm_full_reach * REACH_GATE_K:
            b.reach_for(s, self.grab_side)
        if self._grab_dist() < GRAB_REACH and b.free_hand() is not None:
            b.stop_walk()
            b.grab(s, b.free_hand(self.grab_side))
            self.fsm.social.release(self.fsm.win, self.slot)
            return "got"
        stalled = abs(b.chunk0.x - s.x) < GRAB_REACH or not b.is_moving()
        if stalled and self.timer > APPROACH_TIMEOUT:
            self.timer = 0
            self.fails += 1
            if self.fails >= MAX_FAILS:
                s.fetch_fails += 1
                if s.fetch_fails >= ABANDON_FAILS:
                    s.unfetchable = True
                return "failed"
        return "running"


class Pitch:
    """手里一件武器：转向、抬手瞄准一点、判断能否命中、出手。"""

    def __init__(self, fsm, weapon, spare_cursor=False):
        self.fsm = fsm
        self.win = fsm.win
        self.body = fsm.body
        self.gfx = fsm.gfx
        self.weapon = weapon
        self.spare_cursor = spare_cursor  # 扔出去不打光标
        self.throw_dir = 0
        self.dir_y = 0
        self.line_aim = None
        self.thrown = None
        self.t = 0

    def side(self):
        return self.body.hand_of(self.weapon)

    def face(self, point):
        """朝目标转身；目标贴着身体时保持原朝向。"""
        dx = point[0] - self.body.chunk0.x
        if self.throw_dir == 0 or abs(dx) > AIM_DEADBAND:
            self.throw_dir = 1 if dx >= 0 else -1
        self.body.facing = self.throw_dir

    def aim(self, point):
        """持武器手朝目标抬起；武器不在朝目标那侧的手里且能换手时先换手。返回是否已瞄好。"""
        b, g = self.body, self.gfx
        side = self.side()
        want = "r" if self.throw_dir > 0 else "l"
        if (side != want and b.stats.hands > 1) or b.switch_hands > 0.0:
            b.start_switch_hands()
            g.hand_aim["l"] = g.hand_aim["r"] = None
            return False
        sx, sy = g._shoulder(-1.0 if side == "l" else 1.0, g.body_axis())
        dx, dy = point[0] - sx, point[1] - sy
        d = math.hypot(dx, dy)
        if d > 1e-6:
            g.hand_aim[side] = (sx + dx / d * AIM_REACH, sy + dy / d * AIM_REACH)
        return True

    def can_hit(self, point):
        """按投掷态飞的武器要能解出命中 point 的出手方向，其余看 point 是否在横向角度带内。"""
        w = self.weapon
        if getattr(w, "aims_line", False):
            self.line_aim = w.aim_for(
                self.body, self.throw_dir, self.body.throw_origin(self.throw_dir), point
            )
            return self.line_aim is not None
        return in_band(self.body, point)

    def release(self):
        """瞄好后出手：放下抬着的手。"""
        side = self.side()
        if side is not None:
            self.gfx.hand_aim[side] = None
        self.t = 0

    def release_vertical(self, dir_y):
        """竖直扔（y↓：-1 朝上），后空翻或失重时用。"""
        self.dir_y = dir_y
        self.line_aim = None
        side = self.side()
        if side is not None:
            self.gfx.hand_aim[side] = None
        self.t = 0

    def release_blind(self, throw_dir):
        """不瞄准，朝 throw_dir 扔出去。"""
        self.throw_dir = throw_dir
        self.line_aim = None
        self.t = 0

    def update(self, point):
        """出手后的几帧；point 用来解抛物线竖直初速，None 时按默认上扬。返回 running / thrown。"""
        if self.t == 0:
            b = self.body
            base = throw_speed(self.win)
            side = self.side()
            kw = {"recoil": THROW_RECOIL, "spare_cursor": self.spare_cursor}
            if self.dir_y:
                self.thrown = b.throw(self.weapon, 0, base, dir_y=self.dir_y, **kw)
            elif getattr(self.weapon, "aims_line", False):
                self.thrown = b.throw(self.weapon, self.throw_dir, base, aim=self.line_aim, **kw)
            else:
                vy = None if point is None else aim_vy(b, point, self.throw_dir, base)
                self.thrown = b.throw(self.weapon, self.throw_dir, base, up=3.0, vy=vy, **kw)
            if self.thrown is not None:
                self.gfx.throw_object(side, self.thrown)
            self.gfx.blink = 15
        if self.thrown is not None:
            self.gfx.look_at = (self.thrown.x, self.thrown.y)
        self.t += 1
        if self.t >= THROW_FRAMES:
            self.fsm._clear_hands()
            return "thrown"
        return "running"
