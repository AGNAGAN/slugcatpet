"""单只宠物实例。"""
from __future__ import annotations
import math
import random

from .abilities import instantiate as build_abilities
from .appearance import Look
from . import tuning
from .characters import get as get_cat_def
from .characters.personality import Traits
from .control.vmath import dirvec
from .core.creature import SlugcatBody
from .rendering.graphics import SlugcatGraphics
from .rendering.layout import Layout
from .core.tail import Tail
from .core.units import clampf, inv_lerp, lerp, K_VEL
from .items.base import WARM

TAIL_SNAP = 40.0

ZEROG_ROOM_GRAVITY = 0.5     # 判为零重力的阈值
ZEROG_TAIL_RATE = 0.08
ZEROG_TAIL_AMP0 = 0.4
ZEROG_TAIL_AMP1 = 0.16


class PetUnit:
    def __init__(self, window, index: int, pet_id: str, variant: str, init_state: dict,
                 spawn_x: float | None = None, look: Look | None = None, name: str = ""):
        self.window = window
        self.index = index
        self.id = pet_id
        self.variant = variant
        self.cat = get_cat_def(variant)
        self.traits = Traits(self.cat.personality)
        self.abilities = build_abilities(self.cat)   # key → Ability
        self.organs = {}                    # 能力建的器官（key → 器官对象）
        self.look = look or Look()
        self.name = name                    # 用户起的名字，空=用猫种名
        self.hidden = False                 # 收起：不在场景里，但保留状态
        self._reincarnate_pending = False
        self._cramp_delay = -1                              # <0 才可再抽
        self._cold_rng = random.Random(0xC01D + index)
        self._kill_dialog = None
        self._kill_cancel_by_self = False
        self._kill_dismiss_silent = False   # 静默消解，跳过扣好感
        self.controlled = False
        self.behavior = None
        self._build(init_state, spawn_x)
        self._attach_behavior()

    def __getattr__(self, name):
        """无此属性则转发到 window。"""
        if name == "window":
            raise AttributeError(name)
        return getattr(self.window, name)

    def _build(self, init_state: dict, spawn_x: float | None = None):
        w = self.window
        self.layout_data = Layout.for_cat(self.cat)
        cx = spawn_x if spawn_x is not None else w._WL / 2.0
        floor_y = w._HL
        self.body = SlugcatBody((cx, floor_y), w._WL, floor_y,
                                energy=init_state.get("energy", 1.0),
                                temper=init_state.get("temper", 0.0),
                                food=init_state.get("food"),
                                karma=init_state.get("karma"),
                                stats=self.cat.stats)
        for ab in self.abilities.values():
            ab.attach_body(self, self.body)
        self.body.cold = float(init_state.get("cold", 0.0))
        self.body.visual_floor_y = floor_y
        from .core import chunkphys as _cp
        _hips_half_w = w.atlas.source_size("base", "HipsA")[0] / 2.0
        _crawl_draw_raise = 4.0
        self.body.crawl_sink = _cp.RAD1 - _hips_half_w + _crawl_draw_raise
        margin = self.layout_data.canvas_w / 2.0
        self.body.walk_min = margin
        self.body.walk_max = w._WL - margin
        self.atlas = self._make_atlas()
        self.gfx = SlugcatGraphics(self.body, self.layout_data, self.atlas, cat=self.cat,
                                   look=self.look)
        for _ in range(40):
            self.body.step()
            self.gfx.update()
        ax, ay = self.gfx.tail_root_world()
        self.tail = Tail(ax, ay, self._tail_rads())
        self.tail.floor_y = floor_y
        self._prev_root = (ax, ay)
        self.gfx.tail_segs = self.tail.segs
        self.organs = {}
        for ab in self.abilities.values():
            organ = ab.build(self)
            if organ is not None:
                self.organs[ab.key] = organ
            for slot, fn in ab.draw_layers(self):
                self.gfx.add_layer(slot, fn)
        self._build_accessories()
        self.body.impact_cb = w._shake_impact
        self.body.on_hurt = self._on_hurt
        self._zerog_tail_phase = 0.0

    def _build_accessories(self):
        from .accessories import BUILTIN
        self.accessories = {cls.key: cls(self) for cls in BUILTIN
                            if self.look.wears(cls, self.cat.key)}
        for acc in self.accessories.values():
            acc.color = self.look.acc_color(acc.key)
        layers = self.gfx.acc_layers
        for slot in layers:
            layers[slot].clear()
        for acc in self.accessories.values():
            for slot, fn in acc.draw_layers(self):
                layers[slot].append(fn)

    def _on_hurt(self, kind, ticks):
        """撞击伤害交给行为层；舌头挂着时不算。"""
        tg = self.tongue
        if self.behavior is None or (tg is not None and tg.attached):
            return
        if kind == "die":
            self.behavior.kill()
        else:
            self.behavior.apply_stun(ticks)

    @property
    def tongue(self):
        return self.organs.get("tongue")

    @property
    def skin_id(self) -> str | None:
        return self.look.skin

    def _make_atlas(self):
        """皮肤 → 原版。"""
        from . import skins
        return skins.resolver_for(self.window.atlas, self.skin_id, self.cat.key)

    def set_skin(self, skin_id: str | None):
        self.look.skin = skin_id or None
        self.refresh_skin()

    def set_look(self, look: Look):
        self.look = look
        self.gfx.look = look
        self._build_accessories()
        self.refresh_skin()

    def look_state(self) -> dict:
        """存档用：改过外观才有 look 字段。"""
        s = self.look.to_state()
        return {"look": s} if s else {}

    def refresh_skin(self):
        self.atlas = self._make_atlas()
        self.gfx.apply_skin(self.atlas)
        if len(self.gfx._tail_rad) != len(self.tail.segs):
            old = self.tail
            self.tail = Tail(old.segs[0].x, old.segs[0].y, self._tail_rads())
            self.tail.adopt(old)
            self.gfx.tail_segs = self.tail.segs
        w = self.window
        w._shown = None
        w.update()

    def _tail_rads(self):
        """皮肤改了尾巴段数时，物理段也按 DMS 半径建；4 段沿用游戏默认。"""
        rads = self.gfx._tail_rad
        return rads if len(rads) != 4 else None

    def _attach_behavior(self):
        try:
            from .brain.fsm import BehaviorFSM
        except Exception:
            self.behavior = None
            return
        seed = getattr(self.window, "_seed", None)      # 测试/复现用；None=随机
        self.behavior = BehaviorFSM(self, seed=None if seed is None else seed * 1009 + self.index)

    def respawn(self, preserve=False):
        """重置本猫（preserve=True 保留体征）。"""
        if self.controlled:              # 先退控制，防丢 provider
            from .control.session import exit_control
            exit_control(self)
        self.dismiss_kill_dialog()
        w = self.window
        if preserve:
            b = self.body
            init_state = {"energy": b.energy, "temper": b.temper,
                          "food": b.food, "karma": b.karma}
        else:
            init_state = {"energy": 1.0, "temper": 0.0,
                          "food": tuning.FOOD_INIT, "karma": tuning.KARMA_INIT}
        self._build(init_state)
        self._attach_behavior()
        w._shown = None
        w.update()

    def _kill_cancel_button(self):
        box = self._kill_dialog
        return None if box is None else getattr(box, "cancel_btn", None)

    def kill_cancel_target(self):
        """取消按钮中心的世界坐标，缺失返回 None。"""
        btn = self._kill_cancel_button()
        if btn is None:
            return None
        w = self.window
        try:
            g = btn.mapToGlobal(btn.rect().center())
            local = w.mapFromGlobal(g)
            return w.to_logical(local.x(), local.y())
        except Exception:
            return None

    def click_kill_cancel(self):
        btn = self._kill_cancel_button()
        if btn is not None:
            self._kill_cancel_by_self = True
            btn.click()

    def dismiss_kill_dialog(self):
        box = self._kill_dialog
        if box is not None:
            self._kill_dismiss_silent = True
            box.reject()          # 触发 finished 回调

    def step(self, cursor, cycle_prog):
        if self.controlled and self.body.dead:
            # 死须先退控制再转世
            from .control.session import exit_control
            exit_control(self)
        if self._reincarnate_pending:
            self._reincarnate_pending = False
            self.respawn(preserve=True)
            return
        w = self.window
        b, g = self.body, self.gfx
        if self.controlled:
            # FSM 冻结期同步晕态
            g.stunned = b.stun > 0
            g.look_at = None
        elif self.behavior is not None:
            self.behavior.update(cursor)
        elif w.follow_cursor:
            g.look_at = cursor

        b.suspended = False                 # 舌头能力会按吊挂状态改写
        for ab in self.abilities.values():
            ab.pre_step(self)

        # water_surface 由 window 每 tick 注入
        rg = w.room_gravity
        b.room_gravity = rg
        b.zerog = rg < ZEROG_ROOM_GRAVITY
        self._feed_swim_neighbors()

        b.step()
        self._cold_update(cycle_prog)
        g.update()
        for ab in self.abilities.values():
            ab.post_step(self)
        for acc in self.accessories.values():
            acc.post_step(self)
        self._tick_tail()

    def _feed_swim_neighbors(self):
        b = self.body
        sp = b.swim_pass
        sp.rank = self.index
        if not b.swimming:
            sp.reset()
            return
        r = tuning.SWIM_AVOID_TRIGGER_DIST
        sp.neighbors = [o.body.swim_pass.as_neighbor() for o in self.window.pets
                        if o is not self and o.body.swimming and not o.body.dead
                        and abs(o.body.chunk0.x - b.chunk0.x) <= r
                        and abs(o.body.chunk0.y - b.chunk0.y) <= r]

    def resize(self, floor_y):
        self.tail.floor_y = floor_y
        for ab in self.abilities.values():
            ab.resize(self, floor_y)

    def _cold_update(self, cycle_prog):
        w = self.window
        b = self.body

        if b.dead:
            b.cold_gain = 0.0
            return

        blizzard_active = w.blizzard_on and cycle_prog > 0.0
        exposure = tuning.COLD_EXPOSURE

        cold_gain = 0.0
        src = next(iter(w.items_affording(WARM)), None)
        in_warm_zone = False
        d_hip = 0.0
        if src is not None:
            d_hip = src.dist_to(b.chunk1.x, b.chunk1.y)
            in_warm_zone = src.in_warm_zone(b.chunk1.x, b.chunk1.y)

        if blizzard_active and not in_warm_zone:
            cg = lerp(0.0, 0.00005, inv_lerp(0.1, 0.95, cycle_prog))
            cg += lerp(0.0, 0.0016, cycle_prog)
            g_div = lerp(9100.0, 5350.0, cycle_prog)
            cg += exposure / g_div
            cg += exposure / 8200.0
            cg = lerp(0.0, cg, inv_lerp(-0.5, 1.0, cycle_prog))
            cg *= inv_lerp(50.0, -10.0, b.total_mass)
            if b.cold > 0.8:
                cg *= 0.5
            cg *= self.traits.cold_gain    # 低=更耐寒
            cg = clampf(cg, -1.0, tuning.COLD_GAIN_CLAMP_HI)             # 勿改
            cold_gain = cg
            b.cold += cg
            conscious = b.stun < 10 and not b.dead
            if b.cold >= 0.8 and conscious:
                if cg > tuning.COLD_CRAMP_GAIN_GATE:                     # 勿改
                    if self._cramp_delay < 0:
                        st = int(lerp(5.0, 60.0, b.cold ** 8))
                        self._cramp_delay = int(self._cold_rng.uniform(
                            300 - b.cold * 240, 500 - b.cold * 200))
                        b.stun = max(b.stun, st)
                else:
                    self._cramp_delay = self._cold_rng.randint(200, 499)
            self._cramp_delay -= 1
            if b.cold >= 1.0 and b.stun > tuning.COLD_DEATH_STUN and not b.dead:
                if self.behavior is not None and hasattr(self.behavior, "kill_cold"):
                    self.behavior.kill_cold()
        else:
            if in_warm_zone and b.cold > 0.001:
                f = inv_lerp(src.warm_radius, src.warm_inner, d_hip)
                b.cold = max(b.cold - tuning.COLD_LAMP_WARMTH * f, 0.0)
            if b.cold > 1.0:
                b.cold = 1.0
            b.cold = lerp(b.cold, 0.0, tuning.COLD_NATURAL_DECAY)
        b.cold_gain = cold_gain
        b.clamp_cold()

    def _tick_tail(self):
        """尾巴跟随，顺序固定。"""
        b, g = self.body, self.gfx
        rx, ry = g.draw1[0], g.draw1[1]
        if math.hypot(rx - self._prev_root[0], ry - self._prev_root[1]) > TAIL_SNAP:
            self.tail.snap_to(rx, ry)
        # 松弛度：1=下垂摆动，0=贴流线
        if b.chunk0.pinned or b.chunk1.pinned or b.suspended or b.hover:
            looseness = 1.0
        elif b.bodyMode == "Stand":
            vx_norm = abs(b.chunk1.vx) / K_VEL
            looseness = 1.0 - clampf((vx_norm - 1.0) * 0.5, 0.0, 1.0)
        elif b.bodyMode == "Crawl":
            looseness = 1.0
        elif b.bodyMode == "ClimbingOnBeam":
            looseness = 1.0   # 漏此分支尾巴发僵
        elif b.bodyMode == "ZeroG":
            looseness = 1.0   # 漏此分支尾巴发僵
        else:
            looseness = 0.0   # 空中无动画
        ref_x, ref_y = b.chunk0.x, b.chunk0.y
        if (b.bodyMode == "Stand"
                and abs(b.chunk0.vx) / K_VEL > 2.0 and abs(b.chunk1.vx) / K_VEL > 2.0):
            ref_x = b.chunk1.x + b.facing * 16.0 * clampf(abs(b.chunk1.vx) / K_VEL - 0.2, 0.0, 1.0)
            ref_y = b.chunk1.y + 4.0
        self.tail.step(rx, ry, b.chunk1.x, b.chunk1.y, ref_x, ref_y, looseness,
                       gravity_norm=self.window.room_gravity)   # 零重力不朝世界下耷拉
        if b.bodyMode == "ZeroG":
            self._apply_zerog_tail_sway(b)
        g._apply_sleep_tail_curl()   # 须在 tail.step 之后
        self._prev_root = (rx, ry)
        if b.animation in ("Roll", "Flip"):
            vx, vy = dirvec(b.chunk0.x, b.chunk0.y, b.chunk1.x, b.chunk1.y)
            f = 6.0
            for seg in self.tail.segs:
                seg.vx += vx * f
                seg.vy += vy * f
                f /= 1.7

    def _apply_zerog_tail_sway(self, b):
        self._zerog_tail_phase += ZEROG_TAIL_RATE
        ax, ay = b.chunk0.x - b.chunk1.x, b.chunk0.y - b.chunk1.y   # 体轴
        d = math.hypot(ax, ay) or 1.0
        px, py = -ay / d, ax / d                                    # 垂体轴单位向量
        s = math.sin(self._zerog_tail_phase)
        segs = self.tail.segs
        segs[0].vx += px * ZEROG_TAIL_AMP0 * s
        segs[0].vy += py * ZEROG_TAIL_AMP0 * s
        if len(segs) > 1:
            segs[1].vx += px * ZEROG_TAIL_AMP1 * s
            segs[1].vy += py * ZEROG_TAIL_AMP1 * s

    def fire_tongue(self, tx, ty):
        ab = self.abilities.get("tongue")
        if ab is not None:
            ab.fire(self, tx, ty)

    def fire_tongue_at(self, px, py) -> bool:
        """直接朝世界点钉舌，返回是否射出。"""
        ab = self.abilities.get("tongue")
        return ab is not None and ab.fire_at(self, px, py)

    def fire_tongue_at_obj(self, fruit) -> bool:
        """射舌粘住果子，返回是否射出。"""
        ab = self.abilities.get("tongue")
        return ab is not None and ab.fire_at(self, fruit.x, fruit.y, obj=fruit)
