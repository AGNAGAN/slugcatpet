"""站着待机的状态，失重时漂浮。"""

from __future__ import annotations

import math

from ... import tuning
from ...core.creature import ZEROG_GRAB_DIST, _closest_on_segment
from ...brain.state import State, IDLE
from ...brain.skills import motor
from ...brain.skills.motor import WALL_MARGIN
from ...items.base import CLIMBABLE

# 失重漂浮
ZEROG_ARRIVE_R = 30.0
ZEROG_KICK_FAR = 60.0
ZEROG_TWITCH_PROB = 0.02
ZEROG_CURSOR_FRAC = 0.6
# 失重抓杆：沿杆来回滑一会再松手
ZEROG_GRAB_ALIGN = 12.0
ZEROG_POLE_COOLDOWN = 40
ZEROG_POLE_SEEK_R = 220.0
ZEROG_POLE_SEEK_PROB = 0.5
ZEROG_POLE_PLAY_TICKS = 120
ZEROG_SLIDE_PERIOD = 30
ZEROG_BACK_KICK = 0.5  # 被挡住蹬开时往回的分量
ZEROG_DODGE_KICK = 0.4  # 被挡住蹬开的力度


def _stare_nearness(d):
    """对视邻近度 0..1，越近越大。"""
    span = max(1.0, tuning.STARE_DIST_MAX - tuning.STARE_DIST_NEAR)
    t = max(0.0, min(1.0, 1.0 - (d - tuning.STARE_DIST_NEAR) / span))
    return t**tuning.STARE_DECAY_MULT


class IdleStand(State):
    name = "IdleStand"
    energy = IDLE

    def __init__(self, fsm):
        super().__init__(fsm)
        self._idle_hold = 0
        self._zerog_pole_cd = 0
        self._zerog_pole_play = 0
        self._zerog_slide_sign = 1.0
        self._zerog_target = None
        self._stare = 0
        self._stare_with = None
        self._stare_cd = 0

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.set_posture(True)
        b.stop_walk()
        self._idle_hold = tuning.IDLE_BREATHER
        self._stare = 0
        self._stare_with = None

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        if fsm._zerog():
            self._zerog_idle(cursor)
            return
        self._update_stare()
        if self._stare > 0:
            self._stare -= 1
            ob = self._stare_with.body
            fsm.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
            if self._stare <= 0:
                self._end_stare()
            self._idle_pace()
            return
        fsm.gfx.look_at = fsm._ambient_look(cursor)
        if self._idle_hold > 0:
            self._idle_hold -= 1
            self._idle_pace()
            return
        if fsm.intents.pick():
            return
        self._idle_hold = self._roll_idle_hold()
        self._idle_pace()

    def _end_stare(self):
        fsm = self.fsm
        self._stare = 0
        self._stare_with = None
        self._stare_cd = fsm.rng.randint(tuning.STARE_COOLDOWN_MIN, tuning.STARE_COOLDOWN_MAX)

    def _idle_on_floor(self, o):
        ob = getattr(o, "body", None)
        return (
            ob is not None
            and self.fsm.social.state_of(o) == "IdleStand"
            and ob.on_floor()
            and not ob.is_moving()
        )

    def _update_stare(self):
        fsm = self.fsm
        if self._stare_cd > 0:
            self._stare_cd -= 1
        if self._stare > 0:
            if not self._idle_on_floor(self._stare_with):
                self._end_stare()
            return
        if self._stare_cd > 0:
            return
        b = fsm.body
        best, bd = None, None
        for o in fsm.social.others(fsm.win):
            ob = o.body
            if not self._idle_on_floor(o):
                continue
            d = math.hypot(ob.chunk1.x - b.chunk1.x, ob.chunk1.y - b.chunk1.y)
            if d <= tuning.STARE_DIST_MAX and (bd is None or d < bd):
                best, bd = o, d
        if best is None:
            return
        prob = tuning.STARE_BASE_PROB + (tuning.STARE_NEAR_PROB - tuning.STARE_BASE_PROB) * _stare_nearness(
            bd
        )
        prob *= fsm.traits.activity
        if bd < tuning.STARE_ENGAGE_DIST:
            prob *= tuning.STARE_ENGAGE_MULT
        if fsm.rng.random() < prob:
            self._stare_with = best
            self._stare = fsm.rng.randint(tuning.STARE_LOCK_MIN, tuning.STARE_LOCK_MAX)

    def _idle_pace(self):
        fsm = self.fsm
        p = tuning.PACE_PROB * fsm.traits.activity * fsm.ask("listless", 1.0)
        if not fsm.body.is_moving() and fsm.rng.random() < p:
            motor.wander(fsm)

    def _roll_idle_hold(self):
        """接着闲待一阵再重选。"""
        return self.fsm.rng.randint(tuning.HANG_HOLD_MIN, tuning.HANG_HOLD_MAX)

    def _zerog_idle(self, cursor):
        fsm = self.fsm
        b = fsm.body
        b.stop_walk()
        if fsm.run_tasks("zerog"):
            b.zerog_pole = None
            return
        fsm.gfx.look_at = fsm._ambient_look(cursor)
        if self._zerog_pole_cd > 0:
            self._zerog_pole_cd -= 1

        if fsm._zerog_entered:
            fsm._zerog_entered = False
            if self._zerog_pole_cd <= 0:
                pole = self._zerog_nearest_pole(b.chunk0.x, b.chunk0.y)
                if pole is not None:
                    b.zerog_pole = pole
                    b.zerog_pole_intent = (0.0, 0.0)
                    self._zerog_pole_play = 0

        if b.zerog_pole is not None:
            self._zerog_on_pole(b)
            return

        tx, ty = self._zerog_pick_target(cursor)
        dx, dy = tx - b.chunk0.x, ty - b.chunk0.y
        dist = math.hypot(dx, dy)
        if dist > ZEROG_ARRIVE_R:
            ux, uy = dx / dist, dy / dist
            if self._zerog_try_pole(b, tx, ty):
                return
            on_wall = b.canJump > 0
            b.zerog_swim(ux, uy, on_wall)
            if on_wall and dist > ZEROG_KICK_FAR:
                b.request_zerog_kick(ux, uy)
        else:
            self._zerog_target = None
            if fsm.rng.random() < ZEROG_TWITCH_PROB:
                ang = fsm.rng.uniform(0.0, math.tau)
                b.zerog_swim(math.cos(ang), math.sin(ang), b.canJump > 0)

        fsm.run_tasks("zerog_aim", tx, ty)

    def _zerog_nearest_pole(self, x, y):
        """离 (x, y) 不到 ZEROG_GRAB_DIST 的最近一根杆，没有返回 None。"""
        fsm = self.fsm
        best = None
        best_d = ZEROG_GRAB_DIST
        for p in fsm.items(CLIMBABLE):
            d = _closest_on_segment(x, y, p.ax, p.ay, p.bx, p.by)[2]
            if d < best_d:
                best_d = d
                best = p
        return best

    def _zerog_on_pole(self, b):
        pole = b.zerog_pole
        lx, ly = pole.bx - pole.ax, pole.by - pole.ay
        ll = math.hypot(lx, ly) or 1.0
        axis_x, axis_y = lx / ll, ly / ll
        perp_x, perp_y = -axis_y, axis_x
        t = self._zerog_target
        if t is None:
            along = perp = 0.0
        else:
            rx, ry = t[0] - b.chunk0.x, t[1] - b.chunk0.y
            along = rx * axis_x + ry * axis_y
            perp = rx * perp_x + ry * perp_y
        if abs(along) > ZEROG_GRAB_ALIGN and abs(perp) <= ZEROG_GRAB_DIST:
            self._zerog_pole_play = 0
            s = 1.0 if along > 0.0 else -1.0
        else:
            self._zerog_pole_play += 1
            if self._zerog_pole_play % ZEROG_SLIDE_PERIOD == 0:
                self._zerog_slide_sign = -self._zerog_slide_sign
            s = self._zerog_slide_sign
        b.zerog_pole_intent = (axis_x * s, axis_y * s)
        blocked = s == b.lane_hold
        if blocked or self._zerog_pole_play >= ZEROG_POLE_PLAY_TICKS:
            if blocked:  # 被同一根杆上的猫挡住：往侧后方蹬开
                side = self.fsm.rng.choice((-1.0, 1.0))
                kx, ky = (
                    perp_x * side - axis_x * s * ZEROG_BACK_KICK,
                    perp_y * side - axis_y * s * ZEROG_BACK_KICK,
                )
                k = math.hypot(kx, ky)
                b.zerog_pole_kick(kx / k * ZEROG_DODGE_KICK, ky / k * ZEROG_DODGE_KICK)
                self._zerog_target = None
            b.zerog_pole = None
            self._zerog_pole_play = 0
            self._zerog_pole_cd = ZEROG_POLE_COOLDOWN

    def _zerog_pick_target(self, cursor):
        fsm = self.fsm
        t = self._zerog_target
        if t is not None:
            return t
        if self._zerog_pole_cd <= 0 and fsm.rng.random() < ZEROG_POLE_SEEK_PROB:
            b = fsm.body
            pole = self._zerog_seek_pole(b.chunk0.x, b.chunk0.y)
            if pole is not None:
                cx, cy, _ = _closest_on_segment(b.chunk0.x, b.chunk0.y, pole.ax, pole.ay, pole.bx, pole.by)
                self._zerog_target = (cx, cy)
                return self._zerog_target
        if cursor is not None and fsm.rng.random() < ZEROG_CURSOR_FRAC:
            t = (float(cursor[0]), float(cursor[1]))
        else:
            t = (
                fsm.rng.uniform(WALL_MARGIN, fsm.WL - WALL_MARGIN),
                fsm.rng.uniform(WALL_MARGIN, fsm.HL - WALL_MARGIN),
            )
        self._zerog_target = t
        return t

    def _zerog_seek_pole(self, x, y):
        """主动找杆：离 (x, y) 不到 ZEROG_POLE_SEEK_R 的最近一根杆，没有返回 None。"""
        fsm = self.fsm
        best = None
        best_d = ZEROG_POLE_SEEK_R
        for p in fsm.items(CLIMBABLE):
            d = _closest_on_segment(x, y, p.ax, p.ay, p.bx, p.by)[2]
            if d < best_d:
                best_d = d
                best = p
        return best

    def _zerog_try_pole(self, b, tx, ty):
        if self._zerog_pole_cd > 0:
            return False
        pole = self._zerog_nearest_pole(b.chunk0.x, b.chunk0.y)
        if pole is None:
            return False
        lx, ly = pole.bx - pole.ax, pole.by - pole.ay
        ll = math.hypot(lx, ly) or 1.0
        axis_x, axis_y = lx / ll, ly / ll
        rx, ry = tx - b.chunk0.x, ty - b.chunk0.y
        along = rx * axis_x + ry * axis_y
        s = 1.0 if along > ZEROG_GRAB_ALIGN else (-1.0 if along < -ZEROG_GRAB_ALIGN else 0.0)
        b.zerog_pole = pole
        b.zerog_pole_intent = (axis_x * s, axis_y * s)
        self._zerog_pole_play = 0
        return True
