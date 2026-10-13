"""爆破（工匠）：空中爆跳 / 招架、燃料计数与过热、水下憋气见底即溺爆。"""
from __future__ import annotations

from ..base import Ability, Param
from . import mechanics
from .reach import PyroJumpReach


class PyroAbility(Ability):
    key = "pyro"
    title = {"zh": "爆破", "en": "Pyro"}
    doc = ("空中爆跳（手动控制可招架）；每跳燃料 +1、随时间回落，过热眩晕、满了自爆；"
           "水下憋气降到 drown_burst_air 即溺爆。AI 只在燃料 ≤ heat_cap 时爆跳，永不自爆。")
    params = {
        "heat_cap": Param(mechanics.WARN_AT, 0, mechanics.CAPACITY - 1,
                          "AI 自主爆跳的燃料上限（默认 = 过热警告线，AI 永不至眩晕 / 自爆）"),
        "drown_burst_air": Param(0.65, 0.0, 0.95,
                                 "水下憋气剩余降到此值即溺爆（也是气量条的死亡下界）"),
    }

    def fuel_ok(self, body, cost=1):
        """AI 发射门：当前燃料 + 本次成本 ≤ heat_cap。"""
        mechanics.ensure(body)
        return body._ctrl_pyro_counter + cost <= self.p.heat_cap

    def attach_body(self, pet, body):
        body.air_death = self.p.drown_burst_air
        body.drown_burst_air = self.p.drown_burst_air
        body.no_dive = True

    def reaches(self, pet):
        return [PyroJumpReach(pet)]

    def mount(self, fsm):
        mechanics.ensure(fsm.body)
        fsm.register_ticker(lambda: mechanics.tick_fuel(fsm.win, fsm.body))
        fsm.drown_burst_fx = lambda: mechanics.pyro_explosion(fsm.win, fsm.body)

    def control(self, pet, body):
        body._ctrl_pyro = mechanics.PyroController(pet)
