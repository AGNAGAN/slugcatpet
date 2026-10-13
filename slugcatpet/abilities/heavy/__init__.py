"""重压（饕餮）：会累倒、滑铲与翻滚强劲、落地震动、砸晕别的猫和砸死蝙蝠、扔矛用尽全力。"""

from __future__ import annotations

import math

from ..base import Ability, Param
from .impact import HeavyImpact

SPEAR_DAMAGE = 3.0  # 没累倒时扔出的矛的伤害
SPEAR_DAMAGE_TIRED = 0.3  # 累倒时扔出的矛的伤害
SPEAR_LUNGE = 9.0  # 扔矛时身体顺着矛冲出的速度


class HeavyAbility(Ability):
    key = "heavy"
    title = {"zh": "重压", "en": "Heavy"}
    doc = (
        "气喘到 exhaust_enter 累倒，降到 exhaust_exit 缓过来；累倒时跑、爬变慢，喘气闭眼，"
        "滑铲变弱、翻滚恢复普通限制、扔东西无力。没累倒时翻滚不自然停。"
        "从高处落下震动窗口；砸、滚、滑撞到别的猫会让它晕（不算到人头上：不扣好感、醒来不生气），撞到蝙蝠会砸死。"
        "扔矛一下就气喘到顶：没累倒时矛伤害极高、身体顺势冲出（手操时在地上翻滚、空中空翻），累倒时扔出的矛几乎没伤害。"
        "滑铲速度、跳跃耗气、摔晕阈值等另见数值。"
    )
    params = {
        "exhaust_enter": Param(0.95, 0.0, 1.0, "气喘达到此值累倒"),
        "exhaust_exit": Param(0.4, 0.0, 1.0, "累倒后气喘降到此值以下缓过来"),
        "land_shake": Param(1.0, 0.0, 5.0, "落地震动倍率，0=不震"),
        "land_shake_speed": Param(8.0, 0.0, 60.0, "落地速度达到此值才震"),
        "slam": Param(True, doc="砸、滚、滑撞到别的猫时让它晕"),
    }

    def attach_body(self, pet, body):
        body.endless_roll = True
        body.throw_hooks.append(_spear_thrown)

    def build(self, pet):
        return HeavyImpact(self.p)

    def pre_step(self, pet):
        b = pet.body
        a = b.aerobic
        if a >= self.p.exhaust_enter:
            b.exhausted = True
        elif a < self.p.exhaust_exit:
            b.exhausted = False
        if b.exhausted:
            b.lungs_exhausted = True  # 累倒时肺也算透支
        pet.organs[self.key].pre_step(pet)

    def post_step(self, pet):
        pet.organs[self.key].post_step(pet)


def _spear_thrown(body, obj, throw):
    """扔出扎得进的武器：气喘到顶；没累倒时伤害极高、身体顺着矛冲出，累倒时几乎没伤害。"""
    if not getattr(obj, "pierces", False):
        return
    tired = body.exhausted
    body.aerobic = 1.0
    if tired:
        obj.damage = SPEAR_DAMAGE_TIRED
        return
    obj.damage = SPEAR_DAMAGE
    c0 = body.chunk0
    if body.room_gravity == 0.0 or abs(obj.vx) < 1.0:
        sp = math.hypot(obj.vx, obj.vy)
        if sp > 1e-6:
            c0.vx += obj.vx / sp * SPEAR_LUNGE
            c0.vy += obj.vy / sp * SPEAR_LUNGE
        return
    d = 1 if obj.vx > 0.0 else -1
    c0.vx += d * SPEAR_LUNGE
    if getattr(body, "_ctrl_on", False):
        if body.on_floor():
            body.animation = "Roll"
            body._ctrl_roll_direction = d
            body._ctrl_roll_counter = 0
        else:
            body.animation = "Flip"
