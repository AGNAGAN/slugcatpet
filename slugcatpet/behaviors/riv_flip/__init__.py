"""后空翻上横杆：走到杆下起跳点后空翻抓杆，抓住转 HPole。"""

from __future__ import annotations

import math
from types import SimpleNamespace

from ...brain import maneuver
from ...planning.backflip_reach import SETTLE_MAX, SETTLE_VX, TOP_CLEAR, takeoff_c0_h
from ...planning.jump_arc import get_backflip_arc
from ...brain.skills.hpole import GRIP_DIST
from ...items.base import CLIMBABLE
from ...brain.state import T_ACTIVITY, VIGOROUS
from ..base import Behavior, mood_candidate, mood_params

ARRIVE_X = 8.0  # px
LAUNCH_TIMEOUT = 80  # 起跳未腾空兜底 tick
FLIP_TIMEOUT = 1200  # tick
POLE_X_MARGIN = 10.0  # 离杆端余量 px
AIM_BAND = GRIP_DIST - 4.0  # 贴杆瞄准带，留 sim 残差余量


class RivFlip(Behavior):
    key = "riv_flip"
    mood = "riv_flip"
    title = {"zh": "后空翻上横杆", "en": "Backflip to pole"}
    doc = "无聊时找一根够得着的横杆，走到杆下后空翻上去，抓住就转横杆玩耍，抓不上落地收工。"
    requires = ("acrobat",)
    params = mood_params(1.00, 0.72, 0.30, 0.30, 0.0040, 0.00055)

    def mount(self, fsm):
        _mount(fsm, self.p)


def _walk_band(fsm):
    b = fsm.body
    return (0.0 if b.walk_min is None else b.walk_min, fsm.WL if b.walk_max is None else b.walk_max)


def _pole_reachable(fsm):
    stats = fsm.win.cat.stats
    launch_y = fsm.HL - takeoff_c0_h(stats)
    apex = max(get_backflip_arc(stats, 1).apex, get_backflip_arc(stats, -1).apex)
    for pole in fsm.items(CLIMBABLE):
        if getattr(pole, "kind", None) != "horizontal":
            continue
        rise = launch_y - pole.ay
        if 0.0 < rise <= apex + GRIP_DIST:
            return True
    return False


def _pole_plan(fsm):
    """选可达横杆：杆线在起跳 chunk0 上方且 apex+GRIP_DIST 够到 → (pole, d, launch_x)；无 → None。"""
    stats = fsm.win.cat.stats
    launch_y = fsm.HL - takeoff_c0_h(stats)
    b = fsm.body
    xmin, xmax = _walk_band(fsm)
    for pole in fsm.items(CLIMBABLE):
        if getattr(pole, "kind", None) != "horizontal":
            continue
        rise = launch_y - pole.ay
        if rise <= 0.0:
            continue
        lo = min(pole.ax, pole.bx) + POLE_X_MARGIN
        hi = max(pole.ax, pole.bx) - POLE_X_MARGIN
        if hi <= lo:
            continue
        for ax_t in (max(lo, min(hi, b.chunk1.x)), (lo + hi) * 0.5):
            for d in (1, -1) if ax_t >= b.chunk1.x else (-1, 1):
                arc = get_backflip_arc(stats, d)
                if arc.apex + GRIP_DIST < rise:
                    continue
                for px, py in arc.points:
                    if launch_y + py < TOP_CLEAR:  # 越窗顶余量：其后命中被 clamp 失真，弃该弧
                        break
                    if abs(launch_y + py - pole.ay) <= AIM_BAND:
                        lx = ax_t - px
                        if xmin <= lx <= xmax:
                            return (pole, d, lx)
    return None


def _near_pole(b, pole):
    lo = min(pole.ax, pole.bx) + 2.0
    hi = max(pole.ax, pole.bx) - 2.0
    c0 = b.chunk0
    ax = max(lo, min(hi, c0.x))
    return math.hypot(c0.x - ax, c0.y - pole.ay) <= GRIP_DIST


def _mount(fsm, p):
    flip = SimpleNamespace()

    def enter():
        fsm.body.set_posture(True)
        fsm._clear_hands()
        plan = _pole_plan(fsm)
        if plan is None:
            flip.dirty = False
            flip.pole = None
            fsm._transition("IdleStand")
            return
        flip.dirty = True
        flip.pole, flip.d, flip.x = plan
        flip.phase = "walk"
        flip.settle = 0
        flip.launch_t = 0
        flip.airborne = False
        fsm.body.walk_to(flip.x)

    def finish(b):
        brk()
        fsm.settle()

    def st_rivflip(cursor, disturbed):
        b = fsm.body
        if fsm.timer > FLIP_TIMEOUT:
            finish(b)
            return
        pole = flip.pole
        if pole is not None and pole not in fsm.items(CLIMBABLE):  # 杆没了：空中顺势落地，未起跳直接收工
            pole = flip.pole = None
        ph = flip.phase
        if pole is None and ph != "air":
            finish(b)
            return
        if ph == "walk":
            if b.on_floor() and (not b.is_moving() or abs(b.chunk1.x - flip.x) < ARRIVE_X):
                b.stop_walk()
                flip.phase = "settle"
            return
        if ph == "settle":
            b.stop_walk()
            flip.settle += 1
            still = abs(b.chunk0.vx) < SETTLE_VX and abs(b.chunk1.vx) < SETTLE_VX
            if b.on_floor() and (still or flip.settle > SETTLE_MAX):
                b.backflip_launch(flip.d)
                flip.phase = "air"
                flip.launch_t = 0
            return
        if not b.on_floor():
            flip.airborne = True
            b.move_dir = flip.d
            if pole is not None and _near_pole(b, pole):
                b.stop_walk()
                flip.dirty = False  # animation 交 HPole 生命周期接管
                fsm.social.claim(fsm.win, "hpole", pole)
                fsm._transition("HPole")
            return
        if flip.airborne:
            finish(b)
        else:
            flip.launch_t += 1
            if flip.launch_t > LAUNCH_TIMEOUT:
                finish(b)

    def brk():
        d = fsm.body.move_dir
        maneuver.clear_motion(fsm.body, flip)
        maneuver.stand_facing(fsm.body, d)

    fsm.register_ticker(maneuver.leak_watch(fsm, "RivFlip", flip))
    fsm.register_state(
        "RivFlip",
        enter=enter,
        tick=st_rivflip,
        brk=brk,
        kill_break=brk,
        mood="riv_flip",
        tier=T_ACTIVITY,
        energy=VIGOROUS,
    )

    energy_gate = fsm.traits.play_gate

    def gate(ctx):
        return (
            not ctx.submerged
            and not getattr(fsm.body, "zerog", False)
            and ctx.energy >= energy_gate
            and _pole_reachable(fsm)
        )

    mood_candidate(fsm, "riv_flip", p, gate)
