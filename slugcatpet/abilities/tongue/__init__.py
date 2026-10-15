"""舌头：射出粘住墙 / 天花板 / 果子 / 横杆，收绳拉近或吊挂。"""

from __future__ import annotations

from ..base import Ability, Param
from .aim import tongue_of
from .ceiling_reach import CeilingDropReach
from .climb_reach import ClimbReach
from .control import TongueControl
from .draw import TongueRope, draw_tongue
from .hang_stay import TongueHangStay
from .hpole_swing import HPoleSwing
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
    doc = "射舌粘住东西收绳。规划器多出舌够、舌爬墙、竖杆舌钩、舌吊驻留、吊顶落下几种够取，取果时可在空中抢射补救。"
    params = {
        "ceiling_drop": Param(True, doc="规划器可用爬上天花板、横移后松舌落下的够取，代价最高，作兜底"),
    }
    skills = {"fetch_assist": TongueSnatch, "hpole_mount": HPoleSwing}

    def build(self, pet):
        mx, my = pet.gfx.mouth_world()
        t = Tongue(mx, my, POINTS, _taper(POINTS, ROOT_W, TIP_W))
        t.floor_y = pet.window._HL
        t.body = pet.body  # 失重吐舌时推动身体用
        self.rope = TongueRope()
        return t

    def draw_layers(self, pet):
        rope = self.rope
        return (("over_face", lambda gfx, p, atlas, ts: draw_tongue(tongue_of(pet), rope, p, gfx)),)

    def pre_step(self, pet):
        b, t = pet.body, tongue_of(pet)
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
        if pet.controlled and b.stun > 0 and t.attached:
            t.retract()  # 操控中晕了就松舌

    def control(self, pet, body):
        body._ctrl_tongue = TongueControl(pet)

    def post_step(self, pet):
        self.rope.update(tongue_of(pet))

    def resize(self, pet, floor_y):
        tongue_of(pet).floor_y = floor_y

    def reaches(self, pet):
        out = [TongueReach(pet), ClimbReach(pet), PoleTongueReach(pet), TongueHangStay(pet)]
        if self.p.ceiling_drop:
            out.append(CeilingDropReach(pet))
        return out

    def release(self, pet):
        t = tongue_of(pet)
        t.retract()
        t.reset_config()
