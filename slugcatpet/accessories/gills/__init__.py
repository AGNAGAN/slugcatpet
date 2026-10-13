"""鳃：头侧鳞片随视线扇动。"""

from __future__ import annotations

from ...core.units import K_VEL
from ..base import Accessory
from .draw import EFFECT, draw_gills
from .organ import Gills

FLAT_RATE = 0.08 * K_VEL  # 趴 / 睡时鳃锚退回世界水平的速度


class GillsAccessory(Accessory):
    key = "gills"
    title = {"zh": "鳃", "en": "Gills"}
    default_color = EFFECT
    default_on = ("rivulet",)

    def __init__(self, pet):
        super().__init__(pet)
        b = pet.body
        gh = pet.window.atlas.source_size("base", "LizardScaleA3")[1]
        self.organ = Gills(b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y, gh)

    def draw_layers(self, pet):
        g = self.organ
        return (("under_face", lambda gfx, p, atlas, ts: draw_gills(gfx, g, p, atlas, ts, self)),)

    def post_step(self, pet):
        b, gfx, g = pet.body, pet.gfx, self.organ
        flat = 1.0 if (gfx.sleeping or b.bodyMode == "Crawl") else 0.0
        if g.flat < flat:
            g.flat = min(flat, g.flat + FLAT_RATE)
        elif g.flat > flat:
            g.flat = max(flat, g.flat - FLAT_RATE)
        g.update(
            b.chunk0.x,
            b.chunk0.y,
            b.chunk1.x,
            b.chunk1.y,
            gfx.look_dir[0],
            gfx.look_dir[1],
            submerged=b.head_sub > 0.5,
            flat_anchor=g.flat,
        )
