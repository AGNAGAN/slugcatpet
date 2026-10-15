"""雨：每列的落点（被窗口挡住的列只落到窗口顶边）、强度缓变、风向漂移、雨丝与水花。"""

from __future__ import annotations
import math
import random

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap

from .._paths import assets_dir, bundled_assets_dir
from ..core.units import clampf

COL_W = 4.0  # 落点数组的列宽（逻辑 px）
I_MAX = 0.7  # 雨量满格对应的强度
DANGER = 0.35  # 露天开始被雨推的强度
RISE_SAFE = 0.35 / 160  # 危险线以下每 tick 涨多少
RISE_DANGER = (I_MAX - DANGER) / 1000  # 危险线以上每 tick 涨多少
FALL = I_MAX / 200  # 每 tick 落多少
KICK_SIDE = 20.0  # 判断旁边有无遮挡的距离
SHELTER_MARGIN = 24.0  # 躲雨落脚点离遮挡边缘的最小距离

DIR_RETARGET = 0.025  # 每 tick 换风向目标的概率
DIR_LERP = 0.01
DIR_STEP = 0.0125
SLANT_MAX = 0.22  # 风向 ±1 时雨丝的横移比
SLANT_BUCKETS = 9  # 雨丝贴图按斜度分档缓存

TILE = 256  # 雨丝贴图边长（逻辑 px）
# 雨丝是并排的一暗一亮两道细线，深浅背景上都看得见
RAIN_LIGHT = (235, 242, 255)
RAIN_DARK = (20, 26, 36)
# 远、近、雨幕三层：每张贴图的条数、长度范围、亮线峰值不透明度、每 tick 下落距离
LAYERS = (
    (110, (26.0, 44.0), 60, 22.0),
    (36, (52.0, 84.0), 95, 34.0),
    (240, (90.0, 170.0), 70, 46.0),
)
DIM_RGB = (19, 19, 21)  # 暴雨时露天处压暗到的颜色
DIM_FROM = 0.8  # 画面强度过这个值开始压暗
DIM_MAX = 0.6

SPLASH_ATLAS = "waterSprites"
SPLASH_FRAMES = ("90DegreeSplash", "TallSplash")  # 宽、高两种水花
SPLASH_ANCHOR_Y = (0.8, 0.9)  # 落点在贴图里的高度（自上而下）
SPLASH_PER_PX = 0.04  # 每逻辑 px 露天落点上的水花数
SPLASH_SCALE = (0.2, 0.38)  # 相对贴图原尺寸的缩放范围
SPLASH_OPACITY = 0.35
SPLASH_JITTER = 10.0
FOG_RGB = (175, 185, 198)  # 水花从雾色到白色
SPLASH_TINTS = 5
SPLASH_RETRY = 80  # 没有水花图集时隔多少 tick 再找


def inv_lerp(a, b, v):
    return clampf((v - a) / (b - a), 0.0, 1.0)


def column_share(vis):
    """有雨的列占比：三个均匀随机数的平均值超过 1 − 1.5·vis 的概率。"""
    x = 3.0 * (1.0 - 1.5 * vis)
    if x <= 0.0:
        return 1.0
    if x >= 3.0:
        return 0.0
    if x < 1.0:
        cdf = x**3 / 6.0
    elif x < 2.0:
        cdf = (-2.0 * x**3 + 9.0 * x**2 - 9.0 * x + 3.0) / 6.0
    else:
        cdf = 1.0 - (3.0 - x) ** 3 / 6.0
    return 1.0 - cdf


def layer_opacity(k, i):
    """第 k 层雨丝在强度 i 下的不透明度。"""
    vis = inv_lerp(0.0, 0.5, i)
    if k == 0:
        return vis * 0.85
    if k == 1:
        return inv_lerp(0.15, 1.0, vis)
    return column_share(vis)


def push_force(i):
    """露天时被雨推的力度 0~1。"""
    return inv_lerp(DANGER, I_MAX, i) ** 0.8


class Rain:
    def __init__(self, seed=0):
        self._rng = random.Random(0x7A1 ^ (int(seed or 0) * 2654435761 & 0xFFFFFFFF))
        self.intensity = 0.0
        self.target = 0.0
        self.direction = 0.0
        self._dir_to = 0.0
        self._scroll = [[0.0, 0.0] for _ in LAYERS]  # 每层 (x, y) 卷动量
        self._last_scroll = [[0.0, 0.0] for _ in LAYERS]
        self._WL = 0.0
        self._HL = 0.0
        self._rects = []
        self._reach = []
        self.runs = []  # 露天段 (x0, x1, y)：雨从顶上落到 y
        self.open_frac = 1.0  # 露天面积占全屏的比例
        self.splashes = []  # (露天段序号, x, 种类, 转角, x 缩放, y 缩放, 色档)
        self._tiles = {}
        self._splash_pm = None
        self._splash_wait = 0
        self._frame = None  # 定格的一帧：(画面强度, 斜度档, 各层偏移, 露天段, 水花)

    @property
    def active(self) -> bool:
        return self.intensity > 0.0

    @property
    def shows(self) -> bool:
        """屏上有没有雨可画。"""
        return self.intensity > 0.0 and bool(self.runs)

    def set_target(self, i):
        self.target = clampf(float(i), 0.0, I_MAX)

    def resize(self, WL, HL):
        if (WL, HL) != (self._WL, self._HL):
            self._WL, self._HL = WL, HL
            self._rebuild()

    def set_shelters(self, rects):
        """rects：挡雨窗口的逻辑坐标 (x0, y0, x1, y1)。"""
        rects = sorted(rects)
        if rects != self._rects:
            self._rects = rects
            self._rebuild()

    def _rebuild(self):
        n = max(1, math.ceil(self._WL / COL_W))
        HL = self._HL
        reach = [HL] * n
        for x0, y0, x1, y1 in self._rects:
            if y1 <= 0.0 or y0 >= HL or x1 <= 0.0 or x0 >= self._WL:
                continue
            top = max(y0, 0.0)
            for i in range(max(0, int(x0 // COL_W)), min(n, math.ceil(x1 / COL_W))):
                if top < reach[i]:
                    reach[i] = top
        self._reach = reach
        runs = []
        start = 0
        for i in range(1, n + 1):
            if i == n or reach[i] != reach[start]:
                if reach[start] > 0.0:
                    runs.append((start * COL_W, min(i * COL_W, self._WL), reach[start]))
                start = i
        self.runs = runs
        area = self._WL * HL
        self.open_frac = sum((x1 - x0) * y for x0, x1, y in runs) / area if area > 0 else 1.0

    def reach_at(self, x):
        """这一列的雨落到的 y。"""
        if not self._reach:
            return self._HL
        i = int(x // COL_W)
        return self._reach[min(max(i, 0), len(self._reach) - 1)]

    def exposed(self, x, y):
        return y < self.reach_at(x)

    def dangerous(self) -> bool:
        """雨正在或将要大到露天会被推。"""
        return self.intensity > 0.0 and max(self.target, self.intensity) >= DANGER

    def keeps_out(self, x, y) -> bool:
        """大雨时这里露天，猫不去。"""
        return self.dangerous() and self.exposed(x, y)

    def floor_spans(self, lo, hi, margin):
        """地面上有遮挡的 x 段，限在 [lo, hi] 内、两头各收 margin。"""
        out = []
        start = None
        HL = self._HL
        for i, r in enumerate(self._reach + [HL]):
            if r < HL:
                if start is None:
                    start = i
            elif start is not None:
                a, b = max(start * COL_W + margin, lo), min(i * COL_W - margin, hi)
                if a <= b:
                    out.append((a, b))
                start = None
        return out

    def nearest_shelter_x(self, x, lo, hi, margin):
        """离 x 最近的有遮挡的地面 x；没有返回 None。"""
        best = None
        for a, b in self.floor_spans(lo, hi, margin):
            p = min(max(x, a), b)
            if best is None or abs(p - x) < abs(best - x):
                best = p
        return best

    def kick(self, o, force, grounded, chunks=0, cap=None):
        """推一下露天的质点（着地向上乱踢、偏向有遮挡的一侧，空中往下砸），返回晕几 tick，没淋到返回 None。"""
        rng = self._rng
        r = getattr(o, "rad", 0.0)
        x, y = o.x + rng.uniform(-r, r), o.y + rng.uniform(-r, r)
        if not self.exposed(x, y):
            return None
        if grounded:
            bias = (self.reach_at(x + KICK_SIDE) <= y) - (self.reach_at(x - KICK_SIDE) <= y)
            a = math.radians(rng.uniform(-30.0, 30.0) + bias * 16.0)
            m = rng.random() * 9.0 * force / o.mass
            if cap is not None:
                m = min(m, cap)
            o.vx += math.sin(a) * m
            o.vy -= math.cos(a) * m
        else:
            m = rng.random() ** 5 * 16.5 * force / o.mass
            o.vy += m if cap is None else min(m, cap)
        if chunks and rng.random() ** 1.2 * 2.0 * chunks < force:
            return rng.randint(1, max(1, int(9.0 * force)))
        return 0

    def step(self):
        i, tgt = self.intensity, self.target
        if i < tgt:
            i = min(i + (RISE_SAFE if i < DANGER else RISE_DANGER), tgt)
        elif i > tgt:
            i = max(i - FALL, tgt)
        self.intensity = i
        rng = self._rng
        if rng.random() < DIR_RETARGET:
            self._dir_to = rng.uniform(-1.0, 1.0)
        d = self.direction + (self._dir_to - self.direction) * DIR_LERP
        d = min(d + DIR_STEP, self._dir_to) if d < self._dir_to else max(d - DIR_STEP, self._dir_to)
        self.direction = d
        slant = d * SLANT_MAX
        for k, (_, _, _, speed) in enumerate(LAYERS):
            s, last = self._scroll[k], self._last_scroll[k]
            last[0], last[1] = s[0], s[1]
            s[0] = (s[0] + speed * slant) % TILE
            s[1] = (s[1] + speed) % TILE
        self._step_splashes()

    def _step_splashes(self):
        """每 tick 在露天落点上随机摆一批水花。"""
        size = inv_lerp(0.0, 0.5, self.intensity) ** 2
        self.splashes = []
        if size < 0.05 or not self.runs:
            return
        rng = self._rng
        total = sum(x1 - x0 for x0, x1, _ in self.runs)
        tint = self.intensity / I_MAX * (SPLASH_TINTS - 1)
        for _ in range(int(total * SPLASH_PER_PX * (1.0 + push_force(self.intensity)))):
            pick = rng.random() * total
            for k, (x0, x1, _) in enumerate(self.runs):
                if pick < x1 - x0:
                    break
                pick -= x1 - x0
            x = x0 + pick + rng.uniform(-SPLASH_JITTER, SPLASH_JITTER)
            sy = size * rng.uniform(*SPLASH_SCALE)
            if rng.random() < 0.5:
                kind, rot, sx = 0, rng.uniform(-45.0, 45.0), (-sy if rng.random() < 0.5 else sy)
            else:
                kind, rot, sx = 1, rng.uniform(-25.0, 25.0), rng.uniform(-1.0, 1.0) * sy
            self.splashes.append((k, x, kind, rot, sx, sy, round(rng.random() * tint)))
        self.splashes.sort(key=lambda sp: sp[0])

    def _slant_bucket(self):
        b = round((self.direction + 1.0) * 0.5 * (SLANT_BUCKETS - 1))
        return min(max(b, 0), SLANT_BUCKETS - 1)

    def _tile(self, layer, bucket, scale):
        key = (layer, bucket, scale)
        pm = self._tiles.get(key)
        if pm is not None:
            return pm
        count, (len_lo, len_hi), alpha = LAYERS[layer][:3]
        slant = (bucket / (SLANT_BUCKETS - 1) * 2.0 - 1.0) * SLANT_MAX
        n = math.hypot(slant, 1.0)
        ux, uy = slant / n, 1.0 / n
        side = 1.0 / scale  # 暗线贴在亮线左侧一个设备像素
        rng = random.Random(layer * 131 + 7)
        pm = QPixmap(round(TILE * scale), round(TILE * scale))
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(scale, scale)
        for _ in range(count):
            x, y = rng.uniform(0, TILE), rng.uniform(0, TILE)
            length = rng.uniform(len_lo, len_hi)
            a = alpha * rng.uniform(0.6, 1.0)
            dx, dy = ux * length, uy * length
            for ox in (-TILE, 0, TILE):
                for oy in (-TILE, 0, TILE):
                    x0, y0 = x + ox, y + oy
                    if x0 + dx < -2 or x0 > TILE + 2 or y0 + dy < -2 or y0 > TILE + 2:
                        continue
                    for off, rgb, k in ((-side, RAIN_DARK, 0.55), (0.0, RAIN_LIGHT, 1.0)):
                        g = QLinearGradient(x0, y0, x0 + dx, y0 + dy)
                        g.setColorAt(0.0, QColor(*rgb, 0))
                        g.setColorAt(0.75, QColor(*rgb, round(a * k)))
                        g.setColorAt(1.0, QColor(*rgb, round(a * k * 0.6)))
                        pen = QPen(QBrush(g), 1.0 / scale)
                        p.setPen(pen)
                        p.drawLine(QLineF(x0 + off, y0, x0 + off + dx, y0 + dy))
        p.end()
        pm.setDevicePixelRatio(scale)
        if len(self._tiles) > 4 * SLANT_BUCKETS:
            self._tiles.clear()
        self._tiles[key] = pm
        return pm

    def _splashes(self):
        """各色档的两种水花贴图；没有图集时返回 None。"""
        if self._splash_pm is None:
            if self._splash_wait > 0:
                self._splash_wait -= 1
                return None
            self._splash_wait = SPLASH_RETRY
            for d in (assets_dir(), bundled_assets_dir()):
                if (d / SPLASH_ATLAS).is_file() and (d / f"{SPLASH_ATLAS}.png").is_file():
                    from ..rendering.atlas import Atlas

                    try:
                        at = Atlas(SPLASH_ATLAS, d)
                    except (OSError, ValueError, KeyError):
                        continue
                    self._splash_pm = [
                        [at.sprite(f, self._tint(t)) for f in SPLASH_FRAMES] for t in range(SPLASH_TINTS)
                    ]
                    break
        return self._splash_pm

    @staticmethod
    def _tint(level):
        f = level / (SPLASH_TINTS - 1)
        return QColor(*(round(a + (255 - a) * f) for a in FOG_RGB))

    def snapshot(self, ts):
        """定格当前画面；两次定格之间重画都画同一帧。"""
        if not self.shows:
            self._frame = None
            return
        offs = []
        for s, last in zip(self._scroll, self._last_scroll):
            ox = last[0] + ((s[0] - last[0] + TILE / 2) % TILE - TILE / 2) * ts
            oy = last[1] + ((s[1] - last[1] + TILE / 2) % TILE - TILE / 2) * ts
            offs.append((ox, oy))
        self._frame = (self.intensity, self._slant_bucket(), offs, list(self.runs), self.splashes)

    def paint_rect(self, scale, margin=0.0) -> QRect:
        """本帧雨覆盖的范围（设备 px）。"""
        if not self.active or not self.runs:
            return QRect()
        x0 = min(r[0] for r in self.runs) - margin
        x1 = max(r[1] for r in self.runs) + margin
        y1 = max(r[2] for r in self.runs) + margin + 2.0
        return QRectF(x0 * scale, -margin * scale, (x1 - x0) * scale, (y1 + margin) * scale).toAlignedRect()

    def draw(self, p, scale):
        """画定格的那一帧。"""
        if self._frame is None:
            return
        i, bucket, offs, runs, splashes = self._frame
        p.save()
        dim = round(255 * DIM_MAX * inv_lerp(DIM_FROM, 1.0, inv_lerp(0.0, 0.5, i)))
        if dim > 0:
            for x0, x1, y in runs:
                p.fillRect(QRectF(x0, 0.0, x1 - x0, y), QColor(*DIM_RGB, dim))
        for k, (ox, oy) in enumerate(offs):
            op = layer_opacity(k, i)
            if op <= 0.0:
                continue
            pm = self._tile(k, bucket, scale)
            p.setOpacity(op)
            for x0, x1, y in runs:
                p.drawTiledPixmap(QRectF(x0, 0.0, x1 - x0, y), pm, QPointF((x0 - ox) % TILE, (-oy) % TILE))
        pms = self._splashes() if splashes else None
        if pms:
            p.setOpacity(SPLASH_OPACITY)
            clip = -1
            for k, x, kind, rot, sx, sy, tint in splashes:
                y = runs[k][2]
                if k != clip:
                    p.setClipRect(QRectF(0.0, y - 1e4, self._WL, 1e4))  # 只画到落点以上
                    clip = k
                pm = pms[tint][kind]
                w, h = pm.width(), pm.height()
                p.save()
                p.translate(x, y)
                p.rotate(rot)
                p.scale(sx, sy)
                p.drawPixmap(QPointF(-w * 0.5, -h * SPLASH_ANCHOR_Y[kind]), pm)
                p.restore()
        p.restore()
