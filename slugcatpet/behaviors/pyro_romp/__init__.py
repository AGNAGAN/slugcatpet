"""爆跳撒欢。"""

from __future__ import annotations

from types import SimpleNamespace

from ...abilities.base import Param
from ...abilities.pyro import mechanics as pyro
from ...brain import maneuver
from ... import tuning
from ...brain.skills.motor import arc_blocked, open_span, pick_open_x
from ...brain.state import T_ACTIVITY, VIGOROUS
from ...planning.backflip_reach import SETTLE_MAX, SETTLE_VX, takeoff_c0_h
from ...planning.jump_arc import PYRO_INPUTS, get_pyro_arc
from ..base import Behavior, mood_candidate, mood_params

ARRIVE_X = 8.0  # px
LAUNCH_TIMEOUT = 80  # 起跳后这么久还没离地（被顶住、卡住）就收工
ROMP_TIMEOUT = 1200  # tick
SCAN_STEP = 16.0  # 大雨时找起跳点的取样间隔
PICKS = 6  # 挑空地时随机试这么多个，取第一个走得到的


class PyroRomp(Behavior):
    key = "pyro_romp"
    mood = "pyro_romp"
    title = {"zh": "爆跳撒欢", "en": "Pyro romp"}
    doc = "无聊时找块空地连续爆跳几下；燃料不够一整轮就不玩。"
    requires = ("pyro",)
    params = mood_params(1.00, 0.72, 0.30, 0.30, 0.0040, 0.00055, jumps=Param(2, 1, 5, "一轮连跳次数"))

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    romp = SimpleNamespace(spot=None)
    pyro_ab = fsm.win.abilities["pyro"]

    def fuel_ok(cost):
        return pyro_ab.fuel_ok(fsm.body, cost)

    def variants(x, y):
        """在 (x, y) 起跳时能用的变体：竖跳和朝屏幕中间的斜跳，去掉大雨时会飞出遮挡的。"""
        diag = "diag+" if x < fsm.WL * 0.5 else "diag-"
        stats = fsm.win.cat.stats
        return [v for v in ("vert", diag) if not arc_blocked(fsm, x, y, get_pyro_arc(stats, v).points)]

    def dry_spots():
        """大雨时空地上至少有一种爆跳不出遮挡的起跳点。"""
        lo, hi = open_span(fsm)
        y = fsm.HL - takeoff_c0_h(fsm.win.cat.stats)
        xs = [lo + k * SCAN_STEP for k in range(int((hi - lo) // SCAN_STEP) + 1)]
        return [x for x in xs if variants(x, y)]

    def next_round():
        romp.phase = "walk"
        romp.settle = 0
        romp.air = 0
        romp.launch_t = 0
        romp.fired = False
        romp.airborne = False
        romp.x, romp.spot = romp.spot if romp.spot is not None else spot(), None
        if romp.x is not None and not fsm.body.walk_to(romp.x, ARRIVE_X):
            romp.x = None  # 走不到了：收工

    def spot():
        """挑一处走得到的空地；大雨时只在爆跳不出遮挡的地方挑。没有 None。"""
        xs = dry_spots() if fsm.win.rain.dangerous() else [pick_open_x(fsm) for _ in range(PICKS)]
        fsm.rng.shuffle(xs)
        return next((x for x in xs if fsm.body.reach(x, ARRIVE_X) is not None), None)

    def enter():
        fsm.body.set_posture(True)
        fsm._clear_hands()
        romp.jumps = 0
        romp.dirty = True
        next_round()

    def pick_variant():
        c0 = fsm.body.chunk0
        vs = variants(c0.x, c0.y)
        if not vs:
            return None
        return vs[0] if fsm.rng.random() < 0.5 else vs[-1]

    def finish(b):
        brk()
        fsm.settle()

    def st_pyroromp(cursor, disturbed):
        b = fsm.body
        if fsm.timer > ROMP_TIMEOUT or romp.x is None:
            finish(b)
            return
        ph = romp.phase
        if ph == "walk":
            if b.on_floor() and not b.is_moving():
                b.stop_walk()
                romp.phase = "settle"
            return
        if ph == "settle":
            b.stop_walk()
            romp.settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or romp.settle > SETTLE_MAX):
                if not fuel_ok(1):
                    finish(b)
                    return
                romp.variant = pick_variant()
                if romp.variant is None:
                    finish(b)
                    return
                b.request_jump("stand")
                romp.phase = "air"
                romp.launch_t = 0
            return
        if not b.on_floor():
            romp.airborne = True
            romp.air += 1
            if not romp.fired and romp.air >= tuning.PYRO_BOOST_AIR_TICKS:
                romp.fired = True
                if fuel_ok(1):
                    ix, iy = PYRO_INPUTS[romp.variant]
                    pyro.fire_air_jump(fsm.win, b, ix, iy)
        elif romp.airborne:
            b.animation = None
            b.jump_boost = 0.0
            b.set_posture(True)
            romp.jumps += 1
            if romp.jumps >= p.jumps or not fuel_ok(1):
                finish(b)
            else:
                next_round()
        else:
            romp.launch_t += 1
            if romp.launch_t > LAUNCH_TIMEOUT:
                finish(b)

    def brk():
        d = fsm.body.move_dir
        maneuver.clear_motion(fsm.body, romp)
        maneuver.stand_facing(fsm.body, d)

    fsm.register_ticker(maneuver.leak_watch(fsm, "PyroRomp", romp))
    fsm.register_state(
        "PyroRomp",
        enter=enter,
        tick=st_pyroromp,
        brk=brk,
        kill_break=brk,
        mood="pyro_romp",
        tier=T_ACTIVITY,
        energy=VIGOROUS,
    )

    def gate(ctx):
        romp.spot = None
        if not ctx.submerged and not getattr(fsm.body, "zerog", False) and ctx.energy >= fsm.traits.play_gate:
            romp.spot = spot() if pyro_ab.fuel_ok(fsm.body, p.jumps) else None  # 进来就去这
        return romp.spot is not None

    mood_candidate(fsm, "pyro_romp", p, gate)
