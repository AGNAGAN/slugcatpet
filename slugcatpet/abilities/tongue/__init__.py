"""舌头：射出粘住墙 / 天花板 / 果子 / 横杆，收绳拉近或吊挂。"""
from __future__ import annotations

import math

from ...core.units import clampf
from ..base import Ability, Param
from .ceiling_reach import CeilingDropReach
from .climb_reach import ClimbReach
from .draw import TongueRope, draw_tongue
from .hang_stay import TongueHangStay
from .organ import Tongue
from .pole_reach import PoleTongueReach
from .reach import TongueReach
from .snatch import TongueSnatch

POINTS = 20
ROOT_W = 1.8
TIP_W = 0.3


def _taper(n, root_w, tip_w):
    return [root_w + (tip_w - root_w) * (i / (n - 1)) for i in range(n)]


class TongueAbility(Ability):
    key = "tongue"
    title = {"zh": "舌头", "en": "Tongue"}
    doc = "射舌粘物收绳；规划器多出舌够 / 舌爬 / 竖杆舌钩 / 舌吊驻留 / 吊顶落体，取果可空中抢射补救。"
    params = {
        "ceiling_drop": Param(True, doc="规划器可用「爬上天花板横移再松舌落下」（最贵的兜底够取方式）"),
    }

    def build(self, pet):
        mx, my = pet.gfx.mouth_world()
        t = Tongue(mx, my, POINTS, _taper(POINTS, ROOT_W, TIP_W))
        t.floor_y = pet.window._HL
        t.body = pet.body                   # 供零重力吐舌自推进
        self.rope = TongueRope()
        return t

    def draw_layers(self, pet):
        rope = self.rope
        return (("over_face", lambda gfx, p, atlas, ts: draw_tongue(pet.tongue, rope, p)),)

    def pre_step(self, pet):
        b, t = pet.body, pet.tongue
        mox, moy = pet.gfx.mouth_world()
        if b.swimming:
            t.retract()
            t.update(mox, moy, b.chunk0)
            b.suspended = False
        else:
            t.update(mox, moy, b.chunk0)
            # 尸体不被舌头吊住
            b.suspended = t.attached and not b.dead and not b.swimming
        t.room_gravity = pet.window.room_gravity

    def post_step(self, pet):
        self.rope.update(pet.tongue)

    def resize(self, pet, floor_y):
        pet.tongue.floor_y = floor_y

    def reaches(self, pet):
        out = [TongueReach(pet), ClimbReach(pet), PoleTongueReach(pet), TongueHangStay(pet)]
        if self.p.ceiling_drop:
            out.append(CeilingDropReach(pet))
        return out

    def fetch_assist(self, pet):
        return TongueSnatch(pet)

    def fire(self, pet, tx, ty):
        t = pet.tongue
        if t.is_idle():
            hx, hy, hit = _ray_hit_edge(pet, t, pet.body.chunk0.x, pet.body.chunk0.y, tx, ty)
            mox, moy = pet.gfx.mouth_world()
            t.shoot(mox, moy, hx, hy, hit)
        else:
            t.retract()

    def fire_at(self, pet, px, py, obj=None) -> bool:
        mox, moy = pet.gfx.mouth_world()
        return pet.tongue.shoot(mox, moy, px, py, hit=True, obj=obj)


def _ray_hit_edge(pet, tongue, mx, my, cx, cy):
    WL, H = pet.window._WL, pet.window._HL
    dx, dy = cx - mx, cy - my
    d0 = math.hypot(dx, dy)
    ux, uy = (0.0, -1.0) if d0 < 1e-6 else (dx / d0, dy / d0)
    eps = 1e-6
    best = None
    if uy < -eps:
        t = (0.0 - my) / uy
        if t > 0 and 0 <= mx + ux * t <= WL:
            best = t
    if ux < -eps:
        t = (0.0 - mx) / ux
        if t > 0 and 0 <= my + uy * t <= H and (best is None or t < best):
            best = t
    if ux > eps:
        t = (WL - mx) / ux
        if t > 0 and 0 <= my + uy * t <= H and (best is None or t < best):
            best = t
    if best is not None and best <= tongue.total:
        return mx + ux * best, my + uy * best, True
    ex = clampf(mx + ux * tongue.total, 0.0, WL)
    ey = clampf(my + uy * tongue.total, 0.0, H)
    return ex, ey, False
