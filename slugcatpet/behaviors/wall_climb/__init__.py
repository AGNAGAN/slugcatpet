"""爬墙链 RelocateToWall → TongueClimb → CeilingHang。"""

from __future__ import annotations

from types import SimpleNamespace

from ...abilities.base import Param
from ...abilities.tongue.climb import CeilingHanger, TongueClimber, hang_above_water
from ...brain.desire import _lerp
from ...brain.state import LIGHT, T_ACTIVITY, VIGOROUS
from ..base import Behavior, mood_candidate, mood_params


class WallClimb(Behavior):
    key = "wall_climb"
    mood = "ceiling_play"
    title = {"zh": "爬墙 / 天花板玩耍", "en": "Wall climb"}
    doc = "走到墙脚用舌头爬上天花板吊着晃，玩腻了松手落下。"
    requires = ("tongue",)
    params = mood_params(
        1.00,
        0.75,
        0.30,
        0.10,
        0.0018,
        0.00038,
        energy_fac_fresh=Param(1.30, 0.0, 10.0, "体力满时的权重系数"),
        energy_fac_tired=Param(0.15, 0.0, 10.0, "体力空时的权重系数"),
    )

    def mount(self, fsm):
        _mount(fsm, self.p)


def _mount(fsm, p):
    relocate = SimpleNamespace()

    def relocate_enter():
        fsm.body.set_posture(True)
        relocate.x = None

    def st_relocatetowall(cursor, disturbed):
        b = fsm.body
        side = getattr(fsm, "_wall_side", -1)
        target = b.walk_max if side > 0 else b.walk_min
        if relocate.x is None:
            relocate.x = target
            b.walk_to(target)
        if not b.is_moving() or abs(b.chunk1.x - target) < 6.0:
            b.stop_walk()
            fsm._transition("TongueClimb")

    def climb_enter():
        fsm.climb = TongueClimber(fsm.win, getattr(fsm, "_wall_side", -1), rng=fsm.rng)

    def st_tongueclimb(cursor, disturbed):
        if fsm.climb is None:
            fsm._transition("CeilingHang")
            return
        done = fsm.climb.update()
        if fsm.climb.giveup:
            fsm._break_tongue()
            fsm._transition("IdleStand")
        elif done:
            fsm._transition("CeilingHang")

    def hang_enter():
        fsm.climb = CeilingHanger(fsm.win, getattr(fsm, "_wall_side", -1), fsm.rng)

    def st_ceilinghang(cursor, disturbed):
        done = fsm.climb.update() if fsm.climb else True
        if done or fsm.mood.should_quit("ceiling_play"):
            fsm._break_tongue()
            fsm.climb = None
            fsm._transition("Airborne")

    def brk():
        fsm._break_tongue()
        fsm.body.stop_walk()
        fsm.climb = None

    def kill_brk():
        fsm._break_tongue()
        fsm.climb = None

    fsm.register_state(
        "RelocateToWall", enter=relocate_enter, tick=st_relocatetowall, tier=T_ACTIVITY, energy=LIGHT
    )
    fsm.register_state(
        "TongueClimb",
        enter=climb_enter,
        tick=st_tongueclimb,
        brk=brk,
        kill_break=kill_brk,
        tier=T_ACTIVITY,
        energy=VIGOROUS,
    )
    fsm.register_state(
        "CeilingHang",
        enter=hang_enter,
        tick=st_ceilinghang,
        brk=brk,
        kill_break=kill_brk,
        tier=T_ACTIVITY,
        energy=VIGOROUS,
        mood="ceiling_play",
        mood_entry=False,
    )

    def face_nearer_wall():
        fsm._wall_side = -1 if fsm.body.chunk1.x < fsm.WL / 2 else 1

    fsm.register_mood_entry("ceiling_play", "RelocateToWall", before=face_nearer_wall)
    gate = fsm.traits.play_gate
    mood_candidate(
        fsm,
        "ceiling_play",
        p,
        gate=lambda ctx: ctx.energy >= gate and not ctx.submerged and hang_above_water(fsm.win),
        one_shot=False,
        energy_factor=lambda e: _lerp(e, 0.0, 1.0, p.energy_fac_tired, p.energy_fac_fresh),
        before="idle",
    )
