"""爆跳扑咬。"""
from __future__ import annotations

import math
from types import SimpleNamespace

from ...brain import maneuver
from ...brain.skills.motor import BITE_HEAD_NUDGE
from ...control.mouse import is_over
from ...planning.jump_reach import SETTLE_MAX, SETTLE_VX
from ...abilities.base import Param
from ...abilities.pyro import mechanics as pyro
from ...brain.state import T_ACTIVITY, VIGOROUS
from ..base import Behavior

BODY_LEN = 34.0          # 一个身位：chunk 间距 17 + 两端半径
OVER_PAD = 6.0
NEAR_DIST = BODY_LEN
NEAR_GIVEUP = BODY_LEN * 2.5
NEAR_CATCH_R = 30.0
POUNCE_MIN = BODY_LEN * 2.0
POUNCE_MAX = 350.0
POUNCE_MAX_RISE = 160.0  # 高于此够不到（vert/diag apex ~165）
CATCH_R = 26.0
HOLD_MAX = 400
LAUNCH_TIMEOUT = 80
APPROACH_TIMEOUT = 200
MAUL_TIMEOUT = 600
CHEW_TICKS = 60          # ~1.5s
BITE_PERIOD = 8          # 原版 maul：每 8 tick 一口
JITTER_PERIOD = 3        # 原版 maul：每 3 tick 身体微抖
JITTER_AMP = 1.2


def _fire_tick_for(dist):
    if dist < 95.0:
        return 18
    if dist < 145.0:
        return 16
    if dist < 185.0:
        return 14
    if dist < 235.0:
        return 13
    return 8


def _variant_for(dx, dy):
    adx = abs(dx)
    sx = 1 if dx >= 0 else -1
    if adx < 40.0 and dy < -90.0:
        return (0, 0)
    if -dy > adx * 0.7:
        return (sx, 1)
    return (sx, 0)


class PyroMaul(Behavior):
    key = "pyro_maul"
    title = {"zh": "爆跳扑咬", "en": "Pyro maul"}
    doc = "好感低时，光标从身边经过后移远：概率爆跳扑上去叼住；光标贴身停留：走过去叼住。叼住啃几口后松开。"
    requires = ("pyro",)
    params = {
        "temper_gate": Param(-0.50, -1.0, 1.0, "好感 ≤ 此值才会扑咬"),
        "pounce_prob": Param(0.30, 0.0, 1.0, "光标经过后移远时爆跳扑抓的概率"),
        "near_ticks": Param(120, 1, 4000, "光标贴身停留多少 tick 后走过去叼"),
        "cooldown": Param(1200, 0, 100000, "扑咬后冷却 tick（两种模式共用）"),
    }

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    maul = SimpleNamespace()
    pyro_ab = fsm.win.abilities["pyro"]
    temper_gate = p.temper_gate
    maul.cooldown = 0
    maul.over = False
    maul.pass_ = False
    maul.near_t = 0
    maul.rolled = False
    maul.mode = "pounce"
    maul.hj = None
    maul.dirty = False

    def fuel_ok():
        return pyro_ab.fuel_ok(fsm.body)

    def body_dist(cursor):
        c0, c1 = fsm.body.chunk0, fsm.body.chunk1
        return min(math.hypot(cursor[0] - c0.x, cursor[1] - c0.y),
                   math.hypot(cursor[0] - c1.x, cursor[1] - c1.y))

    def gates_ok():
        b = fsm.body
        if fsm.cursor is not None and fsm.cursor[1] > fsm.HL - 8.0:   # 光标贴着地面咬不到
            return False
        return (fsm.state == "IdleStand" and b.on_floor()
                and not fsm.grab.active and not fsm._exhausted
                and not fsm._zerog() and not b.swimming
                and fsm.win.cursor_hijack is None
                and b.carried_fruit is None and b.carried_stone is None
                and b.temper <= temper_gate and maul.cooldown <= 0)

    def reset_track():
        maul.pass_ = False
        maul.near_t = 0
        maul.rolled = False

    def trigger(mode):
        maul.cooldown = p.cooldown
        maul.mode = mode
        reset_track()
        fsm._transition("PyroMaul")

    def watch():
        if maul.cooldown > 0:
            maul.cooldown -= 1
        cursor = fsm.cursor
        over = cursor is not None and is_over(fsm.body, fsm.gfx, cursor, pad=OVER_PAD)
        if fsm.state == "PyroMaul":
            maul.over = over
            return
        if maul.dirty:
            maneuver.release_hold(fsm.win, maul)
            maneuver.clear_motion(fsm.body, maul)
        if not gates_ok():
            maul.over = over
            reset_track()
            return
        if over:
            if not maul.over:
                maul.pass_ = True
                maul.rolled = False
            maul.near_t += 1      # 悬在身上也算 1 身位内
            if maul.near_t >= p.near_ticks:
                trigger("walkup")
        elif cursor is None:
            reset_track()
        elif maul.pass_:
            d = body_dist(cursor)
            if d <= NEAR_DIST:
                maul.near_t += 1
                if maul.near_t >= p.near_ticks:
                    trigger("walkup")
            else:
                maul.near_t = 0
                if d >= POUNCE_MIN and not maul.rolled:
                    maul.rolled = True
                    rise = fsm.body.chunk0.y - cursor[1]
                    if (fsm.rng.random() < p.pounce_prob and fuel_ok()
                            and d <= POUNCE_MAX and rise <= POUNCE_MAX_RISE):
                        trigger("pounce")
                    else:
                        maul.pass_ = False
        maul.over = over

    def enter():
        b = fsm.body
        b.set_posture(True)
        b.stop_walk()
        fsm._clear_hands()
        maul.phase = "approach" if maul.mode == "walkup" else "settle"
        maul.settle = 0
        maul.air = 0
        maul.ft = 0
        maul.fired = False
        maul.airborne = False
        maul.launch_t = 0
        maul.chew_t = 0
        maul.hj = None
        maul.dirty = True
        if fsm.cursor is not None:
            b.facing = 1 if fsm.cursor[0] >= b.chunk0.x else -1

    def finish(b):
        brk()
        fsm.settle()

    def pin_to_mouth():
        mox, moy = fsm.gfx.mouth_world()
        fsm.win.move_cursor_hold(mox, moy)
        fsm.gfx.hand_aim["l"] = (mox, moy)
        fsm.gfx.hand_aim["r"] = (mox, moy)
        return mox, moy

    def enter_chew(b):
        b.animation = None
        b.jump_boost = 0.0
        b.walk_speed_target = None
        b.stop_walk()
        b.set_posture(False)
        maul.phase = "chew"
        maul.chew_t = 0

    def st_pyromaul(cursor, disturbed):
        b = fsm.body
        if fsm.timer > MAUL_TIMEOUT or maneuver.hold_lost(fsm.win, maul):
            finish(b)
            return
        ph = maul.phase
        if ph == "approach":
            if (cursor is None or body_dist(cursor) > NEAR_GIVEUP
                    or fsm.timer > APPROACH_TIMEOUT):
                finish(b)
                return
            fsm.gfx.look_at = cursor
            mox, moy = fsm.gfx.mouth_world()
            if (math.hypot(cursor[0] - mox, cursor[1] - moy) <= NEAR_CATCH_R
                    and fsm.win.cursor_hijack is None):
                maul.hj = fsm.win.start_cursor_hold(mox, moy, HOLD_MAX)
                if maul.hj is not None:                 # 设置里关了抢光标时咬不住
                    enter_chew(b)
                    return
            dx = abs(cursor[0] - b.chunk1.x)
            if dx < 14.0:                   # 到了光标正下方还咬不到就放弃，别原地来回蹭
                b.stop_walk()
                b.walk_speed_target = None
                if abs(cursor[1] - moy) > NEAR_CATCH_R * 1.3 or cursor[1] > fsm.HL - 8.0:
                    finish(b)
            else:
                b.walk_speed_target = 2.5 if dx < 28.0 else None
                b.walk_to(cursor[0])
            return
        if ph == "settle":
            b.stop_walk()
            b.walk_speed_target = None
            maul.settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or maul.settle > SETTLE_MAX):
                if cursor is None:
                    finish(b)
                    return
                d = body_dist(cursor)
                rise = b.chunk0.y - cursor[1]
                if (d < POUNCE_MIN * 0.7 or d > POUNCE_MAX
                        or rise > POUNCE_MAX_RISE):
                    finish(b)
                    return
                maul.ft = _fire_tick_for(d)
                b.request_jump("stand")
                maul.phase = "air"
                maul.launch_t = 0
            return
        if ph == "air":
            if not b.on_floor():
                maul.airborne = True
                maul.air += 1
                if maul.hj is not None:
                    maul.fired = True
                if not maul.fired and maul.air >= maul.ft:
                    maul.fired = True
                    if cursor is not None and fuel_ok():
                        c0 = b.chunk0
                        ix, iy = _variant_for(cursor[0] - c0.x, cursor[1] - c0.y)
                        pyro.fire_air_jump(fsm.win, b, ix, iy)
                if maul.fired and maul.hj is None and cursor is not None:
                    b.move_dir = 1 if cursor[0] >= b.chunk0.x else -1
                elif maul.hj is not None:
                    b.move_dir = 0
                if maul.hj is None and cursor is not None and fsm.win.cursor_hijack is None:
                    mox, moy = fsm.gfx.mouth_world()
                    if math.hypot(cursor[0] - mox, cursor[1] - moy) <= CATCH_R:
                        maul.hj = fsm.win.start_cursor_hold(mox, moy, HOLD_MAX)
                if maul.hj is not None:
                    pin_to_mouth()
            elif maul.airborne:
                if maul.hj is not None:
                    enter_chew(b)
                else:
                    finish(b)
            else:
                maul.launch_t += 1
                if maul.launch_t > LAUNCH_TIMEOUT:
                    finish(b)
            return
        
        maul.chew_t += 1
        mox, moy = pin_to_mouth()
        fsm.gfx.look_at = (mox, moy)
        if maul.chew_t % JITTER_PERIOD == 0:
            b.chunk0.vx += fsm.rng.uniform(-JITTER_AMP, JITTER_AMP)
            b.chunk0.vy += fsm.rng.uniform(-JITTER_AMP, JITTER_AMP)
        if maul.chew_t % BITE_PERIOD == BITE_PERIOD // 2:
            hd = fsm.gfx.head
            dx, dy = mox - hd.x, moy - hd.y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                hd.vx += dx / d * BITE_HEAD_NUDGE
                hd.vy += dy / d * BITE_HEAD_NUDGE
        if maul.chew_t >= CHEW_TICKS:
            finish(b)

    def brk():
        b = fsm.body
        maneuver.release_hold(fsm.win, maul)
        maneuver.clear_motion(fsm.body, maul)
        b.set_posture(True)
        fsm._clear_hands()
        maul.cooldown = p.cooldown

    fsm.register_ticker(watch)
    fsm.register_state("PyroMaul", enter=enter, tick=st_pyromaul,
                       brk=brk, kill_break=brk, tier=T_ACTIVITY, energy=VIGOROUS)
