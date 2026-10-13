"""生气期捡武器 / 投武器控制器；select→approach→hold→throw，update() 返回路由串。"""

from __future__ import annotations
import math

from ... import tuning
from ...brain.hands import can_wield
from ...items.base import THROWABLE
from ...items.stone.model import GRAVITY as STONE_GRAVITY

GRAB_REACH = 18.0
REACH_GATE_K = 2.0
APPROACH_TIMEOUT = 240
MAX_FAILS = 5
ABANDON_FAILS = 3
THROW_FRAMES = 5
HOLD_AIM_TICKS = 80  # 拿到石头后先盯光标这么久才扔
# 横向门：猫→光标角度，度
THROW_BAND_LO = -28.0
THROW_BAND_HI = 18.0
ABANDON_MIN = 400  # 一直等不到机会，过这么久就消气
ABANDON_MAX = 600

AIM_DEADBAND = 10.0  # 光标越过身体这么远才转向
AIM_REACH = 14.0  # 瞄准时手离肩的距离

THROW_SPEED_FRAC = 0.06
THROW_SPEED_MIN = 30.0
THROW_RECOIL = 0.35


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


def weapon_score(fsm, obj, dist):
    """挑武器的排序值（小者优先）：好感很低时偏向扎得进的。"""
    if getattr(obj, "pierces", False) and fsm.body.temper < tuning.SPEAR_TEMPER:
        return dist * tuning.SPEAR_PREF
    return dist


class WeaponThrower:
    """keep=True 时捡到就收工（揣着），否则捡到后瞄准光标扔。"""

    def __init__(self, win, rng, fsm, keep=False):
        self.win = win
        self.body = win.body
        self.gfx = win.gfx
        self.rng = rng
        self.fsm = fsm
        self.keep = keep

        self.target = None
        self.phase = "select"
        self.grab_side = "r"
        self.timer = 0
        self.fails = 0
        self.throw_dir = 0
        self.throw_t = 0
        self.abandon_at = ABANDON_MAX
        self._thrown = None
        self._line_aim = None

    def _chunk0(self):
        return self.body.chunk0

    def _grab_dist(self):
        """上身或拿东西的手到目标边缘的距离。"""
        s = self.target
        c0 = self._chunk0()
        d = math.hypot(c0.x - s.x, c0.y - s.y)
        hx, hy = self.body._carry_pos(self.grab_side)
        return max(0.0, min(d, math.hypot(hx - s.x, hy - s.y)) - s.rad)

    def _pick_side(self):
        return "r" if self.target.x >= self._chunk0().x else "l"

    def _avail(self, s):
        """可作目标：free 态 + 地面静止 + 未判 unfetchable + 没被别的猫占着 + 不是刚放下的 + 肯拿它当武器 + 拿得下。"""
        return (
            s.state == "free"
            and not s.unfetchable
            and s.at_rest_on_ground(self.win._HL)
            and self.win.social.free_for(self.win, s)
            and not self.fsm.hands.forbidden(s)
            and can_wield(self.body, s)
            and self.body.can_hold(s)
        )

    def _in_band(self, cursor):
        c0 = self._chunk0()
        horiz = abs(cursor[0] - c0.x)
        above = c0.y - cursor[1]  # y↓：>0 光标在上方
        if horiz < 1e-6:
            return False
        ang = math.degrees(math.atan2(above, horiz))
        return THROW_BAND_LO <= ang <= THROW_BAND_HI

    def start_with(self, stone):
        """手里已经有石头：直接进入瞄准。"""
        self.target = stone
        self.grab_side = self.body.hand_of(stone)
        self.phase = "hold"
        self.timer = 0
        self.abandon_at = self.rng.randint(ABANDON_MIN, ABANDON_MAX)

    def _can_hit(self, cursor):
        """出手时机：按投掷态飞的武器要能解出命中光标的出手方向，其余看光标是否在横向角度带内。"""
        t = self.target
        if getattr(t, "aims_line", False):
            self._line_aim = t.aim_for(
                self.body, self.throw_dir, self.body.throw_origin(self.throw_dir), cursor
            )
            return self._line_aim is not None
        return self._in_band(cursor)

    def _solve_vy(self, base):
        cursor = self.fsm.cursor
        if cursor is None:
            return None
        return aim_vy(self.body, cursor, self.throw_dir, base)

    def update(self, still_angry) -> str:
        self.timer += 1
        m = getattr(self, "_phase_" + self.phase, None)
        if m is None:
            return "idle"
        return m(still_angry)

    def _phase_select(self, still_angry):
        if not still_angry:
            return "idle"
        stones = [s for s in self.win.items_affording(THROWABLE) if self._avail(s)]
        if not stones:
            return "revert_wander"
        c0 = self._chunk0()
        self.target = min(stones, key=lambda s: weapon_score(self.fsm, s, math.hypot(c0.x - s.x, c0.y - s.y)))
        self.win.social.claim(self.win, "stone", self.target, "AngryStone")
        self.grab_side = self._pick_side()
        self.fails = 0
        self.timer = 0
        self.phase = "approach"
        return "running"

    def _phase_approach(self, still_angry):
        s = self.target
        if s is None or not self._avail(s):
            return "revert_wander" if still_angry else "idle"
        if not still_angry:
            return "idle"
        self.grab_side = self._pick_side()
        self.body.walk_to(s.x)
        if self._grab_dist() < self.body.arm_full_reach * REACH_GATE_K:
            self.body.reach_for(s, self.grab_side)
        if self._grab_dist() < GRAB_REACH and self.body.free_hand() is not None:
            self.body.stop_walk()
            self.body.grab(s, self.body.free_hand(self.grab_side))
            self.win.social.release(self.win, "stone")
            if self.keep:
                return "armed"
            self.phase = "hold"
            self.timer = 0
            self.abandon_at = self.rng.randint(ABANDON_MIN, ABANDON_MAX)
            return "running"
        stalled = abs(self._chunk0().x - s.x) < GRAB_REACH or not self.body.is_moving()
        if stalled and self.timer > APPROACH_TIMEOUT:
            self.timer = 0
            self.fails += 1
            if self.fails >= MAX_FAILS:
                s.fetch_fails += 1
                if s.fetch_fails >= ABANDON_FAILS:
                    s.unfetchable = True
                return "revert_wander" if still_angry else "idle"
        return "running"

    def _aim(self, side, cursor):
        """持石手朝光标抬起；石头不在朝光标那侧的手里就先换手。返回是否已瞄好。"""
        b, g = self.body, self.gfx
        want = "r" if self.throw_dir > 0 else "l"
        if side != want or b.switch_hands > 0.0:
            b.start_switch_hands()
            g.hand_aim["l"] = g.hand_aim["r"] = None
            return False
        sx, sy = g._shoulder(-1.0 if side == "l" else 1.0, g.body_axis())
        dx, dy = cursor[0] - sx, cursor[1] - sy
        d = math.hypot(dx, dy)
        if d > 1e-6:
            g.hand_aim[side] = (sx + dx / d * AIM_REACH, sy + dy / d * AIM_REACH)
        return True

    def _phase_hold(self, still_angry):
        side = self.body.hand_of(self.target)
        if side is None:
            return "revert_wander" if still_angry else "idle"
        self.body.stop_walk()
        cursor = self.fsm.cursor
        self.gfx.look_at = cursor
        if still_angry:
            if self.timer >= self.abandon_at:
                self.fsm.anger = 0
                return "revert_wander"
            if cursor is None:
                return "running"
            dx = cursor[0] - self._chunk0().x
            if self.throw_dir == 0 or abs(dx) > AIM_DEADBAND:
                self.throw_dir = 1 if dx >= 0 else -1
            self.body.facing = self.throw_dir
            aimed = self._aim(side, cursor)
            if aimed and self.timer >= HOLD_AIM_TICKS and self._can_hit(cursor):
                self.gfx.hand_aim[side] = None
                self.phase = "throw"
                self.throw_t = 0
        else:
            self.throw_dir = 1 if self.rng.random() < 0.5 else -1
            self._line_aim = None
            self.phase = "throw"
            self.throw_t = 0
        return "running"

    def _phase_throw(self, still_angry):
        if self.throw_t == 0:
            base = max(THROW_SPEED_MIN, self.win._WL * THROW_SPEED_FRAC)
            side = self.body.hand_of(self.target)
            if getattr(self.target, "aims_line", False):
                self._thrown = self.body.throw(
                    self.target, self.throw_dir, base, recoil=THROW_RECOIL, aim=self._line_aim
                )
            else:
                self._thrown = self.body.throw(
                    self.target, self.throw_dir, base, up=3.0, recoil=THROW_RECOIL, vy=self._solve_vy(base)
                )
            if self._thrown is not None:
                self.gfx.throw_object(side, self._thrown)
            self.gfx.blink = 15
        if self._thrown is not None:
            self.gfx.look_at = (self._thrown.x, self._thrown.y)
        self.throw_t += 1
        if self.throw_t >= THROW_FRAMES:
            self.fsm._clear_hands()
            return "thrown"
        return "running"
