"""后空翻劫持光标：掠过光标时劫持，贴身携带 5~10 秒后释放。"""

from __future__ import annotations

import math
from types import SimpleNamespace

from ...abilities.base import Param
from ...brain import maneuver
from ... import tuning
from ...planning.reach import walk_band
from ...planning.backflip_reach import best_launch_hit, sweep_hit_topsafe, takeoff_c0_h
from ...planning.jump_reach import SETTLE_MAX, SETTLE_VX
from ...planning.jump_arc import get_backflip_arc
from ...brain.skills.motor import arc_blocked, rain_blocks
from ...brain.state import T_ACTIVITY, VIGOROUS
from ..base import Behavior

SPEED_RELEASE = tuning.CURSOR_SPEED_RELEASE

PLAN_R = 30.0
CATCH_R = 24.0
HOLD_MAX = 700
WALK_TIMEOUT = 400
SNATCH_TIMEOUT = 800
ARRIVE_X = 16.0
LAUNCH_TIMEOUT = 80
# 光标离地面的高度在这个范围内才去够
SNATCH_MIN_ABOVE = 35.0
SNATCH_MAX_ABOVE = 180.0
MIN_LAUNCH_DX = 25.0  # 起跳点至少离光标这么远，免得原地直上
# 带着光标时进入这些状态就放开
_CARRY_BREAK = frozenset(("Dragged", "Stunned", "Dead", "Swimming"))


class RivSnatch(Behavior):
    key = "riv_snatch"
    title = {"zh": "后空翻劫持光标", "en": "Backflip snatch"}
    doc = "光标停在离地不高处够久：跑位、后空翻掠过时叼走光标，落地后贴身带着它走一会再放开。"
    requires = ("acrobat",)
    params = {
        "dwell_ticks": Param(tuning.CURSOR_DWELL_TICKS, 1, 4000, "光标在高度带内停留多少 tick 才触发"),
        "carry_min": Param(200, 1, 4000, "叼住后最短带多久（tick）"),
        "carry_max": Param(400, 1, 4000, "叼住后最长带多久（tick）"),
        "cooldown": Param(1200, 0, 100000, "成功劫持后的冷却（tick）"),
        "cooldown_abort": Param(300, 0, 100000, "放弃 / 扑空后的冷却（tick）"),
    }

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    snatch = SimpleNamespace()
    snatch.cooldown = 0
    snatch.hj = None
    snatch.dirty = False
    snatch.plan = None
    snatch.carry = 0
    snatch.dwell = 0  # 光标在高度带内静止的 tick 数

    def in_band(cursor):
        return cursor is not None and SNATCH_MIN_ABOVE <= fsm.HL - cursor[1] <= SNATCH_MAX_ABOVE

    def plan(cursor):
        if not in_band(cursor):
            return None
        # 两个方向的加力后空翻都试，挑起跳点；没有说明光标太高或太远
        cx, cy = cursor
        stats = fsm.win.cat.stats
        launch_y = fsm.HL - takeoff_c0_h(stats)
        xmin, xmax = walk_band(fsm.win)
        hipx = fsm.body.chunk1.x
        best = None
        for d in (1, -1):
            arc = get_backflip_arc(stats, d, boosted=True)
            r = best_launch_hit(arc, cx, cy, launch_y, xmin, xmax, PLAN_R, hipx)
            if r is None or abs(r[0] - cx) < MIN_LAUNCH_DX or (best is not None and r[2] >= best[2]):
                continue
            if (
                rain_blocks(fsm, (r[0], fsm.HL - 1.0))
                or arc_blocked(fsm, r[0], launch_y, arc.points)
                or fsm.body.reach(r[0], ARRIVE_X) is None
            ):
                continue
            best = (r[0], d, r[2])
        return None if best is None else (best[0], best[1])

    def can_snatch():
        b = fsm.body
        return (
            fsm.state == "IdleStand"
            and fsm.cursor is not None
            and not fsm.grab.active
            and not fsm.ask("exhausted")
            and not fsm._zerog()
            and not b.swimming
            and fsm.win.cursor_hijack is None
            and in_band(fsm.cursor)
            and not rain_blocks(fsm, fsm.cursor)
            and snatch.cooldown <= 0
            and snatch.dwell >= p.dwell_ticks
        )

    def body_mid():
        c0, c1 = fsm.body.chunk0, fsm.body.chunk1
        return ((c0.x + c1.x) * 0.5, (c0.y + c1.y) * 0.5)

    def carry_tick():
        hj = snatch.hj
        bad = (
            hj is None
            or fsm.win.cursor_hijack is not hj
            or not hj.active
            or fsm.grab.active
            or fsm.body.dead
            or fsm.body.swimming
            or fsm._zerog()
            or fsm.state in _CARRY_BREAK
        )
        snatch.carry -= 1
        if bad or snatch.carry <= 0:
            snatch.carry = 0
            maneuver.release_hold(fsm.win, snatch)
        else:
            fsm.win.move_cursor_hold(*body_mid())

    def watch():
        if snatch.cooldown > 0:
            snatch.cooldown -= 1
        if snatch.carry > 0:
            carry_tick()
        still = in_band(fsm.cursor) and fsm._cursor_speed < tuning.CURSOR_DWELL_TOL
        snatch.dwell = snatch.dwell + 1 if still else 0
        if fsm.state == "RivSnatch":
            return
        if snatch.dirty:
            maneuver.release_hold(fsm.win, snatch)
            maneuver.clear_motion(fsm.body, snatch)
        if can_snatch():
            pl = plan(fsm.cursor)
            if pl is not None:
                snatch.plan = pl
                snatch.cooldown = p.cooldown
                fsm._transition("RivSnatch")

    def enter():
        b = fsm.body
        b.set_posture(True)
        fsm._clear_hands()
        snatch.phase = "walk"
        snatch.settle = 0
        snatch.launch_t = 0
        snatch.airborne = False
        snatch.hj = None
        snatch.d = 0
        snatch.dirty = True
        snatch.x = snatch.plan[0] if snatch.plan is not None else None
        if snatch.x is not None:
            b.walk_to(snatch.x, ARRIVE_X)  # 挑的时候已判过走得到

    def finish(b, ok):
        brk(cooldown=p.cooldown if ok else p.cooldown_abort)
        fsm.settle()

    def pick_at_launch(cursor):
        c0 = fsm.body.chunk0
        stats = fsm.win.cat.stats
        first = 1 if cursor[0] >= c0.x else -1
        for d in (first, -first):
            arc = get_backflip_arc(stats, d, boosted=True)
            if sweep_hit_topsafe(
                arc, cursor[0] - c0.x, cursor[1] - c0.y, PLAN_R, c0.y
            ) is not None and not arc_blocked(fsm, c0.x, c0.y, arc.points):
                return d
        return None

    def st_rivsnatch(cursor, disturbed):
        b = fsm.body
        if maneuver.hold_lost(fsm.win, snatch):
            finish(b, ok=True)
            return
        if fsm.timer > SNATCH_TIMEOUT or snatch.x is None:
            finish(b, ok=False)
            return
        ph = snatch.phase
        if ph == "walk":
            if (
                cursor is None
                or not in_band(cursor)
                or rain_blocks(fsm, cursor)
                or fsm._cursor_speed > SPEED_RELEASE
                or fsm.timer > WALK_TIMEOUT
            ):
                finish(b, ok=False)
                return
            fsm.gfx.look_at = cursor
            dx = abs(b.chunk1.x - snatch.x)
            overshot = (b.chunk1.vx > 0 and b.chunk1.x >= snatch.x) or (
                b.chunk1.vx < 0 and b.chunk1.x <= snatch.x
            )
            if b.on_floor() and (not b.is_moving() or dx < ARRIVE_X or overshot):
                b.stop_walk()
                b.walk_speed_target = None
                snatch.phase = "settle"
            else:
                b.walk_speed_target = 3.5 if dx < 32.0 else None
                if not b.walk_to(snatch.x, ARRIVE_X):
                    finish(b, ok=False)
            return
        if ph == "settle":
            if cursor is None or fsm._cursor_speed > SPEED_RELEASE:
                finish(b, ok=False)
                return
            b.stop_walk()
            b.walk_speed_target = None
            snatch.settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or snatch.settle > SETTLE_MAX):
                d = pick_at_launch(cursor)
                if d is None:
                    finish(b, ok=False)
                    return
                b.backflip_launch(d, boosted=True)
                snatch.d = d
                snatch.phase = "air"
                snatch.launch_t = 0
            return
        if not b.on_floor():
            snatch.airborne = True
            b.move_dir = snatch.d
            if snatch.hj is None and cursor is not None and fsm.win.cursor_hijack is None:
                mx, my = body_mid()
                c0 = b.chunk0
                near = min(
                    math.hypot(cursor[0] - mx, cursor[1] - my), math.hypot(cursor[0] - c0.x, cursor[1] - c0.y)
                )
                if near <= CATCH_R:
                    snatch.hj = fsm.win.start_cursor_hold(mx, my, HOLD_MAX)
            if snatch.hj is not None:
                fsm.win.move_cursor_hold(*body_mid())
        elif snatch.airborne:
            if snatch.hj is not None:
                maneuver.clear_motion(fsm.body, snatch)
                b.set_posture(True)
                snatch.carry = fsm.rng.randint(p.carry_min, max(p.carry_min, p.carry_max))
                snatch.cooldown = p.cooldown
                fsm._transition("IdleStand")
            else:
                finish(b, ok=False)
        else:
            snatch.launch_t += 1
            if snatch.launch_t > LAUNCH_TIMEOUT:
                finish(b, ok=False)

    def brk(cooldown=None):
        if cooldown is None:
            cooldown = p.cooldown_abort
        d = fsm.body.move_dir
        maneuver.release_hold(fsm.win, snatch)
        maneuver.clear_motion(fsm.body, snatch)
        maneuver.stand_facing(fsm.body, d)
        fsm._clear_hands()
        snatch.cooldown = cooldown

    fsm.register_ticker(watch)
    fsm.register_state(
        "RivSnatch", enter=enter, tick=st_rivsnatch, brk=brk, kill_break=brk, tier=T_ACTIVITY, energy=VIGOROUS
    )
