"""LizardGraphics 的绘制部分（绿 / 粉）：脊线与颜色函数、精灵助手 Canvas、draw_lizard。

在房间坐标（y↑）里算几何，写窗口坐标（y_win = HL - y）。精灵语义同 Futile FSprite：
rotation 度数视觉顺时针为正，anchorY 从底边起算，scale 乘贴图原始（sourceSize）尺寸。
几何全用 float 计算（不建 V2）。身体、四个圆、尾巴并成一次 drawPath；尾巴渐变只在
变色的那几节叠一层同形的色块（没有逐顶点插值，每节取其三角形顶点色的平均）。
贴图精灵关抗锯齿画（开了会慢六倍），路径填充开抗锯齿。
没有房间调色板：blackColor 固定为原版 palette0 的 blackColor。
每只蜥蜴的绘制状态放在这里的 WeakKeyDictionary 里，不挂在 gfx 上。
"""

from __future__ import annotations

import math
import random
import weakref

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTransform,
)

from .physics import Animation
from .rw import V2, clamp, clamp01, color_lerp, inverse_lerp, lerp

# 原版 palette0.png 在 (2, 7) 的像素：房间调色板的 blackColor
BLACK_COLOR = (12 / 255.0, 8 / 255.0, 14 / 255.0)
CAMO_ALPHA = 0.12
WHITE = (1.0, 1.0, 1.0)

_NoPen = Qt.PenStyle.NoPen
_Winding = Qt.FillRule.WindingFill
_AA = QPainter.RenderHint.Antialiasing
_SMOOTH = QPainter.RenderHint.SmoothPixmapTransform
# 头抖动：发现猎物 / 威胁；身体抖动：发现威胁
_SPOT_ANIMS = (
    Animation.PreySpotted,
    Animation.PreyReSpotted,
    Animation.ThreatSpotted,
    Animation.ThreatReSpotted,
)
_THREAT_ANIMS = (Animation.ThreatSpotted, Animation.ThreatReSpotted)
_rng = random.Random()  # 绘制里的抖动，不动模拟的随机序列
_DEG = 180.0 / math.pi
ARC = 360.0  # 圆与四边形的朝向要一致，否则并成一块时绕数相互抵消


class SpineData:
    """LizardSpineData：pos 为脊线点，outer 为按深度旋转外推的外缘点，dir / perp 为单位向量。"""

    __slots__ = ("f", "x", "y", "ox", "oy", "dx", "dy", "px", "py", "depth_rotation", "rad")

    def __init__(self, f, x, y, ox, oy, dx, dy, px, py, depth_rotation, rad):
        self.f = f
        self.x = x
        self.y = y
        self.ox = ox
        self.oy = oy
        self.dx = dx
        self.dy = dy
        self.px = px
        self.py = py
        self.depth_rotation = depth_rotation
        self.rad = rad


# 颜色


def _q(v: float) -> float:
    """量化到 64 级：眨眼渐变的头色不会把贴图缓存撑爆。"""
    return round(v * 63.0) / 63.0


def quantize(c):
    """颜色量化到 64 级（动态颜色用，避免贴图缓存被撑爆）。"""
    return (_q(c[0]), _q(c[1]), _q(c[2]))


def head_color(g, ts: float):
    """HeadColor：黑色（HeadColor1）与 effectColor（HeadColor2）之间随眨动明暗。"""
    if g.white_flicker > 0 and (g.white_flicker > 15 or g.every_second_draw):
        return WHITE
    a = 1.0 - (0.5 + 0.5 * math.sin(lerp(g.last_blink, g.blink, ts) * 2.0 * math.pi)) ** (
        1.5 + g.lizard.ai.excitement * 1.5
    )
    if g.head_color_setter != 0.0:
        a = lerp(a, 1.0 if g.head_color_setter > 0.0 else 0.0, abs(g.head_color_setter))
    if g.flicker > 10:
        a = g.flicker_color
    a = lerp(
        a,
        max(0.0, lerp(g.last_voice_visualization, g.voice_visualization, ts)) ** 0.75,
        lerp(g.last_voice_visualization_intensity, g.voice_visualization_intensity, ts),
    )
    if g.lizard.lizard_params.key == "white":
        amt = g.camouflaged
        c1 = color_lerp(WHITE, g.white_camo_color, amt)
        c = color_lerp(c1, color_lerp(BLACK_COLOR, g.white_camo_color, amt), a)
    else:
        c = color_lerp(BLACK_COLOR, g.effect_color, a)
    return (_q(c[0]), _q(c[1]), _q(c[2]))


def dynamic_body_color(g, f: float):
    """DynamicBodyColor：白蜥蜴是白色混向伪装色，其余是 blackColor。"""
    if g.lizard.lizard_params.key == "white":
        return quantize(color_lerp(WHITE, g.white_camo_color, g.camouflaged))
    return BLACK_COLOR


def white_alpha(g) -> float:
    """白蜥蜴的伪装在桌面上表现为整体变透明：现形（伪装量最低 0.15）时不透明，完全伪装时 CAMO_ALPHA。"""
    if g.lizard.lizard_params.key != "white":
        return 1.0
    return lerp(1.0, CAMO_ALPHA, inverse_lerp(0.15, 1.0, g.camouflaged))


def body_color(g, f: float):
    """BodyColor：身体黑；尾巴按 tailColor 从 tailColorationStart 起渐变向 effectColor。"""
    if g.lizard.lizard_params.key == "white":
        return dynamic_body_color(g, f)
    frac = g.body_length / g.body_and_tail_length
    tail_color = g.i_vars.tail_color
    if f < frac or tail_color == 0.0:
        return BLACK_COLOR
    p = g.lizard.lizard_params
    value = inverse_lerp(frac, 1.0, f)
    f2 = clamp(inverse_lerp(p.tail_coloration_start, 0.95, value), 0.0, 1.0)
    f2 = (f2**p.tail_coloration_exponent) * tail_color
    return color_lerp(BLACK_COLOR, g.effect_color, f2)


# 每只蜥蜴的绘制状态


class _State:
    __slots__ = ("applied", "seg_fills", "frames")

    def __init__(self):
        self.applied = False
        self.seg_fills = None
        self.frames: dict = {}


_STATES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _state(g) -> _State:
    st = _STATES.get(g)
    if st is None:
        st = _STATES[g] = _State()
    return st


class _Frame:
    """同一 tick、同一 ts 内共用的几何：插值后的各点、身体四点、脊线缓存。"""

    __slots__ = (
        "num",
        "tl",
        "fat",
        "tfat",
        "head_rad",
        "depth_lerp",
        "stamp",
        "depth",
        "hx",
        "hy",
        "dx",
        "dy",
        "tx",
        "ty",
        "sr",
        "rad",
        "bp",
        "sp",
    )

    def __init__(self, g, ts: float, stamp, depth):
        self.stamp = stamp
        self.depth = depth
        conns = g.lizard.body_chunk_connections
        self.num = conns[0].distance + conns[1].distance
        self.tl = g.tail_length
        self.fat = g.i_vars.fatness
        self.tfat = g.i_vars.tail_fatness
        self.head_rad = g.head.rad
        self.depth_lerp = lerp(g.last_depth_rotation, g.depth_rotation, ts)
        dp = g.draw_positions
        h = g.head
        self.hx = h.last_pos.x + (h.pos.x - h.last_pos.x) * ts
        self.hy = h.last_pos.y + (h.pos.y - h.last_pos.y) * ts
        self.dx = [dp[i][1].x + (dp[i][0].x - dp[i][1].x) * ts for i in range(3)]
        self.dy = [dp[i][1].y + (dp[i][0].y - dp[i][1].y) * ts for i in range(3)]
        tail = g.tail
        self.tx = [s.last_pos.x + (s.pos.x - s.last_pos.x) * ts for s in tail]
        self.ty = [s.last_pos.y + (s.pos.y - s.last_pos.y) * ts for s in tail]
        self.sr = [s.stretched_rad for s in tail]
        self.rad = [g.body_chunk_display_rad(i) for i in range(3)]
        self.sp = {}
        dx, dy, tx, ty = self.dx, self.dy, self.tx, self.ty
        bp = []
        for p in range(4):
            num = 1 if p < 2 else 2
            cx, cy = dx[num], dy[num]
            if p % 2 == 1:
                bp.append((cx, cy))
                continue
            if num == 1:
                nx, ny = dx[2], dy[2]
            else:
                nx, ny = tx[0], ty[0]
            ax, ay = cx - dx[num - 1], cy - dy[num - 1]
            ux, uy = _slerp_dir(ax, ay, nx - cx, ny - cy, 0.35)
            k = -0.5 * math.hypot(ax, ay)
            bp.append((cx + ux * k, cy + uy * k))
        self.bp = bp


def _slerp_dir(ax, ay, bx, by, t):
    """Vector3.Slerp(a, b, t).normalized，作用在 z=0 的二维向量上。"""
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    if la < 1e-5 or lb < 1e-5:
        rx, ry = ax + (bx - ax) * t, ay + (by - ay) * t
    else:
        d = (ax * bx + ay * by) / (la * lb)
        if d > 1.0 - 1e-5:
            rx, ry = ax + (bx - ax) * t, ay + (by - ay) * t
        else:
            if d < -1.0 + 1e-5:
                ang, s = math.pi * t, 1.0
            else:
                ang = math.acos(d) * t
                s = 1.0 if ax * by - ay * bx >= 0.0 else -1.0
            c, sn = math.cos(ang), math.sin(s * ang)
            nx, ny = ax / la, ay / la
            rx, ry = c * nx - sn * ny, sn * nx + c * ny
    m = math.hypot(rx, ry)
    return (rx / m, ry / m) if m > 1e-5 else (0.0, 0.0)


def _frame(g, ts: float) -> _Frame:
    dp = g.draw_positions
    tail = g.tail
    stamp = (dp[0][0], dp[1][0], dp[2][0], g.head.pos, tail[0].pos, tail[-1].pos)
    depth = (g.depth_rotation, g.last_depth_rotation)
    frames = _state(g).frames
    fr = frames.get(ts)
    if fr is not None and fr.depth == depth and all(x is y for x, y in zip(fr.stamp, stamp)):
        return fr
    if len(frames) > 16:
        frames.clear()
    fr = frames[ts] = _Frame(g, ts, stamp, depth)
    return fr


def body_position(g, p: int, ts: float) -> V2:
    """BodyPosition。"""
    if p > 3:
        return V2(100.0, 100.0)
    x, y = _frame(g, ts).bp[p]
    return V2(x, y)


def frame_at(g, ts: float) -> _Frame:
    """同一 tick 内共用的几何（update 用 ts=1）。"""
    return _frame(g, ts)


def spine_in(g, fr: _Frame, s: float, ts: float) -> SpineData:
    """在已取得的 frame 上算一个脊线点（不查缓存）。"""
    return _spine(g, fr, s, ts)


def spine_position(g, s: float, ts: float) -> SpineData:
    """SpinePosition：s∈[0,1] 沿身体加尾巴的位置、方向、垂线与按深度旋转外推的外缘点。结果被缓存共享，不要改。"""
    fr = _frame(g, ts)
    r = fr.sp.get(s)
    if r is None:
        r = fr.sp[s] = _spine(g, fr, s, ts)
    return r


def _spine(g, fr: _Frame, s: float, ts: float) -> SpineData:
    num, tl, fat, tfat = fr.num, fr.tl, fr.fat, fr.tfat
    bp = fr.bp
    tx, ty = fr.tx, fr.ty
    floor = math.floor
    split = num / (num + tl)
    if s < split:
        num2 = (s - 0.0) / (split - 0.0)
        num2 = 0.0 if num2 < 0.0 else (1.0 if num2 > 1.0 else num2)
        n4 = num2 * 4.0
        num3 = floor(n4 - 1.0)
        num4 = floor(n4)
        if num3 < 0:
            vx, vy = (bp[0][0] + fr.hx) * 0.5, (bp[0][1] + fr.hy) * 0.5
            a = fr.head_rad
        else:
            vx, vy = bp[num3] if num3 < 4 else (100.0, 100.0)
            a = fr.rad[1 if num3 < 2 else 2] * fat
        if num4 + 1 >= 4:
            v2x, v2y = tx[0], ty[0]
        else:
            v2x, v2y = bp[num4 + 1]
        v3x, v3y = bp[num4] if num4 < 4 else (100.0, 100.0)
        b = fr.rad[1 if num4 < 2 else 2]
        lo, hi = num3 + 1, num4 + 1
        t = 0.0 if lo == hi else (n4 - lo) / (hi - lo)
    else:
        n = len(tx)
        num5 = (s - split) / (1.0 - split) if split != 1.0 else 0.0
        num5 = 0.0 if num5 < 0.0 else (1.0 if num5 > 1.0 else num5)
        num6 = floor(num5 * n - 1.0)
        num7 = min(floor(num5 * n), n - 1)
        if num6 < 0:
            vx, vy = bp[3]
            a = fr.rad[2] * fat
        else:
            vx, vy = tx[num6], ty[num6]
            a = fr.sr[num6] * fat * tfat
        k = min(num7 + 1, n - 1)
        v2x, v2y = tx[k], ty[k]
        v3x, v3y = tx[num7], ty[num7]
        b = fr.sr[num7]
        lo, hi = num6 + 1, num7 + 1
        t = 0.0 if lo == hi else (num5 * n - lo) / (hi - lo)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    ex = (v3x - vx) + ((v2x - v3x) - (v3x - vx)) * t
    ey = (v3y - vy) + ((v2y - v3y) - (v3y - vy)) * t
    m = math.hypot(ex, ey)
    if m > 1e-5:
        dx, dy = ex / m, ey / m
    else:
        ex, ey = tx[-1] - tx[-2], ty[-1] - ty[-2]
        m = math.hypot(ex, ey)
        dx, dy = (ex / m, ey / m) if m > 1e-5 else (0.0, 0.0)
    px, py = -dy, dx
    rad = a + (b - a) * t
    f = fr.depth_lerp
    f = (abs(f) ** (1.2 + (0.3 - 1.2) * (s**0.5))) * (1.0 if f >= 0.0 else -1.0)
    x, y = vx + (v3x - vx) * t, vy + (v3y - vy) * t
    return SpineData(s, x, y, x + px * (f * rad), y + py * (f * rad), dx, dy, px, py, f, rad)


# 精灵助手


_PM_CACHES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_PM_CAP = 3000


class Canvas:
    """把 Futile 语义的精灵画进 p。p 的当前变换视为基础变换（逻辑坐标，y↓）。"""

    def __init__(self, p: QPainter, atlas, HL: float, alpha: float = 1.0):
        self.p = p
        self.atlas = atlas
        self.HL = HL
        self.alpha = alpha
        self.base = p.transform()
        self._identity = self.base.isIdentity()
        self._aa = bool(p.renderHints() & _AA)
        self._op = p.opacity()
        self._on_base = True
        cache = _PM_CACHES.get(atlas)
        if cache is None:
            cache = _PM_CACHES[atlas] = {}
        elif len(cache) > _PM_CAP:
            cache.clear()
        self._cache = cache

    def source_height(self, name: str) -> int:
        return self.atlas.source_size("base", name)[1]

    def _pixmap(self, name: str, col):
        """裁掉透明边的着色贴图，连同它在 sourceSize 画布里的偏移和画布尺寸。"""
        key = (name, col)
        e = self._cache.get(key)
        if e is None:
            qc = QColor(int(col[0] * 255 + 0.5), int(col[1] * 255 + 0.5), int(col[2] * 255 + 0.5))
            at = self.atlas.get("base")
            fr = at.frames[at._key(name)]
            off = fr["spriteSourceSize"] if fr.get("trimmed") else {"x": 0, "y": 0}
            sw, sh = self.atlas.source_size("base", name)
            pm = self.atlas.sprite("base", name, qc, padded=False)
            e = self._cache[key] = (pm, off["x"], off["y"], sw, sh)
        return e

    def _use(self, aa: bool, alpha: float) -> None:
        p = self.p
        if aa != self._aa:
            p.setRenderHint(_AA, aa)
            self._aa = aa
        a = alpha * self.alpha
        if a != self._op:
            p.setOpacity(a)
            self._op = a

    def _to_base(self) -> None:
        if not self._on_base:
            self.p.setTransform(self.base)
            self._on_base = True

    def _xf(self, x, y, rot, sx, sy, w, h, ax, ay) -> None:
        r = rot / _DEG
        c, s = math.cos(r), math.sin(r)
        t = QTransform(
            c * sx,
            s * sx,
            -s * sy,
            c * sy,
            x - c * sx * ax * w + s * sy * (1.0 - ay) * h,
            self.HL - y - s * sx * ax * w - c * sy * (1.0 - ay) * h,
        )
        self.p.setTransform(t if self._identity else t * self.base)
        self._on_base = False

    def sprite(self, name, x, y, rot, sx, sy, col, alpha=1.0, ax=0.5, ay=0.5):
        pm, ox, oy, w, h = self._pixmap(name, col)
        self._use(False, alpha)
        self._xf(x, y, rot, sx, sy, w, h, ax, ay)
        self.p.drawPixmap(ox, oy, pm)

    def block(self, x, y, rot, w, h, col, alpha=1.0):
        """pixel 精灵缩放成 w×h 的色块。"""
        key = ("#block", col)
        pm = self._cache.get(key)
        if pm is None:
            pm = self._cache[key] = QPixmap(1, 1)
            pm.fill(QColor(int(col[0] * 255 + 0.5), int(col[1] * 255 + 0.5), int(col[2] * 255 + 0.5)))
        self._use(False, alpha)
        self._xf(x, y, rot, w, h, 1.0, 1.0, 0.5, 0.5)
        self.p.drawPixmap(0, 0, pm)

    def fill(self, path: QPainterPath, col, alpha=1.0) -> None:
        self._use(True, alpha)
        self._to_base()
        self.p.setPen(_NoPen)
        self.p.setBrush(
            QBrush(QColor(int(col[0] * 255 + 0.5), int(col[1] * 255 + 0.5), int(col[2] * 255 + 0.5)))
        )
        self.p.drawPath(path)

    def fill_gradient(self, path: QPainterPath, x0, y0, x1, y1, c0, c1, alpha=1.0) -> None:
        """沿 (x0,y0)→(x1,y1)（房间坐标）从 c0 渐变到 c1 的填充。"""
        self._use(True, alpha)
        self._to_base()
        grad = QLinearGradient(x0, self.HL - y0, x1, self.HL - y1)
        grad.setColorAt(0.0, _qc(c0))
        grad.setColorAt(1.0, _qc(c1))
        self.p.setPen(_NoPen)
        self.p.setBrush(QBrush(grad))
        self.p.drawPath(path)

    def circle(self, x, y, r, col, alpha=1.0):
        path = QPainterPath()
        path.addEllipse(x - r, self.HL - y - r, 2.0 * r, 2.0 * r)
        self.fill(path, col, alpha)


def _qc(col, a: float = 1.0) -> QColor:
    return QColor(
        int(col[0] * 255 + 0.5), int(col[1] * 255 + 0.5), int(col[2] * 255 + 0.5), int(clamp01(a) * 255 + 0.5)
    )


# 绘制


def _apply_palette(g, st: _State) -> None:
    """ApplyPalette 里与帧无关的部分：尾巴各节的叠色、各装饰件的静态颜色。"""
    n = len(g.tail)
    fills = None
    if g.i_vars.tail_color > 0.0:
        nv = (n - 1) * 4 + 3
        frac = g.body_length / g.body_and_tail_length
        vc = [body_color(g, lerp(frac, 1.0, (j // 2) * 2.0 / (nv - 1))) for j in range(nv)]

        def qc(c):
            return QColor(int(c[0] * 255 + 0.5), int(c[1] * 255 + 0.5), int(c[2] * 255 + 0.5))

        fills = []
        for m in range(n):
            c0, c1 = vc[4 * m], vc[4 * m + 2]
            if max(max(c0[k], c1[k]) - BLACK_COLOR[k] for k in range(3)) < 2.0 / 255.0:
                fills.append(None)
            else:
                fills.append((qc(c0), qc(c1)))
    st.seg_fills = fills
    for c in g.cosmetics:
        c.apply_palette()
    st.applied = True


def draw_lizard(p: QPainter, gfx, ts: float, alpha: float, atlas, HL: float) -> None:
    """按原版精灵层次画一只蜥蜴。p 在窗口逻辑坐标（y↓），ts 是 tick 间插值。"""
    g = gfx
    st = _state(g)
    if not st.applied:
        _apply_palette(g, st)
    ts = clamp(ts, 0.0, 1.0)
    L = g.lizard
    prm = L.lizard_params
    iv = g.i_vars
    fr = _frame(g, ts)
    old_hints = p.renderHints()
    old_op = p.opacity()
    p.setRenderHint(_SMOOTH, True)
    cv = Canvas(p, atlas, HL, alpha * white_alpha(g))
    eff = g.effect_color
    black = BLACK_COLOR
    cyan = prm.key == "cyan"
    white = prm.key == "white"
    body = dynamic_body_color(g, 0.0)

    num_h = lerp(g.last_head_depth_rotation, g.head_depth_rotation, ts)
    jaw = lerp(L.last_jaw_open, L.jaw_open, ts)
    if L.jaw_ready_for_bite and L.consious:
        jaw += _rng.random() * 0.2
    jaw = lerp(
        jaw,
        lerp(g.last_voice_visualization, g.voice_visualization, ts) + 0.2,
        lerp(g.last_voice_visualization_intensity, g.voice_visualization_intensity, ts) * 0.8,
    )
    jaw = clamp(jaw, 0.0, 1.0)

    # 身体：四段四边形加四个圆，和尾巴并成一块路径
    path = QPainterPath()
    path.setFillRule(_Winding)
    dxs, dys = fr.dx, fr.dy
    ax = dxs[0] + (fr.hx - dxs[0]) * 0.2
    ay = dys[0] + (fr.hy - dys[0]) * 0.2
    breath = (
        (math.sin(lerp(g.last_breath, g.breath, ts) * math.pi * 2.0) + 1.0)
        * 0.5
        * ((1.0 - L.ai.run_speed) ** 2)
    )
    prev_r = 5.0
    disp = fr.rad
    threat = L.animation in _THREAT_ANIMS
    for j in range(4):
        num5 = 1 if j < 2 else 2
        vx, vy = fr.bp[j]
        if threat:
            a = _rng.random() * 360.0 / _DEG
            k = _rng.random() * 2.0
            vx += math.sin(a) * k
            vy += math.cos(a) * k
        r = disp[num5]
        if j % 2 == 0:
            r = (r + disp[num5 - 1]) / 2.0
        r *= 1.0 + breath * (3 - j) * 0.1 * (0.5 if j == 0 else 1.0)
        r *= iv.fatness
        nx, ny = ax - vx, ay - vy
        m = math.hypot(nx, ny)
        if m > 1e-5:
            nx, ny = nx / m, ny / m
        else:
            nx = ny = 0.0
        qx, qy = -ny, nx
        # v0 = a - perp*prev, v1 = a + perp*prev（vec + nrm*d 即 a），v3 = vec + perp*r，v2 = vec - perp*r
        path.moveTo(ax - qx * prev_r, HL - (ay - qy * prev_r))
        path.lineTo(ax + qx * prev_r, HL - (ay + qy * prev_r))
        path.lineTo(vx + qx * r, HL - (vy + qy * r))
        path.lineTo(vx - qx * r, HL - (vy - qy * r))
        path.closeSubpath()
        path.moveTo(vx + r, HL - vy)
        path.arcTo(vx - r, HL - vy - r, 2.0 * r, 2.0 * r, 0.0, ARC)
        path.closeSubpath()
        prev_r = r
        ax, ay = vx, vy

    # 尾巴：三角带的外轮廓（偶数顶点一侧，奇数顶点另一侧）
    n = len(g.tail)
    fat = iv.fatness * iv.tail_fatness
    xs: list = []
    ys: list = []
    ax, ay = dxs[2], dys[2]
    prev_r = disp[2] * iv.fatness
    sr, tx, ty = fr.sr, fr.tx, fr.ty
    for i in range(n):
        vx, vy = tx[i], ty[i]
        nx, ny = vx - ax, vy - ay
        d = math.hypot(nx, ny)
        if d > 1e-5:
            nx, ny = nx / d, ny / d
        else:
            nx = ny = 0.0
        qx, qy = -ny, nx
        k = d / 5.0
        w = (prev_r + sr[i]) * 0.5 * fat
        xs.append(ax - qx * w + nx * k)
        ys.append(ay - qy * w + ny * k)
        xs.append(ax + qx * w + nx * k)
        ys.append(ay + qy * w + ny * k)
        if i < n - 1:
            w2 = sr[i] * fat
            xs.append(vx - qx * w2 - nx * k)
            ys.append(vy - qy * w2 - ny * k)
            xs.append(vx + qx * w2 - nx * k)
            ys.append(vy + qy * w2 - ny * k)
        else:
            xs.append(vx)
            ys.append(vy)
        prev_r = sr[i] * fat
        ax, ay = vx, vy
    nv = len(xs)
    path.moveTo(xs[0], HL - ys[0])
    for i in range(2, nv, 2):
        path.lineTo(xs[i], HL - ys[i])
    for i in range(nv - 2 if (nv - 1) % 2 == 0 else nv - 1, 0, -2):
        path.lineTo(xs[i], HL - ys[i])
    path.closeSubpath()

    # 四肢：数据先算好，图层顺序见下
    dep = abs(lerp(g.last_depth_rotation, g.depth_rotation, ts))
    limb_draw = []
    for i, limb in enumerate(g.limbs):
        lp, ll = limb.pos, limb.last_pos
        lx, ly = ll.x + (lp.x - ll.x) * ts, ll.y + (lp.y - ll.y) * ts
        ci = 0 if i < 2 else 2
        cx, cy = dxs[ci], dys[ci]
        if i < 2:
            cx += (dxs[1] - cx) * 0.2
            cy += (dys[1] - cy) * 0.2
        val = int(math.hypot(lx - cx, ly - cy) / (4.0 * prm.limb_size)) + 1
        val = max(1, min(9, val))
        val += 9 * (2 - int(clamp(abs(limb.flip) * 3.0, 0.0, 2.0)))
        if i >= 2:
            val += 27
        rot = math.degrees(math.atan2(lx - cx, ly - cy)) - 90.0
        sy = (1.0 if limb.flip >= 0.0 else -1.0) * prm.limb_thickness
        suffix = f"0{val}" if val < 10 else f"{val}"
        col_alpha = lerp(1.0, 0.3, dep) if i % 2 == 0 else 1.0
        limb_draw.append((lx, ly, rot, sy, suffix, col_alpha))

    limb_color_alpha = math.sin(g.camouflaged * math.pi) * 0.3 if white else 0.0

    def draw_limb(i):
        lx, ly, rot, sy, suffix, col_alpha = limb_draw[i]
        cv.sprite(f"LizardArm_{suffix}", lx, ly, rot, 1.0, sy, body)
        if white:
            cv.sprite(f"LizardArmColor_{suffix}", lx, ly, rot, 1.0, sy, black, limb_color_alpha)
        elif not cyan:
            cv.sprite(f"LizardArmColor_{suffix}", lx, ly, rot, 1.0, sy, eff, col_alpha)

    # 图层顺序同 AddToContainer：偶数肢 → 身体与尾 → 奇数肢 → 头后装饰件 → 头 → 前景装饰件
    draw_limb(0)
    draw_limb(2)
    cv.fill(path, body)
    fills = st.seg_fills
    if fills is not None:
        pp = cv.p
        for m in range(n):
            f = fills[m]
            if f is None:
                continue
            b = 4 * m
            seg = QPainterPath()
            if m < n - 1:
                order = (b, b + 2, b + 4, b + 5, b + 3, b + 1)
                ex, ey = (xs[b + 2] + xs[b + 3]) * 0.5, (ys[b + 2] + ys[b + 3]) * 0.5
            else:
                order = (b, b + 2, b + 1)
                ex, ey = xs[b + 2], ys[b + 2]
            seg.moveTo(xs[order[0]], HL - ys[order[0]])
            for i in order[1:]:
                seg.lineTo(xs[i], HL - ys[i])
            seg.closeSubpath()
            grad = QLinearGradient((xs[b] + xs[b + 1]) * 0.5, HL - (ys[b] + ys[b + 1]) * 0.5, ex, HL - ey)
            grad.setColorAt(0.0, f[0])
            grad.setColorAt(1.0, f[1])
            br = QBrush(grad)
            pp.setBrush(br)
            pp.setPen(QPen(br, 0.8))
            pp.drawPath(seg)
        pp.setPen(_NoPen)
    draw_limb(1)
    draw_limb(3)

    for c in g.cosmetics:
        if c.sprites_overlap == "BehindHead":
            c.draw(cv, ts)

    _draw_head(cv, g, fr, ts, num_h, jaw)

    for c in g.cosmetics:
        if c.sprites_overlap == "InFront":
            c.draw(cv, ts)

    if g.flicker > 10:
        g.flicker_color = _rng.random()
    if _rng.random() > 0.025:
        g.every_second_draw = not g.every_second_draw
    p.setTransform(cv.base)
    p.setOpacity(old_op)
    p.setRenderHints(old_hints)


def _draw_head(cv: Canvas, g, fr: _Frame, ts: float, num_h: float, jaw: float) -> None:
    L = g.lizard
    prm = L.lizard_params
    d0x, d0y = fr.dx[0], fr.dy[0]
    hx, hy = fr.hx, fr.hy
    px, py = hx + (d0x - hx) * 0.2, hy + (d0y - hy) * 0.2
    if L.consious:
        if L.bubble > 0:
            a = _rng.random() * 360.0 / _DEG
            k = 2.0 * g.bubble_intensity
            px += math.sin(a) * k
            py += math.cos(a) * k
        if g.white_flicker > 0:
            a = _rng.random() * 360.0 / _DEG
            k = _rng.random() * 2.0
            px += math.sin(a) * k
            py += math.cos(a) * k
        if L.animation in _SPOT_ANIMS:
            a = _rng.random() * 360.0 / _DEG
            k = _rng.random() * (1.0 + 2.0 * lerp(g.last_voice_visualization, g.voice_visualization, ts))
            px += math.sin(a) * k
            py += math.cos(a) * k
    rot0 = math.degrees(math.atan2(hx - d0x, hy - d0y))
    qx, qy = d0x - hx, d0y - hy
    m = math.hypot(qx, qy)
    if m > 1e-5:
        qx, qy = qx / m, qy / m
    else:
        qx = qy = 0.0
    nx, ny = -qy, qx  # perpendicular
    m = math.hypot(nx, ny)
    if m > 1e-5:
        nx, ny = nx / m, ny / m
    lf = prm.jaw_open_lower_jaw_fac
    apart = prm.jaw_open_move_jaws_apart
    ang = prm.jaw_open_angle
    sx = (1.0 if num_h >= 0.0 else -1.0) * prm.head_size * g.i_vars.head_size
    sy = prm.head_size * g.i_vars.head_size
    k = 3 - int(abs(num_h) * 3.9)
    hg = prm.head_graphics
    ay = 0.55 if prm.key == "green" else 0.7
    hc = head_color(g, ts)
    black = BLACK_COLOR
    up = jaw * num_h * apart * (1.0 - lf)
    lo = jaw * num_h * apart * lf
    rot_up = rot0 + ang * (1.0 - lf) * jaw * num_h
    rot_lo = rot0 - ang * lf * jaw * num_h
    sprite = cv.sprite
    # 青蜥蜴：颌和头保持 blackColor（ApplyPalette），上下牙随 HeadColor，眼睛是 effectColor
    cyan = prm.key == "cyan"
    c_jaw = c_head = black if cyan else hc
    c_teeth = hc if cyan else black
    c_eyes = g.effect_color if cyan else black
    sprite(f"LizardJaw{k}.{hg[0]}", px - nx * lo, py - ny * lo, rot_lo, sx, sy, c_jaw, 1.0, 0.5, ay)
    sprite(f"LizardLowerTeeth{k}.{hg[1]}", px - nx * lo, py - ny * lo, rot_lo, sx, sy, c_teeth, 1.0, 0.5, ay)
    if getattr(L, "tongue", None) is not None:
        _draw_tongue(cv, g, fr, ts, hc)
    sprite(f"LizardUpperTeeth{k}.{hg[2]}", px + nx * up, py + ny * up, rot_up, sx, sy, c_teeth, 1.0, 0.5, ay)
    sprite(f"LizardHead{k}.{hg[3]}", px + nx * up, py + ny * up, rot_up, sx, sy, c_head, 1.0, 0.5, ay)
    sprite(f"LizardEyes{k}.{hg[4]}", px + nx * up, py + ny * up, rot_up, sx, sy, c_eyes, 1.0, 0.5, ay)


# 青蜥蜴：舌头、跳跃光、烟雾


def _draw_tongue(cv: Canvas, g, fr: _Frame, ts: float, hc) -> None:
    """舌头：嘴到舌尖的带状网格（颜色从 HeadColor 渐变到 blackColor）加舌尖的小椭圆。"""
    tg = g.lizard.tongue
    if not tg.out:
        return
    parts = g.tongue
    n = len(parts)
    HL = cv.HL
    ax, ay = fr.dx[0], fr.dy[0]
    prev_r = 8.0
    xs: list = []
    ys: list = []
    for i, part in enumerate(parts):
        lp, pp = part.last_pos, part.pos
        vx, vy = lp.x + (pp.x - lp.x) * ts, lp.y + (pp.y - lp.y) * ts
        nx, ny = vx - ax, vy - ay
        d = math.hypot(nx, ny)
        if d > 1e-5:
            nx, ny = nx / d, ny / d
        else:
            nx = ny = 0.0
        qx, qy = -ny, nx
        k = d / 5.0
        r = part.rad
        w = (prev_r + r) * 0.5
        xs.append(ax - qx * w + nx * k)
        ys.append(ay - qy * w + ny * k)
        xs.append(ax + qx * w + nx * k)
        ys.append(ay + qy * w + ny * k)
        if i < n - 1:
            xs.append(vx - qx * r - nx * k)
            ys.append(vy - qy * r - ny * k)
            xs.append(vx + qx * r - nx * k)
            ys.append(vy + qy * r - ny * k)
        else:
            xs.append(vx)
            ys.append(vy)
        prev_r = r
        ax, ay = vx, vy
    nv = len(xs)
    path = QPainterPath()
    path.setFillRule(_Winding)
    path.moveTo(xs[0], HL - ys[0])
    for i in range(2, nv, 2):
        path.lineTo(xs[i], HL - ys[i])
    for i in range(nv - 2 if (nv - 1) % 2 == 0 else nv - 1, 0, -2):
        path.lineTo(xs[i], HL - ys[i])
    path.closeSubpath()
    cv.fill_gradient(path, (xs[0] + xs[1]) * 0.5, (ys[0] + ys[1]) * 0.5, xs[-1], ys[-1], hc, BLACK_COLOR)
    g1, g0 = tg.graph_pos[1], tg.graph_pos[0]
    tx, ty = g1.x + (g0.x - g1.x) * ts, g1.y + (g0.y - g1.y) * ts
    p2 = parts[n - 2]
    ex = p2.last_pos.x + (p2.pos.x - p2.last_pos.x) * ts
    ey = p2.last_pos.y + (p2.pos.y - p2.last_pos.y) * ts
    cv.sprite(
        "Circle20",
        tx,
        ty,
        math.degrees(math.atan2(ex - tx, ey - ty)),
        0.05 * (4.0 if g.lizard.lizard_params.key == "blue" else 5.0),
        0.05 * math.hypot(tx - ex, ty - ey),
        BLACK_COLOR,
        1.0,
        0.5,
        0.0,
    )


# 调色板里的 fogColor（palette0 在 (1, 7)），烟雾淡出用
_FOG_COLOR = (113 / 255.0, 118 / 255.0, 129 / 255.0)
_SMOKE_FADE = color_lerp(BLACK_COLOR, _FOG_COLOR, 0.6)
_Plus = QPainter.CompositionMode.CompositionMode_Plus
_Normal = QPainter.CompositionMode.CompositionMode_SourceOver


_SOFT: dict = {}
_SOFT_N = 32


def _soft_pixmap(col, hard: float, levels: int = 15) -> QPixmap:
    """软边圆盘（颜色量化到 levels 级，中心到 hard 满不透明，边缘淡到 0）。"""
    key = (round(col[0] * levels), round(col[1] * levels), round(col[2] * levels), round(hard * 10), levels)
    pm = _SOFT.get(key)
    if pm is None:
        if len(_SOFT) > 600:
            _SOFT.clear()
        n = _SOFT_N
        pm = QPixmap(n, n)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c0 = QColor(round(key[0] * 255 / levels), round(key[1] * 255 / levels), round(key[2] * 255 / levels))
        c1 = QColor(c0)
        c1.setAlpha(0)
        grad = QRadialGradient(n / 2.0, n / 2.0, n / 2.0)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(key[3] / 10.0, c0)
        grad.setColorAt(1.0, c1)
        q.setPen(_NoPen)
        q.setBrush(QBrush(grad))
        q.drawEllipse(0, 0, n, n)
        q.end()
        _SOFT[key] = pm
    return pm


def _blob(
    p: QPainter, base: QTransform, HL, x, y, rot, rx, ry, col, alpha, hard: float, levels: int = 15
) -> None:
    """软边椭圆（半轴 rx、ry，房间坐标）：中心不透明度 alpha，hard 以内保持，到边缘淡到 0。"""
    a = clamp01(alpha)
    if a <= 0.004:
        return
    r = rot / _DEG
    c, s = math.cos(r), math.sin(r)
    k = 2.0 / _SOFT_N
    # 贴图 (u, v)（像素，中心为原点）→ 房间：X = c*u*rx*k + s*v*ry*k，Y = -s*u*rx*k + c*v*ry*k；窗口 y = HL - y
    p.setTransform(QTransform(c * rx * k, s * rx * k, s * ry * k, -c * ry * k, x, HL - y) * base)
    p.setOpacity(a)
    h = _SOFT_N // 2
    p.drawPixmap(-h, -h, _soft_pixmap(col, hard, levels))


# 烟雾每帧先画到四分之一分辨率的图层再整块放大：软边烟团的像素量大、细节少，直接逐个画太贵
_SMOKE_Q = 0.25
_smoke_layer: list = [None]


def draw_cyan_smoke(p: QPainter, plist, ts: float, alpha: float, HL: float) -> None:
    """CyanLizardSmoke：每个粒子一条拖尾加一团圆（原版是 FireSmoke 着色器，这里用软边渐变近似）。

    plist 是 `jump_module.smoke.draw_list(ts)`：每项是 dict（x0 y0 scale_x0 scale_y0 rotation0 x1 y1 scale1
    alpha0 alpha1 fade_t big lizard_graphics），Futile_White 的 scale 1 = 16px。
    烟雾原版画在最底层（Background 容器），调用方应先于蜥蜴和杆子画。
    """
    if not plist:
        return
    base = p.transform()
    vis = base.inverted()[0].mapRect(QRectF(p.viewport()))
    # 按每个粒子的范围求总包围盒（只算看得见的部分）
    x0 = y0 = 1e30
    x1 = y1 = -1e30
    items = []
    for d in plist:
        r0 = max(d["scale_x0"], d["scale_y0"]) * 8.0
        r1 = d["scale1"] * 8.0
        for cx, cy, r in ((d["x0"], d["y0"], r0), (d["x1"], d["y1"], r1)):
            x0, x1 = min(x0, cx - r), max(x1, cx + r)
            y0, y1 = min(y0, HL - cy - r), max(y1, HL - cy + r)
        items.append(d)
    x0, y0 = max(x0, vis.left()), max(y0, vis.top())
    x1, y1 = min(x1, vis.right()), min(y1, vis.bottom())
    if x1 <= x0 or y1 <= y0:
        return
    q = _SMOKE_Q
    w, h = int(math.ceil((x1 - x0) * q)) + 2, int(math.ceil((y1 - y0) * q)) + 2
    img = _smoke_layer[0]
    if img is None or img.width() < w or img.height() < h:
        img = _smoke_layer[0] = QImage(max(w, 64), max(h, 64), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    ip = QPainter(img)
    ip.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)  # 低分辨率图层，最近邻即可
    k = 2.0 / _SOFT_N * q
    hc_cache: dict = {}
    pix = _soft_pixmap
    half = _SOFT_N // 2
    draw_px = ip.drawPixmap
    set_xf = ip.setTransform
    set_op = ip.setOpacity
    fade = _SMOKE_FADE
    for d in items:
        lg = d["lizard_graphics"]
        if d["big"]:
            col = lg.effect_color
        else:
            col = hc_cache.get(id(lg))
            if col is None:
                col = hc_cache[id(lg)] = head_color(lg, ts)
        t = d["fade_t"]
        col = (
            col[0] + (fade[0] - col[0]) * t,
            col[1] + (fade[1] - col[1]) * t,
            col[2] + (fade[2] - col[2]) * t,
        )
        pm = pix(col, 0.3)
        for xx, yy, rot, rx, ry, a in (
            (d["x0"], d["y0"], d["rotation0"], d["scale_x0"] * 8.0, d["scale_y0"] * 8.0, d["alpha0"] * 0.6),
            (d["x1"], d["y1"], 0.0, d["scale1"] * 8.0, d["scale1"] * 8.0, d["alpha1"] * 0.6),
        ):
            a = 0.0 if a < 0.0 else (1.0 if a > 1.0 else a)
            if a <= 0.004:
                continue
            r = rot / _DEG
            c, sn = math.cos(r), math.sin(r)
            set_xf(
                QTransform(
                    c * rx * k, sn * rx * k, sn * ry * k, -c * ry * k, (xx - x0) * q, (HL - yy - y0) * q
                )
            )
            set_op(a)
            draw_px(-half, -half, pm)
    ip.end()
    old_hints = p.renderHints()
    old_op = p.opacity()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setOpacity(old_op * alpha)
    p.drawImage(QRectF(x0, y0, w / q, h / q), img, QRectF(0, 0, w, h))
    p.setOpacity(old_op)
    p.setRenderHints(old_hints)


def draw_jump_smoke(p: QPainter, jump_module, ts: float, alpha: float, HL: float) -> None:
    """jump_module（可为 None）里的青蜥蜴烟雾。"""
    sm = getattr(jump_module, "smoke", None)
    if sm is not None:
        draw_cyan_smoke(p, sm.draw_list(ts), ts, alpha, HL)


def draw_jump_lights(p: QPainter, jump_module, ts: float, alpha: float, HL: float) -> None:
    """jump_module（可为 None）里的 JumpLight 和 ShockWave（原版都在 Bloom 层，画在最上面）。

    JumpLight 的 draw_data：x y scale=(s0,s1,s2) alpha=(a0,a1,a2)；0 号 LightSource、1 号 FlatLight 着色
    effect_color，2 号白色（原版 intensity 恒 0，alpha 恒 0，跳过）。着色器衰减曲线未知，半径按
    精灵尺寸（scale*8）乘 0.6，强度按观感取。
    ShockWave 的 draw_data：x y scale color；画成渐隐的细环。
    """
    if jump_module is None or not (jump_module.lights or jump_module.shock_waves):
        return
    base = p.transform()
    old_mode = p.compositionMode()
    old_hints = p.renderHints()
    old_op = p.opacity()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setCompositionMode(_Plus)
    p.setPen(_NoPen)
    for light in jump_module.lights:
        d = light.draw_data(ts)
        eff = light.lizard.effect_color
        (s0, s1, _), (a0, a1, _) = d["scale"], d["alpha"]
        _blob(p, base, HL, d["x"], d["y"], 0.0, s0 * 4.8, s0 * 4.8, eff, alpha * 0.45 * a0, 0.0, 31)
        _blob(p, base, HL, d["x"], d["y"], 0.0, s1 * 4.8, s1 * 4.8, eff, alpha * a1, 0.4, 31)
    p.setCompositionMode(_Normal)
    p.setTransform(base)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for sw in jump_module.shock_waves:
        d = sw.draw_data(ts)
        t = d["color"][2]  # 0 → 1：环从中心扩散并淡出
        r = d["scale"] * 8.0
        if r <= 1.0 or t >= 1.0:
            continue
        fade = (1.0 - t) ** 1.5
        pen = QPen(_qc(WHITE, 0.5 * fade * alpha), 1.0 + 5.0 * fade)
        p.setOpacity(1.0)
        p.setPen(pen)
        p.drawEllipse(QPointF(d["x"], HL - d["y"]), r, r)
    p.setCompositionMode(old_mode)
    p.setTransform(base)
    p.setOpacity(old_op)
    p.setRenderHints(old_hints)


# 头盾弹开的粒子：Spark（火花）与 StationaryEffect.FlashingOrb（闪光球）


def draw_sparks(p: QPainter, sparks, ts: float, alpha: float, HL: float) -> None:
    """Spark：一条细三角形拖尾，颜色为粒子色；所属蜥蜴白闪时改用 HeadColor。

    读字段：pos、last_pos、last_last_pos、last_last_last_pos、life、color、lizard（LizardGraphics 或 None）。
    """
    old_hints = p.renderHints()
    old_op = p.opacity()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setOpacity(old_op * alpha)
    p.setPen(_NoPen)
    for sp in sparks:
        lp, pp = sp.last_pos, sp.pos
        x, y = lp.x + (pp.x - lp.x) * ts, lp.y + (pp.y - lp.y) * ts
        a, b = sp.last_last_last_pos, sp.last_last_pos
        tx, ty = a.x + (b.x - a.x) * ts, a.y + (b.y - a.y) * ts
        if math.hypot(x - tx, y - ty) < 9.0:
            dx, dy = (0.0, 1.0) if (x == tx and y == ty) else _unit(tx - x, ty - y)
            tx, ty = x + dx * 9.0, y + dy * 9.0
        k = inverse_lerp(0.0, 0.1, sp.life)
        tx, ty = x + (tx - x) * k, y + (ty - y) * k
        nx, ny = _unit(x - tx, y - ty)
        qx, qy = -ny, nx
        gfx = sp.lizard
        col = head_color(gfx, ts) if gfx is not None and gfx.white_flicker > 0 else sp.color
        p.setBrush(QBrush(_qc(col)))
        path = QPainterPath()
        path.moveTo(x + qx, HL - (y + qy))
        path.lineTo(x - qx, HL - (y - qy))
        path.lineTo(tx, HL - ty)
        path.closeSubpath()
        p.drawPath(path)
    p.setOpacity(old_op)
    p.setRenderHints(old_hints)


def draw_flash_orbs(p: QPainter, effects, ts: float, alpha: float, HL: float) -> None:
    """StationaryEffect.FlashingOrb：随机抖动、忽大忽小的圆球，颜色为所属蜥蜴的 HeadColor（无则灰白随机）。

    读字段：pos、last_pos、life、last_life、lizard（LizardGraphics 或 None）。
    """
    old_hints = p.renderHints()
    old_op = p.opacity()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setOpacity(old_op * alpha)
    p.setPen(_NoPen)
    for ef in effects:
        lp, pp = ef.last_pos, ef.pos
        x, y = lp.x + (pp.x - lp.x) * ts, lp.y + (pp.y - lp.y) * ts
        life = lerp(ef.last_life, ef.life, ts)
        a = _rng.random() * 360.0 / _DEG
        k = _rng.random() * 10.0 * life
        x, y = x + math.sin(a) * k, y + math.cos(a) * k
        r = 10.0 * max(0.0, _rng.random() * life) ** 0.1  # Circle20，scale 即半径的十分之一
        if ef.lizard is not None:
            col = head_color(ef.lizard, ts)
        else:
            col = color_lerp((0.5, 0.5, 0.5), WHITE, _rng.random())
        p.setBrush(QBrush(_qc(col)))
        p.drawEllipse(QPointF(x, HL - y), r, r)
    p.setOpacity(old_op)
    p.setRenderHints(old_hints)


def _unit(x: float, y: float):
    m = math.hypot(x, y)
    return (x / m, y / m) if m > 1e-5 else (0.0, 0.0)
