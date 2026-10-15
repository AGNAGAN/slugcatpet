"""蛋虫物理与行为核心：两节身体（头在前），站在地面上时不受重力；闲逛、受惊逃跑、跳开。y↓。"""

from __future__ import annotations

import math
import random as _random

from ...core.chunkphys import BodyChunk, solve_conn
from ...core.units import clampf, inv_lerp, lerp, lerp_tick
from ..base import HIT_SLAM, HIT_SPEAR, HIT_STONE
from ..bugegg.model import BugEgg
from ..state import ItemState
from .gfx import EggBugGfx

HEAD_RAD, REAR_RAD = 5.0, 8.0
MASS = 0.4
CONN = 12.0
GRAVITY = 0.9
AIR_FRICTION = 0.999
TANGENTIAL = 0.8  # 着地时切向速度保留（surfaceFriction 0.4）
WATER_FRICTION, BUOYANCY = 0.96, 0.95
TILE = 20.0
TRACK = 10.0  # 站着时身体中心离地高度
FOOTING_TICKS = 20  # 连续在地面格里这么久才站稳
FOOTING_MAX = 35
FOOT_DAMP = 0.8
RUN_HEAD, RUN_REAR = 6.2, 1.0
RUN_K = 0.85**0.6
AIR_STEER = 0.3
TRACK_PULL_MAX = 1.2
TURN_HEAD, TURN_REAR, TURN_HOP = 1.3, 0.5, 3.2
STEP_AHEAD = TILE  # 往前看一格

JUMP_SPEED, JUMP_RAND, JUMP_SPIN = 17.0, 5.0, 11.0
SWIM_FLOAT = 0.3  # 在水里往上浮的力，浮在水面上
JUMP_COOLDOWN = 90
SHAKE_KICK = 2.0
HELD_KICK = 2.0  # 被拎着时每节乱蹬
HELD_DAMP = 0.8
MEAT = 1  # 尸体能啃几口
EGGS = 6

FLEE_FLAIL = 5.0  # 逃跑中腾空时乱蹬

# 威胁：猫和光标都按 slugcat 的体型算
THREAT_K = 0.68  # severity^1.5 × 10
THREAT_UP, THREAT_DOWN = 0.5, 0.005  # 平滑：上升按比例、下降按定值
FLEE_UTIL = 0.02
SIT_UTIL = 0.5
SHELTER_UTIL = 0.3  # 威胁低于这个时大雨里先去躲雨
NOTICE_R = 1200.0  # 视距：进入这个距离算「看见」
SPOT_JUMP_R = 87.0  # 第一次看见时这么近就跳开
SURPRISE_R = 300.0
WEAPON_WARN_R = 300.0
WEAPON_WARN_ABOVE = 50.0
FLEE_RANGE = 600.0
FLEE_SAMPLES = 10
FLEE_REPICK = 20
CROSS_PENALTY = 10.0
IDLE_MARGIN = 30.0
IDLE_COUNTER = (200, 800)
IDLE_MARGIN_HI, IDLE_MARGIN_LO, IDLE_MARGIN_SPAN = 100.0, -300.0, 300.0  # 换闲逛点的门槛随计数从严变松
ARRIVE = 10.0
RUN_IDLE, RUN_FLEE = 0.5, 1.0

# 受伤（原版模板：伤害抗性 0.15、晕抗性 0.3、即死线 0.7）
DAMAGE_RES, STUN_RES, INSTANT_DEATH = 0.15, 0.3, 0.7
HITS = {HIT_STONE: (0.01, 45.0), HIT_SPEAR: (1.0, 20.0), HIT_SLAM: (0.5, 30.0)}


def threat_at(d):
    """一个威胁在距离 d 处的威胁值（按格数衰减）。"""
    return THREAT_K / max(1.0, (d / TILE) ** 1.25)


class EggBug:
    """两节身体的小活物：怕猫和光标，逃跑时会跳；死了是两节软塌塌的尸体。"""

    collision_layer = 1
    throwable = False
    creature = True
    is_meat = True
    bulky = True
    stops_weapons = True  # 扔中它的武器停在它身上
    needle_quarters = 12  # 被连着的骨针扎中时喂给矛大师的 1/4 格数

    def __init__(self, x: float, y: float, seed: int = 0):
        rng = self._rng = _random.Random(seed * 7919 + 13)
        self._id = int(seed)
        side = 1.0 if rng.random() < 0.5 else -1.0
        self.c0 = BodyChunk(0, x + side * CONN * 0.5, y, HEAD_RAD, MASS / 3.0)
        self.c1 = BodyChunk(1, x - side * CONN * 0.5, y, REAR_RAD, MASS * 2.0 / 3.0)
        self.rad, self.mass = REAR_RAD, MASS
        self.water_y = None
        self.room_gravity = 1.0
        self._impact_cb = None
        self.state = ItemState.FREE
        self.held_by_hand = None
        self.stalk = None
        self.collide_with_objects = True
        self.dead = False
        self.stun = 0
        self.health = 1.0
        self.dissolve = -1
        self.has_eggs = True
        self.meat = MEAT
        self.drop_eggs = True  # 死时爆蛋；被骨针吸食时关掉
        self.burst = False  # 刚死、等着爆蛋
        self.footing = 0
        self.no_jumps = 0
        self.shake = 0
        self.fear = 0.0
        self.threat = 0.0  # 平滑后的威胁效用
        self.panic = 0.0
        self.run_speed = RUN_IDLE
        self.run_cycle = 0.0
        self.mode = "idle"  # idle / flee
        self.sitting = False
        self.dest = None
        self.idle_counter = 0
        self.flee_timer = 0
        self.travel = 0.0  # 行进方向（-1..1）
        self.facing = side
        self.age = 0
        self.jumped = False  # 这一 tick 起跳了
        self._threats = ()
        self._shelter = None
        self._weapons = ()
        self._noticed = set()  # 眼下看得见的威胁
        self._seen = set()  # 见过的威胁，再出现时不算第一次
        self._WL = self._HL = None
        self.gfx = EggBugGfx(self, rng)

    # 对外的位置：腹部那一节；写位置时整个身体平移，写速度时两节一起加

    @property
    def x(self):
        return self.c1.x

    @x.setter
    def x(self, v):
        d = v - self.c1.x
        self.c1.x = v
        self.c0.x += d

    @property
    def y(self):
        return self.c1.y

    @y.setter
    def y(self, v):
        d = v - self.c1.y
        self.c1.y = v
        self.c0.y += d

    @property
    def vx(self):
        return self.c1.vx

    @vx.setter
    def vx(self, v):
        d = v - self.c1.vx
        self.c1.vx = v
        self.c0.vx += d

    @property
    def vy(self):
        return self.c1.vy

    @vy.setter
    def vy(self, v):
        d = v - self.c1.vy
        self.c1.vy = v
        self.c0.vy += d

    @property
    def last_x(self):
        return self.c1.last_x

    @last_x.setter
    def last_x(self, v):
        d = v - self.c1.last_x
        self.c1.last_x = v
        self.c0.last_x += d

    @property
    def last_y(self):
        return self.c1.last_y

    @last_y.setter
    def last_y(self, v):
        d = v - self.c1.last_y
        self.c1.last_y = v
        self.c0.last_y += d

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def chunks(self):
        return (self.c0, self.c1)

    @property
    def conscious(self):
        return not self.dead and self.stun <= 0

    @property
    def huntable(self):
        return self.dissolve < 0

    @property
    def can_jump(self):
        """眼下飞来武器的话来得及跳开。"""
        hl = self._HL
        return (
            self.conscious
            and self.no_jumps <= 0
            and hl is not None
            and (self._on_track(self.c0, hl) or self._on_track(self.c1, hl))
        )

    @property
    def exposed(self):
        """落在地上、一时跳不开：这时扔武器打得中。"""
        hl = self._HL
        return hl is not None and not self.can_jump and self._on_track(self.c1, hl)

    @property
    def carcass(self):
        return self.dead

    @property
    def edible(self):
        return self.dead and self.meat > 0 and self.dissolve < 0

    @property
    def fetch_ready(self):
        return self.dead and self.state == ItemState.FREE and self.held_by_hand is None and self.dissolve < 0

    def set_rotation_to_grabber(self, gx: float, gy: float) -> None:
        """拿在手里时腹部贴着手，头自己垂着（见 _held_step）。"""

    def bleed(self, n):
        self.gfx.bleed(n)

    def loot_quarters(self, traits):
        """打死它能吃到几个 1/4 格：背上的蛋加尸体的肉。"""
        q = traits.meat * self.meat
        if self.has_eggs and self.drop_eggs:
            q += EGGS * traits.nourishment(BugEgg)
        return q

    def collision_chunks(self):
        self.collide_with_objects = self.state == ItemState.FREE and self.dissolve < 0
        for c in (self.c0, self.c1):
            c.collide_with_objects = self.collide_with_objects
        return (self.c0, self.c1)

    def dist_to(self, x, y):
        return min(math.hypot(x - c.x, y - c.y) - c.rad for c in (self.c0, self.c1))

    # 受伤

    def struck(self, how, rng=None) -> None:
        damage, bonus = HITS.get(how, (0.0, 0.0))
        self.violence(damage, bonus)

    def violence(self, damage, stun_bonus) -> None:
        if self.dead:
            return
        rng = self._rng
        dmg = damage / DAMAGE_RES
        st = (damage * 30.0 + stun_bonus) / STUN_RES
        st *= 1.5 + inv_lerp(0.5, 0.0, self.health) * rng.random()
        self.stun = max(self.stun, int(st))
        self.health -= dmg
        if rng.random() < -self.health or self.health < -1.0 or (self.health < 0.0 and rng.random() < 0.33):
            self.die()
        elif dmg >= INSTANT_DEATH:
            self.die()
        if damage > 0.05:
            self.gfx.squirt(inv_lerp(0.2, 1.0, damage))

    def die(self) -> None:
        if self.dead:
            return
        self.dead = True
        self.mode = "idle"
        self.sitting = False
        if self.drop_eggs and self.has_eggs:
            self.burst = True

    def drained(self) -> None:
        """被骨针吸食：蛋连汁一起被吸走，死了也不爆。"""
        self.drop_eggs = False
        self.has_eggs = False

    # 感知：由物品类型每 tick 写入

    def sense(self, threats, weapons, WL, HL, shelter=None):
        """threats: [(key, x, y)]；weapons: [(key, x, y, vx, vy)]；shelter: 大雨时该躲去的地面 x，不用躲为 None。"""
        self._threats = threats
        self._weapons = weapons
        self._shelter = shelter
        self._WL, self._HL = WL, HL

    # 推进

    def step(self, WL: float, HL: float) -> None:
        st = self.state
        if st in (ItemState.EATEN, ItemState.GONE):
            return
        self.age += 1
        self.jumped = False
        c0, c1 = self.c0, self.c1
        if st == ItemState.CARRIED:
            self._held_step()
            return
        self._vitals()
        if self.shake > 0:
            self.shake -= 1
            if not self.dead:
                for c in (c0, c1):
                    if self._on_track(c, HL):
                        self._kick(c, SHAKE_KICK)
        mouse = st == ItemState.MOUSE
        sub = self._submersion(c0)
        rg = self.room_gravity
        if mouse:
            if not self.dead:
                for c in (c0, c1):
                    self._kick(c, HELD_KICK)
            self.footing = 0
            hx, hy = c1.x, c1.y
            c1.pinned = True
            c0.update(WL, HL, GRAVITY, AIR_FRICTION, None, rg, self.water_y, BUOYANCY, WATER_FRICTION)
            c1.update(WL, HL, GRAVITY, AIR_FRICTION, None, rg, self.water_y, BUOYANCY, WATER_FRICTION)
            c1.x, c1.y = hx, hy
            solve_conn(c0, c1, CONN, 0.5)
            c1.pinned = False
            if self.conscious:
                self._perceive(HL)
            self.gfx.update(HL)
            return
        if self.conscious:
            self.footing += 1
            if sub > 0.3:
                self._swim(sub, WL)
            else:
                self._act(WL, HL)
        else:
            self.footing = 0
        footing = self.on_footing
        if footing:
            for c in (c0, c1):
                c.vx *= FOOT_DAMP
                c.vy *= FOOT_DAMP
        elif self.conscious and self.mode == "flee":
            for c in (c0, c1):
                if self._on_track(c, HL):
                    self._kick(c, FLEE_FLAIL * self._rng.random())
        g = 0.0 if footing else GRAVITY
        for c in (c0, c1):
            fall = c.vy
            c.update(WL, HL, g, AIR_FRICTION, self._impact_cb, rg, self.water_y, BUOYANCY, WATER_FRICTION)
            if c.on_floor and not footing:
                c.vx *= TANGENTIAL
            if c.cy == 1 and fall > 2.0 and self._rng.random() * 7.0 < fall:
                self.gfx.squirt(inv_lerp(2.0, 14.0, fall))
        solve_conn(c0, c1, CONN, 0.5)
        for c in (c0, c1):
            c.clamp_inside(WL, HL)
        self.gfx.update(HL)

    def _held_step(self):
        """被猫拿着：腹部那一节由手定位，头垂下来晃；活着的会挣扎。"""
        c0, c1 = self.c0, self.c1
        c0.last_x, c0.last_y = c0.x, c0.y
        if not self.dead:
            self._kick(c0, HELD_KICK)
        c0.vy += GRAVITY * self.room_gravity
        c0.vx *= HELD_DAMP
        c0.vy *= HELD_DAMP
        c0.x += c0.vx
        c0.y += c0.vy
        c1.pinned = True
        solve_conn(c0, c1, CONN, 0.5)
        c1.pinned = False
        hl = self._HL
        if hl is not None:
            for c in (c0, c1):
                if c.y > hl - c.rad:
                    c.y = hl - c.rad
                    c.vy = min(c.vy, 0.0)
        self.footing = 0
        self.gfx.update(hl or 0.0)

    @property
    def on_footing(self):
        return (self.footing > FOOTING_TICKS) and self.room_gravity > 0.5

    def _on_track(self, c, HL):
        """这一节在地面格里（能站的地方）。"""
        return self.room_gravity > 0.5 and c.y >= HL - TILE and self._submersion(c) <= 0.3

    def _submersion(self, c):
        if self.water_y is None:
            return 0.0
        return clampf((c.y + c.rad - self.water_y) / (2.0 * c.rad), 0.0, 1.0)

    def _kick(self, c, k):
        a = self._rng.uniform(0.0, math.tau)
        c.vx += math.cos(a) * k
        c.vy += math.sin(a) * k

    def _vitals(self):
        """伤后的随机死亡、抽搐、回血，以及晕倒时的挣扎。"""
        rng = self._rng
        if self.dead:
            self.stun = 0
            return
        h = self.health
        if h < 0.0 and rng.random() < -h and rng.random() < 0.025:
            self.die()
            return
        if rng.random() * 0.7 > h and rng.random() < 0.125:
            hi = max(1, rng.randint(1, max(1, 27 - int(clampf(20.0 * h, 0.0, 10.0)))))
            self.stun = max(self.stun, rng.randint(1, hi))
        if 0.0 < h < 1.0 and rng.random() < 0.02:
            self.health = min(1.0, h + 1.0 / lerp(140.0, 50.0, h))
        if self.no_jumps > 0 and self.on_footing:
            self.no_jumps -= 1
        if self.stun > 0:
            if self.stun > rng.randint(20, 80):
                self.shake = max(self.shake, 10)
                for c in (self.c0, self.c1):
                    if c.cx or c.cy:
                        a = rng.uniform(0.0, math.tau)
                        k = rng.random() * 3.0
                        c.vx += (math.cos(a) - c.cx) * k
                        c.vy += (math.sin(a) - c.cy) * k
            self.stun -= 1

    # 行为

    def _act(self, WL, HL):
        c0, c1 = self.c0, self.c1
        if not self._on_track(c0, HL) and not self._on_track(c1, HL):
            self.footing = max(0, min(FOOTING_MAX, self.footing - 3))
        self._perceive(HL)
        self._choose_dest(WL)
        self.sitting = False
        tx = self.dest
        if tx is None or (abs(c0.x - tx) < ARRIVE and (self.threat < SIT_UTIL or self.mode == "flee")):
            self.sitting = True
            if self.on_footing:
                ty = HL - TRACK
                for c in (c0, c1):
                    c.vy += max((ty - c.y) / 8.0, -TRACK_PULL_MAX)
        else:
            d = 1.0 if tx > c0.x else -1.0
            self._run(d, HL)
            self.travel = lerp(self.travel, d, 0.4)
        if math.hypot(c0.x - c0.last_x, c0.y - c0.last_y) >= 5.0:
            self.run_cycle += self.run_speed / 10.0
        self.travel *= 0.5 if self.sitting else 0.995

    def _run(self, d, HL):
        """朝 d 方向沿地面走一格：两节都往地面线靠，头往前拉、尾往后拽。"""
        c0, c1 = self.c0, self.c1
        ty = HL - TRACK
        footing = self.on_footing
        if footing:
            for c in (c0, c1):
                c.vy += max((ty - c.y) / 8.0, -TRACK_PULL_MAX)
        mx, my = c0.x + d * STEP_AHEAD, ty
        dx, dy = mx - c0.x, my - c0.y
        n = math.hypot(dx, dy) or 1.0
        ux, uy = dx / n, dy / n
        if not footing:
            ux, uy = ux * AIR_STEER, uy * AIR_STEER
        on_floor = c1.y >= HL - TILE
        if on_floor and ((ux < -0.5 and c0.x > c1.x + 5.0) or (ux > 0.5 and c0.x < c1.x - 5.0)):
            s = -1.0 if ux < 0.0 else 1.0
            c0.vx -= s * TURN_HEAD
            c1.vx += s * TURN_REAR
            c0.vy -= TURN_HOP
        k = self.run_speed * RUN_K
        c0.vx += ux * RUN_HEAD * k
        c0.vy += uy * RUN_HEAD * k
        c1.vx -= ux * RUN_REAR * k
        c1.vy -= uy * RUN_REAR * k
        self.facing = d

    def _swim(self, sub, WL):
        """在水里：减速、往目标方向划，没地方去就往上浮。"""
        c0, c1 = self.c0, self.c1
        self.footing = 0
        self.sitting = False
        for c in (c0, c1):
            c.vy -= SWIM_FLOAT * self._submersion(c) * self.room_gravity
        c0.vx *= 1.0 - 0.05 * sub
        c0.vy *= 1.0 - 0.05 * sub
        c1.vx *= 1.0 - 0.1 * sub
        c1.vy *= 1.0 - 0.1 * sub
        self._perceive(self._HL or 0.0)
        self._choose_dest(WL)
        if self.dest is None or abs(self.dest - c0.x) < ARRIVE:
            c0.vy -= 0.5
            return
        d = 1.0 if self.dest > c0.x else -1.0
        c0.vx += d * 1.6 * sub
        c1.vx -= d * 0.5 * sub
        self.facing = d

    def _perceive(self, HL):
        """更新威胁、恐惧、跑速；看见威胁时受惊或跳开，迎面飞来的武器也跳开。"""
        rng = self._rng
        cx, cy = (self.c0.x + self.c1.x) * 0.5, (self.c0.y + self.c1.y) * 0.5
        raw = 0.0
        near = None
        visible = set()
        for key, x, y in self._threats:
            d = math.hypot(x - cx, y - cy)
            raw += threat_at(d)
            if near is None or d < near[0]:
                near = (d, x, y)
            if d < NOTICE_R:
                visible.add(key)
            if d < NOTICE_R and key not in self._noticed:
                self._noticed.add(key)
                first = key not in self._seen
                self._seen.add(key)
                if first or rng.random() <= self.fear:
                    self.surprise(x, y)
                    if first and d < SPOT_JUMP_R:
                        self.try_jump(x, y)
        self._noticed &= visible
        cur = raw ** (1.0 / 1.5) if raw > 0.0 else 0.0
        util = clampf(lerp(-0.01, 1.01, cur), 0.0, 1.0)
        w = lerp(0.1, 1.0, inv_lerp(0.1, 2.0, raw) ** 0.5)
        target = util * w
        if target > self.threat:
            self.threat += (target - self.threat) * THREAT_UP
        else:
            self.threat = max(target, self.threat - THREAT_DOWN)
        self.panic = 1.0 - 1.0 / (cur + 1.0)
        self.fear = lerp_tick(self.fear, max(self.threat, self.panic**0.7), 0.07, 1.0 / 30.0)
        fleeing = self.threat >= FLEE_UTIL
        if fleeing and self.mode != "flee":
            self.flee_timer = 0
        self.mode = "flee" if fleeing else "idle"
        if fleeing:
            self.run_speed = lerp_tick(self.run_speed, RUN_FLEE, 0.01, 0.1)
            if near is not None and rng.random() < self.panic:
                d, x, y = near
                if d < HEAD_RAD + REAR_RAD + 40.0 * self.fear:
                    self.try_jump(x, y)
        else:
            self.run_speed = lerp_tick(
                self.run_speed, RUN_IDLE + 0.5 * max(self.threat, self.fear), 0.01, 1.0 / 60.0
            )
        for _, wx, wy, wvx, _ in self._weapons:
            ahead = math.copysign(WEAPON_WARN_R, wvx)
            if (
                abs(wvx) > 0.5
                and wvx * (cx - wx) > 0.0
                and math.hypot(cx - wx - ahead, cy - wy) < WEAPON_WARN_R
            ):
                if wy >= cy - WEAPON_WARN_ABOVE:
                    self.try_jump(wx, wy)
                else:
                    self.gfx.squirt(1.0)

    def _choose_dest(self, WL):
        rng = self._rng
        x = self.c0.x
        lo, hi = IDLE_MARGIN, max(IDLE_MARGIN, WL - IDLE_MARGIN)
        if self._shelter is not None and self.threat < SHELTER_UTIL:
            self.dest = self._shelter
            return
        if self.mode == "flee":
            self.flee_timer -= 1
            if self.dest is None or self.flee_timer <= 0:
                best, bs = None, None
                for i in range(FLEE_SAMPLES + 2):
                    if i < 2:
                        c = lo if i == 0 else hi
                    else:
                        c = rng.uniform(max(lo, x - FLEE_RANGE), min(hi, x + FLEE_RANGE))
                    s = self._spot_threat(c, x)
                    if bs is None or s < bs:
                        best, bs = c, s
                self.dest = best
                self.flee_timer = FLEE_REPICK
            return
        self.idle_counter -= 1
        c = rng.uniform(lo, hi)
        margin = lerp(IDLE_MARGIN_HI, IDLE_MARGIN_LO, self.idle_counter / IDLE_MARGIN_SPAN)
        if self.dest is None or self._idle_score(c, x) < self._idle_score(self.dest, x) + margin:
            self.dest = c
            self.idle_counter = rng.randint(*IDLE_COUNTER)

    def _idle_score(self, c, x):
        return 1.0 + self._spot_threat(c, x) * 1000.0

    def _spot_threat(self, c, x):
        """站到 c 的威胁，路上要从威胁身边穿过时加罚。"""
        s = 0.0
        hl = self._HL or 0.0
        for _, tx, ty in self._threats:
            s += threat_at(math.hypot(tx - c, ty - (hl - TRACK)))
            if min(x, c) < tx < max(x, c):
                s += CROSS_PENALTY
        return s

    def surprise(self, x, y):
        """受惊：往背离的方向一蹿、抖一阵，恐惧猛涨。"""
        rng = self._rng
        cx, cy = self.c1.x, self.c1.y
        d = math.hypot(cx - x, cy - y)
        if d < SURPRISE_R:
            ax, ay = ((cx - x) / d, (cy - y) / d) if d > 1e-6 else (0.0, -1.0)
            k = 0.5 + 0.5 * self.fear
            for c in (self.c0, self.c1):
                if self._HL is not None and self._on_track(c, self._HL):
                    a = rng.uniform(0.0, math.tau)
                    c.vx += (math.cos(a) * 4.0 + ax * 2.0) * k
                    c.vy += (math.sin(a) * 4.0 + ay * 2.0) * k
        self.shake = max(self.shake, rng.randint(5, 15))
        self.fear = lerp_tick(self.fear, 1.0, 0.3, 1.0 / 7.0)
        self.gfx.squirt(self.fear)

    def try_jump(self, x, y):
        """背离 (x, y) 斜向上跳开，空中翻滚；落地后冷却一阵才能再跳。"""
        if not self.conscious:
            return
        self.gfx.squirt(0.5 + 0.5 * self.fear)
        if not self.can_jump:
            return
        rng = self._rng
        c0, c1 = self.c0, self.c1
        mx, my = (c0.x + c1.x) * 0.5, (c0.y + c1.y) * 0.5
        vx, vy = mx - x, my - y
        n = math.hypot(vx, vy) or 1.0
        a = rng.uniform(0.0, math.tau)
        vx, vy = vx / n + math.cos(a) * 0.3, vy / n + math.sin(a) * 0.3
        n = math.hypot(vx, vy) or 1.0
        vx, vy = vx / n, vy / n
        t = lerp(0.7, 0.3, inv_lerp(-0.5, 0.5, -vy))
        vx, vy = _slerp_up(vx, vy, t)
        for c in (c0, c1):
            c.vx *= 0.5
            c.vy *= 0.5
            a = rng.uniform(0.0, math.tau)
            r = JUMP_RAND * rng.random()
            c.vx += vx * JUMP_SPEED + math.cos(a) * r
            c.vy += vy * JUMP_SPEED + math.sin(a) * r
        s = -1.0 if rng.random() < 0.5 else 1.0
        px, py = -vy * s, vx * s
        c0.vx += px * JUMP_SPIN
        c0.vy += py * JUMP_SPIN
        c1.vx -= px * JUMP_SPIN
        c1.vy -= py * JUMP_SPIN
        self.footing = 0
        self.no_jumps = JUMP_COOLDOWN
        self.jumped = True


def _slerp_up(x, y, t):
    """单位向量 (x, y) 朝正上方 (0, -1) 转过 t 比例的夹角。"""
    a0 = math.atan2(y, x)
    a1 = -math.pi / 2.0
    da = (a1 - a0 + math.pi) % math.tau - math.pi
    a = a0 + da * t
    return math.cos(a), math.sin(a)
