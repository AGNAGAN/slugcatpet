"""配件（Accessory）基类：纯外观、会动的额外部件。"""
from __future__ import annotations


class Accessory:
    key = ""
    title = {"zh": "", "en": ""}
    default_color = (255, 255, 255)
    default_on = ()
    color_group = None

    def __init__(self, pet):
        self.pet = pet
        self.color = None

    def post_step(self, pet):
        """图形姿态更新之后。"""

    def draw_layers(self, pet):
        """[(槽位, fn(gfx, painter, atlas, ts))]；槽位见 SlugcatGraphics.LAYER_SLOTS。"""
        return ()
