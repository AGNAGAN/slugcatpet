"""面罩疤：贴在脸下、头上的一张图。"""
from __future__ import annotations

import math

from ...appearance import accessory_color
from ...rendering.primitives import blit
from ..base import Accessory

FRAME = "MushroomA"


class ScarAccessory(Accessory):
    key = "scar"
    title = {"zh": "面罩疤", "en": "Scar"}
    default_color = (69, 40, 60)
    default_on = ("artificer",)
    color_group = "FACESCAR"

    def draw_layers(self, pet):
        return (("behind_face", lambda gfx, p, atlas, ts: self._draw(gfx, p, atlas)),)

    def _draw(self, gfx, p, atlas):
        element, fx, fy, rot = gfx.face_pose
        scale_x = 1.0
        if getattr(gfx.body, "animation", None) == "Flip":
            r = math.radians(rot)    # Flip 前移 4，y↓
            x = fx + math.sin(r) * 4.0
            y = fy - math.cos(r) * 4.0
        else:
            digit = len(element) >= 2 and element[-1].isdigit()
            n = int(element[-1]) if digit else 0
            if digit and element[-2] == "C":
                scale_x = 1.0 - n / 8.0
                x = fx + 3.0 + 4.0 * (n / 8.0)
            elif digit and element[-2] == "D":
                x = fx + 3.0 * (1.0 - n / 8.0)
            else:
                x = fx + 3.0
            y = fy - 3.0
        blit(p, atlas, FRAME, x, y, rot, scale_x, 1.0,
             accessory_color(self, gfx._gcol), ax=0.5, ay=0.5)
