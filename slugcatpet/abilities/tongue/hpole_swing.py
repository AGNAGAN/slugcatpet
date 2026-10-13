"""舌头钩着横杆上杆：先吊着荡一会，再收绳到杆下抓住（技能槽 hpole_mount）。"""

from __future__ import annotations

from ...brain.skills.hpole import GIVEUP, GRIP, GRIP_DIST, RUNNING
from .aim import tongue_of

SWAY_TICKS = 55
GRIP_IDEAL = 9.0
REEL_RATE = 2.0
REEL_TIMEOUT = 240


class HPoleSwing:
    def __init__(self, pet):
        self.tongue = tongue_of(pet)
        self.body = pet.body
        self.reeling = False
        self.t = 0

    def anchor_x(self, default):
        """抓杆的横坐标：舌头钉在哪就抓哪。"""
        a = self.tongue.anchor
        return a[0] if a is not None else default

    def update(self, anchor):
        tg = self.tongue
        if not tg.attached:
            return GIVEUP
        self.t += 1
        tg.anchor = anchor
        if not self.reeling:
            if self.t > SWAY_TICKS:
                self.reeling = True
                self.t = 0
            return RUNNING
        tg.set_targets(ideal=GRIP_IDEAL, reel_rate=REEL_RATE)
        if abs(self.body.chunk0.y - anchor[1]) <= GRIP_DIST or self.t > REEL_TIMEOUT:
            return GRIP
        return RUNNING
