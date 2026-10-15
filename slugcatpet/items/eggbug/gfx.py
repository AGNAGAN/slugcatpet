"""蛋虫的视觉状态：腿、触角、背上的蛋、尾尖、侧翻程度和滴液，每 tick 随身体更新。y↓。"""

from __future__ import annotations

import math

from ...core.units import clampf, lerp, lerp_tick
from ...world.liquid_drip import new_drip, step_drips

LEG_LEN = 35.0
THIGH, SHIN = LEG_LEN / 3.0, LEG_LEN * 2.0 / 3.0
ANT_SEGS = 4
ANT_GAP = 15.0
ANT_ROOT = 20.0  # 第一节离头的最远距离
EGG_ROWS, EGG_PER_ROW = 2, 3
EGG_HANG = 5.0
DANGLE_TICKS = 30
DRIP_MAX = 40


def _unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-9 else (0.0, -1.0)


def _rnv(rng):
    a = rng.uniform(0.0, math.tau)
    return math.cos(a), math.sin(a)


def perp(x, y):
    """单位法向（原版 PerpendicularVector）。"""
    x, y = _unit(x, y)
    return -y, x


def deg_to_vec(a):
    r = math.radians(a)
    return math.sin(r), math.cos(r)


def vec_to_deg(x, y):
    return math.degrees(math.atan2(x, y))


def dist_to_line(px, py, ax, ay, bx, by):
    """点到 a→b 直线的有符号距离（原版 DistanceToLine(V, l2=a, l1=b)）。"""
    d = math.hypot(ay - by, ax - bx) or 1e-9
    return ((ay - by) * px - (ax - bx) * py + ax * by - ay * bx) / d


def ik(ax, ay, cx, cy, a, b, flip):
    """两段肢体的关节点：长 a、b，flip 定弯向和弯的程度（原版 InverseKinematic）。"""
    d = math.hypot(cx - ax, cy - ay) or 1e-9
    k = math.degrees(math.acos(clampf((d * d + a * a - b * b) / (2.0 * d * a), 0.2, 0.98))) * flip
    ux, uy = deg_to_vec(vec_to_deg(cx - ax, cy - ay) + k)
    return ax + ux * a, ay + uy * a


def _slerp(v0, v1, t):
    a0, a1 = math.atan2(v0[1], v0[0]), math.atan2(v1[1], v1[0])
    a = a0 + ((a1 - a0 + math.pi) % math.tau - math.pi) * t
    return math.cos(a), math.sin(a)


class EggBugGfx:
    def __init__(self, bug, rng):
        self.bug = bug
        self.rng = rng
        c0, c1 = bug.c0, bug.c1
        self.dir = _unit(c0.x - c1.x, c0.y - c1.y)
        self.flip = self.last_flip = 0.0
        self.zrot = self.last_zrot = (0.0, 1.0)
        self.away = (0.0, 0.0)
        self.dangle = DANGLE_TICKS
        tx, ty = c1.x - self.dir[0] * 7.0, c1.y - self.dir[1] * 7.0
        self.tail = [tx, ty, 0.0, 0.0]
        self.last_tail = (tx, ty)
        # 腿：[脚 x, 脚 y, 上帧 x, 上帧 y, 是否踩着, vx, vy]；i%2 是左右，i<2 是前腿
        self.legs = [[c0.x, c0.y, c0.x, c0.y, False, 0.0, 0.0] for _ in range(4)]
        self.ants = [[[c0.x, c0.y, 0.0, 0.0] for _ in range(ANT_SEGS)] for _ in range(2)]
        self.last_ants = [[(c0.x, c0.y)] * ANT_SEGS for _ in range(2)]
        self.eggs = [[c1.x, c1.y, 0.0, 0.0] for _ in range(EGG_ROWS * EGG_PER_ROW)]
        self.last_eggs = [(c1.x, c1.y)] * (EGG_ROWS * EGG_PER_ROW)
        self.drips = []
        self.jitter = (0.0, 0.0, 0.0, 0.0)
        self.hue = lerp(-0.15, 0.1, (rng.random() + rng.random()) * 0.5)
        self._ready = False

    # 几何

    @property
    def show_eggs(self):
        return self.bug.has_eggs and not self.bug.dead

    def egg_attach(self, i):
        """背上第 i 个蛋的挂点：两排随侧翻程度分开，侧视时重合。"""
        b = self.bug
        row, e = divmod(i, EGG_PER_ROW)
        t = e / 2.0
        vx, vy = lerp(b.c1.x, self.tail[0], t), lerp(b.c1.y, self.tail[1], t)
        dx, dy = _unit(b.c0.x - vx, b.c0.y - vy)
        k = deg_to_vec(vec_to_deg(*self.zrot) + (-45.0 if row == 0 else 45.0))[0]
        if self.show_eggs:
            k *= lerp(1.5, 1.0, abs(self.flip))
        k *= 3.0 if e == 2 else 5.0
        px, py = -dy, dx
        s = lerp(2.0, -2.0, t)
        return vx + dx * s + px * k, vy + dy * s + py * k

    def row_in_front(self, row, ts=1.0):
        """这一排蛋在身体前面（朝着观看者）。"""
        z = _slerp(self.last_zrot, self.zrot, ts)
        return deg_to_vec(vec_to_deg(*z) + (-45.0 if row == 0 else 45.0))[1] > 0.0

    def ant_dir(self, side, side_fac):
        """触角伸出的方向：身体方向往一侧偏，偏多少随侧翻程度。"""
        dx, dy = self.dir
        px, py = -dy, dx
        f = self.flip
        k = lerp(-0.7 if side == 0 else 0.7, f * -1.4, abs(f * 0.7)) * side_fac
        return _unit(dx + px * k, dy + py * k)

    def _solid(self, x, y, HL):
        wl = self.bug._WL
        return y >= HL or x < 0.0 or (wl is not None and x > wl)

    # 推进

    def update(self, HL):
        b, rng = self.bug, self.rng
        c0, c1 = b.c0, b.c1
        self.dir = _unit(c0.x - c1.x, c0.y - c1.y)
        if not self._ready:
            self._snap(HL)
        self.dangle = 0 if b.conscious and b.on_footing else DANGLE_TICKS
        self.last_flip, self.last_zrot = self.flip, self.zrot
        self.zrot = _slerp(self.zrot, deg_to_vec(-90.0 * self.flip), 0.5)
        if b.sitting:
            self.away = _unit(lerp(self.away[0], 0.0, 0.1), lerp(self.away[1], -1.0, 0.1))
        else:
            self.away = (self.away[0] * 0.7, self.away[1] * 0.7)
        self._tail(HL)
        self._legs(HL)
        self._antennae(HL)
        self._eggs()
        self._drips(HL)
        if b.shake > 0:
            j0, j1 = _rnv(rng), _rnv(rng)
            r0, r1 = rng.random() * 4.0, rng.random() * 4.0
            self.jitter = (j0[0] * r0, j0[1] * r0, j1[0] * r1, j1[1] * r1)
        else:
            self.jitter = (0.0, 0.0, 0.0, 0.0)

    def _snap(self, HL):
        """第一帧：各部件直接摆到该在的位置。"""
        self._ready = True
        for i in range(len(self.eggs)):
            ax, ay = self.egg_attach(i)
            self.eggs[i] = [ax, ay + EGG_HANG, 0.0, 0.0]
            self.last_eggs[i] = (ax, ay + EGG_HANG)
        hx, hy = self.bug.c0.x, self.bug.c0.y
        for s in range(2):
            ux, uy = self.ant_dir(s, 1.0)
            for i in range(ANT_SEGS):
                r = ANT_ROOT + ANT_GAP * i
                p = (hx + ux * r, min(hy + uy * r, HL - 1.0))
                self.ants[s][i] = [p[0], p[1], 0.0, 0.0]
                self.last_ants[s][i] = p

    def _tail(self, HL):
        """尾尖：被拉向腹部后方偏腹侧的点，有弹性、往下垂。"""
        b = self.bug
        c0, c1 = b.c0, b.c1
        bx, by = _unit(c1.x - c0.x, c1.y - c0.y)
        px, py = perp(c0.x - c1.x, c0.y - c1.y)
        t = self.tail
        self.last_tail = (t[0], t[1])
        t[0] += t[2]
        t[1] += t[3]
        t[2] *= 0.99
        t[3] *= 0.99
        gx = c1.x + bx * 7.0 + px * self.flip * 7.0
        gy = c1.y + by * 7.0 + py * self.flip * 7.0
        ox, oy = gx - t[0], gy - t[1]
        d = math.hypot(ox, oy)
        t[2] += ox * 0.2 + c1.vx * 0.1
        t[3] += oy * 0.2 + c1.vy * 0.1
        if d > 6.0:
            k = (d - 6.0) / d
            t[0] += ox * k
            t[1] += oy * k
            t[2] += ox * k
            t[3] += oy * k
        t[2] = (t[2] - c1.vx) * 0.5 + c1.vx
        t[3] = (t[3] - c1.vy) * 0.5 + c1.vy
        t[3] += 0.4 * b.room_gravity
        t[2] += bx * 0.8
        t[3] += by * 0.8
        if t[1] > HL - 3.0:
            t[1] = HL - 3.0

    def _legs(self, HL):
        b = self.bug
        c0, c1 = b.c0, b.c1
        dx, dy = self.dir
        num = vec_to_deg(c0.x - c1.x, c0.y - c1.y)
        lean = sum(dist_to_line(leg[0], leg[1], c1.x, c1.y, c0.x, c0.y) for leg in self.legs)
        self.flip = lerp_tick(self.flip, clampf(lean / 40.0, -1.0, 1.0), 0.07, 0.1)
        px, py = perp(c0.x - c1.x, c0.y - c1.y)
        wall = 0.0
        if self._solid(c0.x + px * 20.0, c0.y + py * 20.0, HL):
            wall += 1.0
        if self._solid(c0.x - px * 20.0, c0.y - py * 20.0, HL):
            wall -= 1.0
        if wall:
            self.flip = lerp_tick(self.flip, wall, 0.07, 0.05)
        ahead = 1.0 if dx >= 0.0 else -1.0
        for i, leg in enumerate(self.legs):
            leg[2], leg[3] = leg[0], leg[1]
            hx, hy = self.hip(i)
            front = i < 2
            side = -1.0 if i % 2 == 0 else 1.0
            if not self.dangle:
                reach = 30.0 if front else -22.0
                tx = hx + ahead * reach + side * 3.0 + b.travel * 6.0
                phase = 0.5 + 0.5 * math.sin((b.run_cycle + i * 0.25) * math.pi)
                if leg[4] and (
                    abs(leg[0] - tx) > lerp(26.0, 6.0, phase)
                    or math.hypot(leg[0] - hx, leg[1] - hy) > LEG_LEN
                ):
                    leg[4] = False
                if not leg[4]:
                    gap = tx - leg[0]
                    mv = min(abs(gap), max(abs(gap) * 0.4, 4.0 + 1.6 * abs(c0.vx)))
                    leg[0] += mv if gap > 0.0 else -mv
                    rem = abs(tx - leg[0])
                    leg[1] = HL - min(6.0, rem * 0.5)
                    if rem < 1.5:
                        leg[0], leg[1], leg[4] = tx, HL, True
                leg[5] = leg[6] = 0.0
            else:
                self._dangle(leg, num, front, i % 2, wall)
            ox, oy = leg[0] - hx, leg[1] - hy
            d = math.hypot(ox, oy)
            if d > LEG_LEN:
                leg[0], leg[1] = hx + ox / d * LEG_LEN, hy + oy / d * LEG_LEN
            if leg[1] > HL:
                leg[1] = HL

    def _dangle(self, leg, num, front, side, wall):
        """悬空、死了或被拿着：腿朝两侧张开垂着，活着的乱蹬。"""
        b, rng = self.bug, self.rng
        c0 = b.c0
        leg[4] = False
        leg[0] += leg[5]
        leg[1] += leg[6]
        leg[5] *= 0.99
        leg[6] *= 0.99
        a = 45.0 if front else 135.0
        sgn = 1.0 if side == 0 else -1.0
        ux, uy = deg_to_vec(num + a * (-wall if wall else sgn))
        rx, ry = deg_to_vec(num + a * sgn)
        ax = c0.x + ux * LEG_LEN * 0.2 + rx * LEG_LEN * 0.1
        ay = c0.y + uy * LEG_LEN * 0.2 + ry * LEG_LEN * 0.1
        for tx, ty in ((ax, ay), (c0.x, c0.y)):
            ox, oy = leg[0] - tx, leg[1] - ty
            d = math.hypot(ox, oy)
            if d > LEG_LEN:
                k = (LEG_LEN - d) / d
                leg[0] += ox * k
                leg[1] += oy * k
                leg[5] += ox * k
                leg[6] += oy * k
            leg[5] = (leg[5] - c0.vx) * 0.9 + c0.vx
            leg[6] = (leg[6] - c0.vy) * 0.9 + c0.vy
        ox, oy = leg[0] - c0.x, leg[1] - c0.y
        d = math.hypot(ox, oy)
        if d < 6.0:
            ox, oy = _unit(ox, oy)
            leg[0], leg[1] = c0.x + ox * 6.0, c0.y + oy * 6.0
        gx, gy = ax + ux * LEG_LEN * 0.7, ay + uy * LEG_LEN * 0.7
        leg[5] = lerp(leg[5], gx - leg[0], 0.3)
        leg[6] = lerp(leg[6], gy - leg[1], 0.3) + 0.4 * b.room_gravity
        if b.conscious:
            rx, ry = _rnv(rng)
            leg[5] += rx * 3.0
            leg[6] += ry * 3.0

    def hip(self, i):
        b = self.bug
        dx, dy = self.dir
        k = 4.0 if i < 2 else -4.0
        return lerp(b.c0.x, b.c1.x, 0.3) + dx * k, lerp(b.c0.y, b.c1.y, 0.3) + dy * k

    def _antennae(self, HL):
        """触角：一串互相牵着的点，被推向伸出方向；死了也照样伸着，活着时轻轻颤。"""
        b, rng = self.bug, self.rng
        c0 = b.c0
        rx, ry = self.ant_dir(0, 1.0)
        root = (c0.x + rx * 4.0, c0.y + ry * 4.0)
        tremble = 1.0 + b.fear
        for s in range(2):
            pts = self.ants[s]
            self.last_ants[s] = [(p[0], p[1]) for p in pts]
            for i, p in enumerate(pts):
                t = i / (ANT_SEGS - 1)
                p[0] += p[2]
                p[1] += p[3]
                p[2] *= 0.81
                p[3] *= 0.81
                if p[1] > HL - 1.0:
                    p[1] = HL - 1.0
                if i == 0:
                    ox, oy = p[0] - root[0], p[1] - root[1]
                    d = math.hypot(ox, oy)
                    if d > ANT_ROOT:
                        k = (ANT_ROOT - d) / d
                        p[0] += ox * k
                        p[1] += oy * k
                        p[2] += ox * k
                        p[3] += oy * k
                else:
                    q = pts[i - 1]
                    ox, oy = p[0] - q[0], p[1] - q[1]
                    d = math.hypot(ox, oy)
                    if d > ANT_GAP:
                        k = (ANT_GAP - d) / d * 0.5
                        p[0] += ox * k
                        p[1] += oy * k
                        p[2] += ox * k
                        p[3] += oy * k
                        q[0] -= ox * k
                        q[1] -= oy * k
                        q[2] -= ox * k
                        q[3] -= oy * k
                if i > 1:
                    q = pts[i - 2]
                    ux, uy = _unit(p[0] - q[0], p[1] - q[1])
                    p[2] += ux * 0.8
                    p[3] += uy * 0.8
                    q[2] -= ux * 0.8
                    q[3] -= uy * 0.8
                ux, uy = self.ant_dir(s, math.sqrt(1.0 - t))
                k = math.sin(t * math.pi) * 1.7
                f = lerp(6.0, 2.0, t)
                p[2] += (ux + self.away[0] * k) * f
                p[3] += (uy + self.away[1] * k) * f + 0.3 * b.room_gravity
                if b.conscious:
                    jx, jy = _rnv(rng)
                    r = t * rng.random() * tremble
                    p[0] += jx * r
                    p[1] += jy * r

    def _eggs(self):
        b, rng = self.bug, self.rng
        c0, c1 = b.c0, b.c1
        mx, my = (c0.x + c1.x) * 0.5, (c0.y + c1.y) * 0.5
        px, py = perp(c1.x - c0.x, c1.y - c0.y)
        f = self.flip * 0.4
        leak = (b.shake > 0 or b.no_jumps > 60) and self.show_eggs
        for i, e in enumerate(self.eggs):
            self.last_eggs[i] = (e[0], e[1])
            e[0] += e[2]
            e[1] += e[3]
            e[2] *= 0.99
            e[3] *= 0.99
            ax, ay = self.egg_attach(i)
            ox, oy = e[0] - ax, e[1] - ay
            d = math.hypot(ox, oy)
            if d > 1e-6:
                k = (EGG_HANG - d) / d
                e[0] += ox * k
                e[1] += oy * k
                e[2] += ox * k
                e[3] += oy * k
            e[2] = (e[2] - c1.vx) * 0.9 + c1.vx
            e[3] = (e[3] - c1.vy) * 0.9 + c1.vy
            ox, oy = _unit(ax - mx, ay - my)
            e[2] += ox * 0.7 + px * f
            e[3] += oy * 0.7 + py * f + 0.9 * b.room_gravity
            if leak and rng.random() < 0.05 and rng.random() < b.fear:
                ux, uy = _unit(e[0] - ax, e[1] - ay)
                v = lerp(3.0, 7.0, rng.random())
                jx, jy = _rnv(rng)
                r = rng.random() * 4.0
                self._drip(e[0], e[1], ux * v + jx * r, uy * v + jy * r, False)

    def _drip(self, x, y, vx, vy, blood):
        if len(self.drips) < DRIP_MAX:
            self.drips.append(new_drip(x, y, vx, vy, self.rng, blood))

    def squirt(self, intensity):
        """受惊、挨打或摔落时，每个蛋按强度有机会往外喷一滴液体。"""
        if not self.show_eggs:
            return
        rng = self.rng
        intensity = clampf(intensity, 0.0, 1.0)
        for i, e in enumerate(self.eggs):
            if rng.random() >= lerp(0.07, 0.4, intensity):
                continue
            ax, ay = self.egg_attach(i)
            ux, uy = _unit(e[0] - ax, e[1] - ay)
            v = lerp(3.0, 7.0, rng.random() ** (1.5 - 0.6 * intensity))
            jx, jy = _rnv(rng)
            r = rng.random() * 4.0
            k = rng.random() ** lerp(1.4, 0.4, intensity)
            self._drip(e[0], e[1], (ux * v + jx * r) * k, (uy * v + jy * r) * k, False)

    def bleed(self, n):
        """被啃时从腹部溅出几滴暗色的血。"""
        b, rng = self.bug, self.rng
        for _ in range(n):
            rx, ry = _rnv(rng)
            r = rng.random()
            x, y = b.c1.x + rx * b.c1.rad * r, b.c1.y + ry * b.c1.rad * r
            self._drip(x, y, rx * 6.0 * r, ry * 6.0 * r - 7.0 * r, True)

    def _drips(self, HL):
        self.drips = step_drips(self.drips, self.bug.room_gravity, HL)
