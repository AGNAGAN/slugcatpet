"""打猎控制器：拿武器 → 走到能出手的位置 → 按提前量瞄准扔；猎物在头顶时后空翻往上扔。update() 返回 running / done / giveup。"""

from __future__ import annotations

import math

from ...brain.hands import can_wield
from ...brain.skills.throw import Pitch, WeaponPickup, throw_speed
from ...items.base import alive_creature

AIM_MIN_TICKS = 10  # 瞄准至少这么久才扔
AIM_TIMEOUT = 160  # 一直等不到出手机会就换个位置
MAX_REPOS = 2  # 换这么多次位置还扔不出去就放弃
STALK_REPICK = 20  # 走位目标每隔这么久重算
HUNT_TIMEOUT = 1500
WATCH_TICKS = 30  # 扔出后看一会儿结果
MAX_THROWS = 3
NEAR = 30.0  # 离走位目标这么近算到了
STAND_MIN = 90.0  # 离猎物至少这么远（水平）
LINE_SLOPE = 1.15  # 扎得进的：水平距离 ≥ 高度 × 此值（约 41° 以内）
ARC_SLOPE = 3.5  # 石头：水平距离 ≥ 高度 × 此值（约 16° 以内）
FLIP_STEEP = 41.4  # 猎物仰角超过这个（横扔够不着）、又够近时后空翻往上扔
FLIP_NEAR = 60.0  # 猎物水平偏离这么近才翻
FLIP_HIGH = 420.0  # 再高翻上去也扔不到
FLIP_APEX_VY = -2.0  # 上升慢到这里出手（y↓）
FLIP_TIMEOUT = 40


def needs_pierce(o) -> bool:
    """大活物：石头只能砸晕，要扎得进的武器才打得死。"""
    return getattr(o, "stops_weapons", False)


def is_prey(o):
    """活着、没被拿着、眼下能当猎物打的活物。"""
    return alive_creature(o) and o.state == "free" and o.held_by_hand is None and o.huntable


class Hunter:
    def __init__(self, fsm, prey_pick, grow=None):
        self.fsm = fsm
        self.win = fsm.win
        self.body = fsm.body
        self.gfx = fsm.gfx
        self.prey_pick = prey_pick  # () → 猎物或 None
        self.grow = grow  # 技能槽 grow_weapon：只用身上长出的武器
        self.prey = None
        self.phase = "arm"
        self.timer = 0
        self.t = 0
        self.throws = 0
        self.repos = 0
        self.weapon = None
        self.pickup = None
        self.pitch = None
        self.want_x = None

    # 武器

    def _usable(self, o):
        if self.grow is not None:
            return getattr(o, "feeds", None) is self.body
        return getattr(o, "throwable", False) and can_wield(self.body, o, hunting=True) and self._fits(o)

    def _fits(self, o):
        """这件武器对得上眼下的猎物。"""
        p = self.prey
        return p is None or not needs_pierce(p) or getattr(o, "pierces", False)

    def held_weapon(self):
        return next((o for o in self.body.held_items() if self._usable(o)), None)

    def _to_aim(self, w):
        self.weapon = w
        self.pitch = Pitch(self.fsm, w, spare_cursor=True)
        self.phase = "aim"
        self.t = 0
        self.want_x = None

    # 推进

    def update(self) -> str:
        self.timer += 1
        if self.timer > HUNT_TIMEOUT:
            return "giveup"
        if self.phase in ("arm", "aim", "flip") and (self.prey is None or not is_prey(self.prey)):
            self.prey = self.prey_pick()
            if self.prey is None:
                return "giveup"
        return getattr(self, "_phase_" + self.phase)()

    def _phase_arm(self):
        w = self.held_weapon()
        if w is not None:
            self._to_aim(w)
            return "running"
        if self.grow is not None:
            self.phase = "grow"
            return "running"
        self.pickup = WeaponPickup(self.fsm, lambda s, d: d, "Hunt", hunting=True, accept=self._fits)
        if not self.pickup.select():
            return "giveup"
        self.phase = "fetch"
        return "running"

    def _phase_grow(self):
        self.gfx.look_at = (self.prey.x, self.prey.y) if self.prey is not None else None
        r = self.grow.update()
        if r == "got":
            self._to_aim(self.grow.weapon)
        elif r == "fail":
            return "giveup"
        return "running"

    def _phase_fetch(self):
        pk = self.pickup
        if not pk.available():
            return "giveup"
        r = pk.update()
        if r == "got":
            self._to_aim(pk.target)
        elif r == "failed":
            return "giveup"
        return "running"

    def _lead(self):
        """猎物在武器飞到时的大概位置。"""
        p, c0 = self.prey, self.body.chunk0
        d = math.hypot(p.x - c0.x, p.y - c0.y)
        fs = getattr(self.weapon, "flight_speed", None)
        v = fs(self.body) if fs is not None else throw_speed(self.win)
        n = d / max(v, 1.0)
        return p.x + p.vx * n, p.y + p.vy * n

    def _stand_x(self, pt, close=False):
        """能出手的站位：离猎物水平距离按武器能打的仰角定，太靠边就换另一侧；close 时贴上去逼它先跳。"""
        b = self.body
        above = max(0.0, b.chunk0.y - pt[1])
        slope = LINE_SLOPE if getattr(self.weapon, "aims_line", False) else ARC_SLOPE
        need = 0.0 if close else max(STAND_MIN, above * slope)
        lo = b.walk_min if b.walk_min is not None else 0.0
        hi = b.walk_max if b.walk_max is not None else self.win._WL
        side = 1.0 if b.chunk0.x >= pt[0] else -1.0
        for s in (side, -side):
            x = pt[0] + s * need
            if lo <= x <= hi:
                return x
        return min(hi, max(lo, pt[0] + side * need))

    def _steep(self, pt):
        c0 = self.body.chunk0
        dx, above = abs(pt[0] - c0.x), c0.y - pt[1]
        return (
            above > 0.0
            and above < FLIP_HIGH
            and dx < FLIP_NEAR
            and math.degrees(math.atan2(above, max(dx, 1e-6))) > FLIP_STEEP
        )

    def _phase_aim(self):
        b, pitch = self.body, self.pitch
        if pitch.side() is None:
            self.phase = "arm"
            return "running"
        pt = self._lead()
        self.gfx.look_at = pt
        wait = not getattr(self.prey, "exposed", True)
        if not wait and self._steep(pt) and b.on_floor():
            b.stop_walk()
            b.backflip_launch(1 if pt[0] >= b.chunk0.x else -1)
            self.phase = "flip"
            self.t = 0
            return "running"
        self.t += 1
        pitch.face(pt)
        if pitch.can_hit(pt) and not wait:
            b.stop_walk()
            b.facing = pitch.throw_dir
            if pitch.aim(pt) and self.t >= AIM_MIN_TICKS:
                pitch.release()
                self.phase = "throw"
            return "running"
        if self.want_x is None or self.t % STALK_REPICK == 0:
            self.want_x = self._stand_x(pt, close=wait)
        if abs(b.chunk0.x - self.want_x) > NEAR:
            b.walk_to(self.want_x)
        else:
            b.stop_walk()
            pitch.aim(pt)
        if self.t > AIM_TIMEOUT:
            self.repos += 1
            if self.repos >= MAX_REPOS:
                return "giveup"
            self.t = 0
            self.want_x = None
        return "running"

    def _phase_flip(self):
        b = self.body
        self.t += 1
        self.gfx.look_at = (self.prey.x, self.prey.y)
        if b.animation != "Flip" and self.t > 3:
            self.phase = "aim"
            self.t = 0
            return "running"
        if b.chunk0.vy > FLIP_APEX_VY or self.t > FLIP_TIMEOUT:
            self.pitch.release_vertical(-1)
            self.phase = "throw"
        return "running"

    def _phase_throw(self):
        if self.pitch.update(self._lead() if self.prey is not None else None) == "thrown":
            self.throws += 1
            self.phase = "watch"
            self.t = 0
        return "running"

    def _phase_watch(self):
        self.t += 1
        w = self.pitch.thrown
        if w is not None:
            self.gfx.look_at = (w.x, w.y)
        if self.t < WATCH_TICKS:
            return "running"
        if self.prey is not None and getattr(self.prey, "dead", False):
            return "done"
        if self.throws >= MAX_THROWS:
            return "giveup"
        self.prey = None
        self.phase = "arm"
        return "running"

    def release(self):
        """收尾：没扔出去的武器留着，抬着的手放下。"""
        b, g = self.body, self.gfx
        b.stop_walk()
        b.arm_aim["l"] = b.arm_aim["r"] = None
        g.hand_aim["l"] = g.hand_aim["r"] = None
        if self.pickup is not None and self.pickup.target is not None:
            self.fsm.social.release(self.win, "stone")
