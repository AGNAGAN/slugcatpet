"""骨针：尾巴上长出骨针，拔下来连着脐带扔出去，扎中活物进食；没有能吃东西的嘴。"""

from __future__ import annotations

import math
import random
import zlib

from ...accessories.tail_specks import speck_at, tail_shape
from ...core.units import lerp
from ...core.vecmath import _ang_from_up
from ...rendering.primitives import blit
from ..base import MOUTH, Ability
from .cord import Cord

GROW_FAST_TO = 0.11  # 第一段先快速长到这里
GROW_FAST_UNTIL = 0.1
GROW_FAST_RATE = 0.1
GROW_RATE = 0.05
GROW_DONE = 0.95
SHRINK_RATE = 0.05
SHRINK_SNAP = 0.025
JITTER_FROM = 0.6  # 长过这里头开始抖
JITTER_MAX = 2.0
SLOT_ROWS, SLOT_LINES = 4, 2  # 只在前 4 行、前 2 列里挑
SPRITE = "BioSpear"
GROW_LEN = 0.5  # 长满时露出贴图长度的这么多
GROW_COLOR = (255, 255, 255)
SPARKS = 5
DRIPS = 4
MAX_CORDS = 4
SUBMERGED = 0.5  # 浸没过这么多拔不了


def _tail_point(gfx):
    segs = gfx.tail_segs
    return (segs[0].x, segs[0].y) if segs else gfx.tail_root_world()


class NeedlePull:
    """技能槽 grow_weapon：站着从尾巴拔一根骨针到空手里；update() 返回 running / got / fail。"""

    def __init__(self, pet):
        self.pet = pet
        self.ab = pet.abilities["needle"]
        self.ab.pulled = None
        self.ab.failed = False
        self.weapon = None

    def ready(self):
        return self.ab.can_grow(self.pet.body)

    def update(self):
        ab = self.ab
        if ab.pulled is not None:
            self.weapon, ab.pulled = ab.pulled, None
            return "got" if self.pet.body.hand_of(self.weapon) is not None else "fail"
        if ab.failed:
            ab.failed = False
            return "fail"
        if not ab.can_grow(self.pet.body):
            return "fail"
        self.pet.body.stop_walk()
        ab.want = True
        return "running"


class NeedleAbility(Ability):
    key = "needle"
    title = {"zh": "骨针", "en": "Needles"}
    doc = (
        "不能用嘴吃东西。站着不动、有空手时从尾巴上拔骨针。"
        "连着身体扔出的骨针扎中或穿过活物给 1/4 格食物；落地、扎住或被别人拿走就断开，变成普通的矛。"
    )
    removes = (MOUTH,)
    skills = {"grow_weapon": NeedlePull}

    def attach_body(self, pet, body):
        self.pet = pet
        self._rng = random.Random(zlib.crc32(str(pet.id).encode()))
        self.prog = 0.0
        self.want = False
        self.pulled = None
        self.failed = False
        self.cords = []
        self._new_slot()
        body.throw_hooks.append(self._thrown)
        body.pierce_hooks.append(_fed)

    def _new_slot(self):
        r = self._rng
        self.slot = (r.randint(0, SLOT_ROWS - 1), r.randint(0, SLOT_LINES - 1))
        self.style = r.randint(0, 2)

    def can_grow(self, body):
        return (
            not body.dead
            and body.stun <= 0
            and body.free_hand() is not None
            and body.submersion < SUBMERGED
            and not body.swimming
        )

    def draw_layers(self, pet):
        return (("over_tail", lambda gfx, p, atlas, ts: self._draw(gfx, p, atlas, ts)),)

    def pre_step(self, pet):
        b = pet.body
        if getattr(b, "_ctrl_on", False):
            inp = b._ctrl_input
            if inp:
                i0 = inp[0]
                if i0.pckp and i0.x == 0 and i0.y == 0 and not i0.jmp and not i0.thrw:
                    self.want = True
        want, self.want = self.want and self.can_grow(b), False
        p = self.prog
        if not want:
            p = lerp(p, 0.0, SHRINK_RATE)
            self.prog = 0.0 if p < SHRINK_SNAP else p
            return
        p = lerp(p, GROW_FAST_TO, GROW_FAST_RATE) if p < GROW_FAST_UNTIL else lerp(p, 1.0, GROW_RATE)
        if p > JITTER_FROM:
            k = (p - JITTER_FROM) / (1.0 - JITTER_FROM) * JITTER_MAX * self._rng.random()
            a = self._rng.uniform(0.0, math.tau)
            b.chunk0.x += math.cos(a) * k
            b.chunk0.y += math.sin(a) * k
        if p > GROW_DONE:
            self._pull(pet)
            return
        self.prog = p

    def _pull(self, pet):
        """长满：尾巴中段溅出火花和水滴，骨针放进空手（没空手就掉下）。"""
        b, win, r = pet.body, pet.window, self._rng
        segs = pet.gfx.tail_segs
        mx, my = (segs[len(segs) // 2].x, segs[len(segs) // 2].y) if segs else _tail_point(pet.gfx)
        for _ in range(SPARKS):
            a = r.uniform(0.0, math.tau)
            v = lerp(2.0, 7.0, r.random())
            win.add_spark(mx, my, math.cos(a) * v, math.sin(a) * v, life=18)
        for _ in range(DRIPS):
            win.add_spark(mx, my, r.uniform(-1.0, 1.0), -r.uniform(0.5, 2.5), life=30)
        c0 = b.chunk0
        obj = win.grow_weapon(b, c0.x, c0.y, self.style)
        self.prog = 0.0
        self._new_slot()
        if obj is None:
            self.failed = True
            return
        side = b.free_hand()
        if side is not None:
            b.grab(obj, side)
            self.pulled = obj
        else:
            self.failed = True

    def _thrown(self, body, obj, throw):
        """连着身体扔出的骨针从尾根牵出脐带。"""
        if getattr(obj, "feeds", None) is not body:
            return
        if len(self.cords) >= MAX_CORDS:
            self.cords.pop(0)
        self.cords.append(Cord(_tail_point(self.pet.gfx), obj, self._rng))

    def post_step(self, pet):
        gfx = pet.gfx
        gfx.tail_grow = (*self.slot, self.prog) if self.prog > 0.0 else None
        if self.cords:
            root = _tail_point(gfx)
            floor = pet.window._HL
            alive = not pet.body.dead
            self.cords = [c for c in self.cords if c.update(root, floor, alive)]

    def release(self, pet):
        self.want = False

    def _draw(self, gfx, p, atlas, ts):
        segs = gfx.tail_segs
        if self.cords and segs:
            s0 = segs[0]
            root = (lerp(s0.lx, s0.x, ts), lerp(s0.ly, s0.y, ts))
            for c in self.cords:
                c.draw(p, root, ts)
        if self.prog <= 0.0:
            return
        pts, rads = tail_shape(gfx, ts)
        if pts is None:
            return
        x, y, nx, ny, _, _ = speck_at(pts, rads, *self.slot)
        rot = _ang_from_up(nx, ny)
        blit(p, atlas, f"{SPRITE}{self.style + 1}", x, y, rot, 1.0, self.prog * GROW_LEN, GROW_COLOR, ay=1.0)


def _fed(body, weapon, target, alive):
    """连着自己的骨针扎中活物时进食，给几个 1/4 格由目标的 needle_quarters 定，默认 1；目标有 drained() 时告诉它被吸过了。"""
    if alive and getattr(weapon, "feeds", None) is body:
        body.feed(getattr(target, "needle_quarters", 1))
        drained = getattr(target, "drained", None)
        if drained is not None:
            drained()
