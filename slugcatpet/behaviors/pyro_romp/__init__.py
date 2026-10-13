"""爆跳撒欢。"""
from __future__ import annotations

from types import SimpleNamespace

from ...abilities.base import Param
from ...abilities.pyro import mechanics as pyro
from ...brain import maneuver
from ... import tuning
from ...brain.skills.motor import pick_open_x
from ...brain.state import T_ACTIVITY, VIGOROUS
from ...planning.backflip_reach import SETTLE_MAX, SETTLE_VX
from ...planning.jump_arc import PYRO_INPUTS
from ..base import Behavior, mood_candidate, mood_params

ARRIVE_X = 8.0           # px
LAUNCH_TIMEOUT = 80      # 起跳未腾空兜底 tick（被顶/卡住）
ROMP_TIMEOUT = 1200      # tick


class PyroRomp(Behavior):
    key = "pyro_romp"
    mood = "pyro_romp"
    title = {"zh": "爆跳撒欢", "en": "Pyro romp"}
    doc = "无聊时找块空地连续爆跳几下；燃料不够一整轮就不玩。"
    requires = ("pyro",)
    params = mood_params(1.00, 0.72, 0.30, 0.30, 0.0040, 0.00055,
                         jumps=Param(2, 1, 5, "一轮连跳次数"))

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    romp = SimpleNamespace()
    pyro_ab = fsm.win.abilities["pyro"]

    def fuel_ok(cost):
        return pyro_ab.fuel_ok(fsm.body, cost)

    def next_round():
        romp.phase = "walk"
        romp.settle = 0
        romp.air = 0
        romp.launch_t = 0
        romp.fired = False
        romp.airborne = False
        romp.x = pick_open_x(fsm)
        fsm.body.walk_to(romp.x)

    def enter():
        fsm.body.set_posture(True)
        fsm._clear_hands()
        romp.jumps = 0
        romp.dirty = True
        next_round()

    def pick_variant():
        if fsm.rng.random() < 0.5:
            return "vert"
        return "diag+" if fsm.body.chunk0.x < fsm.WL * 0.5 else "diag-"

    def finish(b):
        brk()
        fsm.settle()

    def st_pyroromp(cursor, disturbed):
        b = fsm.body
        if fsm.timer > ROMP_TIMEOUT:
            finish(b)
            return
        ph = romp.phase
        if ph == "walk":
            if b.on_floor() and (not b.is_moving()
                                 or abs(b.chunk1.x - romp.x) < ARRIVE_X):
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
    fsm.register_state("PyroRomp", enter=enter, tick=st_pyroromp,
                       brk=brk, kill_break=brk, mood="pyro_romp", tier=T_ACTIVITY,
                       energy=VIGOROUS)

    energy_gate = fsm.traits.play_gate

    def gate(ctx):
        # 燃料够一整轮；泳/零重力退避；体力过门
        return (not ctx.submerged and not getattr(fsm.body, "zerog", False)
                and ctx.energy >= energy_gate
                and pyro_ab.fuel_ok(fsm.body, p.jumps))

    mood_candidate(fsm, "pyro_romp", p, gate)
