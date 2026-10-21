"""物理内核：显式速度质点 + 连接约束 + 轴对齐碰撞。坐标系 y↓，常量换算见 core.units。"""

from __future__ import annotations
import math

from .units import K_IMP, K_VEL, clampf, damp60, lerp

RAD0 = 9.0  # 胸
RAD1 = 8.0  # 臀
MASS = 0.35
DIST_STAND = 17.0
DIST_CRAWL = 17.0

GRAVITY = 0.9 * K_IMP  # y↓
AIR_FRICTION = damp60(0.999)
BOUNCE = 0.1
WEIGHT_SYMMETRY = 0.5
ELASTICITY = 1.0
SURFACE_FRICTION = 0.5
MAX_STRETCH = 1.5  # pinned 端硬上限，rest×此值

STOP_THRESH = (1.0 + 9.0 * (1.0 - BOUNCE)) * K_VEL
TANGENTIAL = min(max(SURFACE_FRICTION * 2.0, 0.0), 1.0)

IMPACT_THRESHOLD = 1.0 * K_VEL
IMPACT_SHAKE_MOMENTUM = 7.0 * K_VEL
IMPACT_STRENGTH_KNEE = 30.0 * K_VEL


def apply_water(
    obj,
    water_y,
    buoyancy: float,
    water_friction,
    room_gravity: float,
    air_friction: float,
    immunity: float = 0.0,
) -> None:
    r = obj.rad
    sub = 0.0
    if water_y is not None and obj.y + r > water_y:
        sub = (obj.y + r - water_y) / (2.0 * r)
        if sub > 1.0:
            sub = 1.0
    if sub <= 0.0:
        obj.vx *= air_friction
        obj.vy *= air_friction
        return
    if obj.vx > -obj.vy * 5.0 and abs(obj.vx) > 10.0 and obj.vy > 0.0 and sub < 0.5:
        obj.vy *= -0.5
        obj.vx *= 0.75
        return
    obj.vy -= buoyancy * room_gravity * sub  # 浮力，y↓取负
    wf = water_friction if water_friction is not None else air_friction
    spd = math.hypot(obj.vx, obj.vy)
    inner = lerp(wf * immunity, wf, (1.0 / max(1.0, spd - 10.0)) ** 0.5)
    k = lerp(air_friction, inner, sub)
    obj.vx *= k
    obj.vy *= k


class BodyChunk:
    __slots__ = (
        "x",
        "y",
        "vx",
        "vy",
        "last_x",
        "last_y",
        "last_last_x",
        "last_last_y",
        "rad",
        "mass",
        "index",
        "cx",
        "cy",
        "lcx",
        "lcy",
        "pinned",
        "collide_with_objects",
        "impact_scale",
    )

    def __init__(self, index: int, x: float, y: float, rad: float, mass: float):
        self.index = index
        self.x = self.last_x = self.last_last_x = x
        self.y = self.last_y = self.last_last_y = y
        self.vx = self.vy = 0.0
        self.rad = rad
        self.mass = mass
        self.cx = self.cy = 0
        self.lcx = self.lcy = 0
        self.pinned = False  # 外部定位，不积分不撞
        self.collide_with_objects = True
        self.impact_scale = 1.0  # 撞击速度放大（拖拽时补回限速）

    @property
    def on_floor(self) -> bool:
        return self.cy == 1  # y↓，+1=着地

    def hold_still(self) -> None:
        """位置由外面定：只推进历史、清掉接触，不积分。"""
        self.last_last_x, self.last_last_y = self.last_x, self.last_y
        self.last_x, self.last_y = self.x, self.y
        self.lcx, self.lcy = self.cx, self.cy
        self.cx = self.cy = 0

    def update(
        self,
        W: float,
        H: float,
        gravity: float = GRAVITY,
        air_friction: float = AIR_FRICTION,
        impact=None,
        room_gravity: float = 1.0,
        water_y=None,
        buoyancy: float = 1.0,
        water_friction=None,
        water_immunity: float = 0.0,
    ) -> None:
        if self.vx != self.vx:
            self.vx = 0.0
        if self.vy != self.vy:
            self.vy = 0.0
        if self.pinned:
            self.hold_still()
            return
        self.vy += gravity * room_gravity
        apply_water(self, water_y, buoyancy, water_friction, room_gravity, air_friction, water_immunity)
        self.last_last_x, self.last_last_y = self.last_x, self.last_y
        self.last_x, self.last_y = self.x, self.y
        self.x += self.vx
        self.y += self.vy
        self.lcx, self.lcy = self.cx, self.cy
        self.cx = self.cy = 0
        self._collide(W, H, impact)

    def clamp_inside(self, W: float, H: float) -> None:
        if self.pinned:
            return
        r = max(self.rad, 1.0)
        if self.x < r:
            self.x = r
        elif self.x > W - r:
            self.x = W - r
        if self.y < r:
            self.y = r
        elif self.y > H - r:
            self.y = H - r

    def _collide(self, W: float, H: float, impact) -> None:
        r = max(self.rad, 1.0)
        if self.y + r > H and self.vy > 0:
            self.y = H - r
            if self.vy > IMPACT_THRESHOLD and impact is not None:
                fire_impact(self, (0, 1), abs(self.vy), self.lcy < 1, impact)
            self.cy = 1
            self.vy = -abs(self.vy) * BOUNCE
            if self.vy > -STOP_THRESH:
                self.vy = 0.0
            self.vx *= TANGENTIAL
        elif self.y - r < 0 and self.vy < 0:
            self.y = r
            if -self.vy > IMPACT_THRESHOLD and impact is not None:
                fire_impact(self, (0, -1), abs(self.vy), self.lcy > -1, impact)
            self.cy = -1
            self.vy = abs(self.vy) * BOUNCE
            if self.vy < STOP_THRESH:
                self.vy = 0.0
            self.vx *= TANGENTIAL
        if self.x + r > W and self.vx > 0:
            self.x = W - r
            if self.vx > IMPACT_THRESHOLD and impact is not None:
                fire_impact(self, (1, 0), abs(self.vx), self.lcx < 1, impact)
            self.cx = 1
            self.vx = -abs(self.vx) * BOUNCE
            if self.vx > -STOP_THRESH:
                self.vx = 0.0
            self.vy *= TANGENTIAL
        elif self.x - r < 0 and self.vx < 0:
            self.x = r
            if -self.vx > IMPACT_THRESHOLD and impact is not None:
                fire_impact(self, (-1, 0), abs(self.vx), self.lcx > -1, impact)
            self.cx = -1
            self.vx = abs(self.vx) * BOUNCE
            if self.vx < STOP_THRESH:
                self.vx = 0.0
            self.vy *= TANGENTIAL


def fire_impact(c: BodyChunk, direction, speed: float, first_contact: bool, impact) -> None:
    if not first_contact:
        return
    speed *= getattr(c, "impact_scale", 1.0)
    momentum = speed * c.mass
    if momentum <= IMPACT_SHAKE_MOMENTUM:
        return
    strength = max((momentum - IMPACT_STRENGTH_KNEE) / 50.0, 0.0)
    ix = direction[0] * momentum * 0.1
    iy = direction[1] * momentum * 0.1
    impact(c, direction, speed, strength, ix, iy)


def solve_conn(
    a: BodyChunk,
    b: BodyChunk,
    rest: float = DIST_STAND,
    wsym: float = WEIGHT_SYMMETRY,
    elasticity: float = ELASTICITY,
    ctype: str = "Normal",
    max_stretch: float = MAX_STRETCH,
) -> None:
    dx, dy = b.x - a.x, b.y - a.y
    d = math.hypot(dx, dy) or 1e-6
    if ctype == "Pull" and not (d > rest):
        return
    if ctype == "Push" and not (d < rest):
        return
    ux, uy = dx / d, dy / d
    corr = (rest - d) * elasticity  # >0 推开，<0 拉拢
    ca = corr * wsym
    cb = corr * (1.0 - wsym)
    ap, bp = a.pinned, b.pinned
    if ap and bp:
        return
    if ap:
        b.x += ux * cb
        b.y += uy * cb
        b.vx += ux * cb * K_IMP
        b.vy += uy * cb * K_IMP
    elif bp:
        a.x -= ux * ca
        a.y -= uy * ca
        a.vx -= ux * ca * K_IMP
        a.vy -= uy * ca * K_IMP
    else:
        a.x -= ux * ca
        a.y -= uy * ca
        a.vx -= ux * ca * K_IMP
        a.vy -= uy * ca * K_IMP
        b.x += ux * cb
        b.y += uy * cb
        b.vx += ux * cb * K_IMP
        b.vy += uy * cb * K_IMP

    # 硬上限，仅单端 pinned 时触发
    if max_stretch is not None and (ap != bp):
        limit = rest * max_stretch
        dx, dy = b.x - a.x, b.y - a.y
        d = math.hypot(dx, dy)
        if d > limit:
            ux, uy = dx / d, dy / d
            if ap:
                b.x = a.x + ux * limit
                b.y = a.y + uy * limit
            else:
                a.x = b.x - ux * limit
                a.y = b.y - uy * limit


def aabb_wall_collide(obj, WL, HL, impact=None):
    r = obj.rad
    tang = clampf(obj.surface_friction * 2.0, 0.0, 1.0)
    stop = 1.0 + 9.0 * (1.0 - obj.bounce)  # 低弹性→高阈值，撞墙即停
    has_ceil = hasattr(obj, "_contact_ceil")
    prev_floor, prev_x = obj._contact_floor, obj._contact_x
    prev_ceil = obj._contact_ceil if has_ceil else False
    obj._contact_floor = False
    obj._contact_x = 0
    if has_ceil:
        obj._contact_ceil = False
    if obj.y + r > HL and obj.vy > 0:
        obj.y = HL - r
        if impact is not None:
            fire_impact(obj, (0, 1), abs(obj.vy), not prev_floor, impact)
        obj._contact_floor = True
        obj.vy = -abs(obj.vy) * obj.bounce
        if obj.vy > -stop:
            obj.vy = 0.0
        obj.vx *= tang
    elif obj.y - r < 0 and obj.vy < 0:
        obj.y = r
        if impact is not None:
            fire_impact(obj, (0, -1), abs(obj.vy), not prev_ceil, impact)
        if has_ceil:
            obj._contact_ceil = True
        obj.vy = abs(obj.vy) * obj.bounce
        if obj.vy < stop:
            obj.vy = 0.0
        obj.vx *= tang
    if obj.x + r > WL and obj.vx > 0:
        obj.x = WL - r
        if impact is not None:
            fire_impact(obj, (1, 0), abs(obj.vx), prev_x < 1, impact)
        obj._contact_x = 1
        obj.vx = -abs(obj.vx) * obj.bounce
        if obj.vx > -stop:
            obj.vx = 0.0
        obj.vy *= tang
    elif obj.x - r < 0 and obj.vx < 0:
        obj.x = r
        if impact is not None:
            fire_impact(obj, (-1, 0), abs(obj.vx), prev_x > -1, impact)
        obj._contact_x = -1
        obj.vx = abs(obj.vx) * obj.bounce
        if obj.vx < stop:
            obj.vx = 0.0
        obj.vy *= tang


def collide_objects(entities) -> None:
    """同一碰撞层的物体两两推开，层 0 不参与。"""
    buckets: dict[int, list] = {}
    for e in entities:
        layer = e.collision_layer
        if layer == 0:
            continue
        buckets.setdefault(layer, []).append(e)
    for objs in buckets.values():
        n = len(objs)
        if n < 2:
            continue
        groups = [o.collision_chunks() for o in objs]
        for i in range(n):
            for j in range(i + 1, n):
                _collide_pair(objs[i], objs[j], groups[i], groups[j])


def _grounded(o) -> bool:
    f = getattr(o, "on_floor", None)  # 只有猫的身体有
    return f is not None and f()


def _uncross(a, b):
    """两只猫都在地上、上身交叉（头的左右和臀相反）时 a 往哪侧挪才解开（±1）；没交叉 None。
    这时沿连线推开会把交叉越推越深，两只就卡成 X。"""
    if not (_grounded(a) and _grounded(b)):
        return None
    dh, dt = a.chunk0.x - b.chunk0.x, a.chunk1.x - b.chunk1.x
    if dh * dt >= 0.0:
        return None
    return 1.0 if dt > 0.0 else -1.0


def _collide_pair(a, b, a_chunks, b_chunks) -> None:
    if not (getattr(a, "collides_with", None) is None or a.collides_with(b)):
        return
    a_fix = getattr(a, "steady", False) and not hasattr(b, "steady")
    b_fix = getattr(b, "steady", False) and not hasattr(a, "steady")
    side = _uncross(a, b)
    for ca in a_chunks:
        if not ca.collide_with_objects:
            continue
        for cb in b_chunks:
            if not cb.collide_with_objects:
                continue
            rad_sum = ca.rad + cb.rad
            dx, dy = cb.x - ca.x, cb.y - ca.y
            if not (-rad_sum < dx < rad_sum and -rad_sum < dy < rad_sum):
                continue
            dist = math.hypot(dx, dy)
            if dist >= rad_sum:
                continue
            ap = a_fix or getattr(ca, "pinned", False)  # 世界物体无 pinned
            bp = b_fix or getattr(cb, "pinned", False)
            if ap and bp:
                continue
            if side is not None:  # 交叉着：横着往各自臀那侧推
                ux, uy = -side, 0.0
            elif dist < 1e-9:  # 完全重合时横着推开
                ux, uy = 1.0, 0.0
            else:
                ux, uy = dx / dist, dy / dist
            ga, gb = _grounded(a), _grounded(b)
            if ga != gb:  # 着地的一方不被没着地的顶动，免得叠在身上的猫带着下面的一起漂
                ap = ap or ga
                bp = bp or gb
                if ap and bp:
                    continue
            pen = rad_sum - dist
            if ap:
                wa, wb = 0.0, 1.0
            elif bp:
                wa, wb = 1.0, 0.0
            else:
                wa = cb.mass / (ca.mass + cb.mass)
                wb = 1.0 - wa
            ax, ay = ux * pen * wa, uy * pen * wa
            bx, by = ux * pen * wb, uy * pen * wb
            ca.x -= ax
            ca.y -= ay
            ca.vx -= ax
            ca.vy -= ay
            cb.x += bx
            cb.y += by
            cb.vx += bx
            cb.vy += by
            if ca.x == cb.x:  # 同 x 时加确定性微扰
                if not ap:
                    ca.vx += 1e-4
                if not bp:
                    cb.vx -= 1e-4
            for o, mine, other, ch in ((a, ca, b, cb), (b, cb, a, ca)):
                note = getattr(o, "note_foot", None)  # 只有猫的身体有
                if note is not None:
                    note(mine, other, ch)
