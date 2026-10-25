"""蜥蜴移植用的原版数学：Vector2、Mathf、RWCustom.Custom 的等价实现。坐标系与原版相同（y↑）。"""

from __future__ import annotations

import math
import random

DEG = math.pi / 180.0


class V2:
    """不可变二维向量，语义同 Unity Vector2。"""

    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.x = float(x)
        self.y = float(y)

    def __add__(self, o):
        return V2(self.x + o.x, self.y + o.y)

    def __sub__(self, o):
        return V2(self.x - o.x, self.y - o.y)

    def __mul__(self, k):
        return V2(self.x * k, self.y * k)

    __rmul__ = __mul__

    def __truediv__(self, k):
        return V2(self.x / k, self.y / k)

    def __neg__(self):
        return V2(-self.x, -self.y)

    def __eq__(self, o):
        return isinstance(o, V2) and self.x == o.x and self.y == o.y

    def __hash__(self):
        return hash((self.x, self.y))

    def __iter__(self):
        yield self.x
        yield self.y

    def __repr__(self):
        return f"V2({self.x:.3f}, {self.y:.3f})"

    @property
    def magnitude(self) -> float:
        return math.hypot(self.x, self.y)

    @property
    def sqr_magnitude(self) -> float:
        return self.x * self.x + self.y * self.y

    @property
    def normalized(self) -> V2:
        m = math.hypot(self.x, self.y)
        return V2(self.x / m, self.y / m) if m > 1e-5 else V2()


ZERO = V2()


def dot(a: V2, b: V2) -> float:
    return a.x * b.x + a.y * b.y


def distance(a: V2, b: V2) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def vlerp(a: V2, b: V2, t: float) -> V2:
    """Vector2.Lerp（t 夹到 0..1）。"""
    t = clamp01(t)
    return V2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)


def clamp_magnitude(v: V2, m: float) -> V2:
    s = v.sqr_magnitude
    if s > m * m:
        k = m / math.sqrt(s)
        return V2(v.x * k, v.y * k)
    return v


def vangle(a: V2, b: V2) -> float:
    """Vector2.Angle：两向量夹角（度，无符号）。"""
    d = math.sqrt(a.sqr_magnitude * b.sqr_magnitude)
    if d < 1e-15:
        return 0.0
    return math.degrees(math.acos(clamp(dot(a, b) / d, -1.0, 1.0)))


# Mathf


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def lerp(a: float, b: float, t: float) -> float:
    """Mathf.Lerp（t 夹到 0..1）。"""
    return a + (b - a) * clamp01(t)


def lerp_unclamped(a: float, b: float, t: float) -> float:
    """Unity.Mathematics math.lerp（不夹）。"""
    return a + (b - a) * t


def inverse_lerp(a: float, b: float, v: float) -> float:
    if a == b:
        return 0.0
    return clamp01((v - a) / (b - a))


def sign(v: float) -> float:
    """Mathf.Sign：0 也返回 1。"""
    return 1.0 if v >= 0.0 else -1.0


def int_clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else (hi if v > hi else v)


def floor_to_int(v: float) -> int:
    return math.floor(v)


def round_to_int(v: float) -> int:
    """Mathf.RoundToInt：银行家舍入，同 C# Math.Round。"""
    return round(v)


# RWCustom.Custom

EIGHT_DIRECTIONS = ((-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1))
EIGHT_DIRECTIONS_DIAGONALS_LAST = ((-1, 0), (0, -1), (1, 0), (0, 1), (-1, -1), (1, -1), (1, 1), (-1, 1))
EIGHT_DIRECTIONS_AND_ZERO = ((0, 0), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1))
FOUR_DIRECTIONS = ((-1, 0), (0, -1), (1, 0), (0, 1))
FOUR_DIRECTIONS_AND_ZERO = ((0, 0), (-1, 0), (0, -1), (1, 0), (0, 1))


def int_clamp_at_one(dx: int, dy: int) -> tuple[int, int]:
    """IntVector2.ClampAtOne。"""
    return (max(-1, min(1, dx)), max(-1, min(1, dy)))


def dir_vec(a: V2, b: V2) -> V2:
    """重合时返回 (0, 1)，同原版。"""
    if a.x == b.x and a.y == b.y:
        return V2(0.0, 1.0)
    return (b - a).normalized


def dist_less(a: V2, b: V2, d: float) -> bool:
    return math.hypot(a.x - b.x, a.y - b.y) < d


def dist_no_sqrt(a: V2, b: V2) -> float:
    dx, dy = a.x - b.x, a.y - b.y
    return dx * dx + dy * dy


def deg_to_vec(ang: float) -> V2:
    """0° 朝上，顺时针为正。"""
    return V2(math.sin(ang * DEG), math.cos(ang * DEG))


def vec_to_deg(v: V2) -> float:
    return math.degrees(math.atan2(v.x, v.y))


def aim_from_one_vector_to_another(a: V2, b: V2) -> float:
    return vec_to_deg(b - a)


def perpendicular_vector(v: V2) -> V2:
    n = v.normalized
    return V2(-n.y, n.x)


def rotate_around_origo(v: V2, deg: float) -> V2:
    a = -deg * DEG
    c, s = math.cos(a), math.sin(a)
    return V2(c * v.x - s * v.y, s * v.x + c * v.y)


def distance_to_line(v: V2, l2: V2, l1: V2) -> float:
    return ((l2.y - l1.y) * v.x - (l2.x - l1.x) * v.y + l2.x * l1.y - l2.y * l1.x) / math.sqrt(
        (l2.y - l1.y) ** 2 + (l2.x - l1.x) ** 2
    )


def signed_angle(a: V2, b: V2) -> float:
    """Custom.Angle。"""
    return vangle(a, b) * sign(distance_to_line(a, b, -b))


def closest_point_on_line(a: V2, b: V2, p: V2) -> V2:
    ap, ab = p - a, b - a
    k = (ap.x * ab.x + ap.y * ab.y) / (ab.x * ab.x + ab.y * ab.y)
    return V2(a.x + ab.x * k, a.y + ab.y * k)


def move_towards(a: V2, b: V2, speed: float) -> V2:
    if dist_less(a, b, speed):
        return b
    return a + dir_vec(a, b) * speed


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def lerp_map(
    val: float, from_a: float, to_a: float, from_b: float, to_b: float, exponent: float = 1.0
) -> float:
    t = inverse_lerp(from_a, to_a, val)
    if exponent != 1.0:
        t = t**exponent
    return lerp_unclamped(from_b, to_b, t)


def lerp_and_tick(a: float, b: float, k: float, tick: float) -> float:
    a = lerp(a, b, k)
    if a < b:
        return min(a + tick, b)
    return max(a - tick, b)


def s_curve(x: float, k: float) -> float:
    x = x * 2.0 - 1.0
    if x < 0.0:
        x = abs(1.0 + x)
        return k * x / (k - x + 1.0) * 0.5
    k = -1.0 - k
    return 0.5 + k * x / (k - x + 1.0) * 0.5


def lerp_elastic_ease_in(start: float, end: float, perc: float) -> float:
    n = -(2.0 ** (10.0 * (perc - 1.0))) * math.sin((perc - 1.1) * 2.0 * math.pi / 0.4)
    return (end - start) * n + start


def lerp_elastic_ease_out(start: float, end: float, perc: float) -> float:
    n = 2.0 ** (-10.0 * perc) * math.sin((perc - 0.1) * 2.0 * math.pi / 0.4) + 1.0
    return (end - start) * n + start


# 随机：原版用全局 UnityEngine.Random，这里每只蜥蜴一个 random.Random，调用方传进来


def rnv(rng: random.Random) -> V2:
    return deg_to_vec(rng.random() * 360.0)


def _random_deviation(rng: random.Random, k: float) -> float:
    return s_curve(rng.random() * 0.5, k) * 2.0 * (1.0 if rng.random() < 0.5 else -1.0)


def clamped_random_variation(rng: random.Random, base: float, max_dev: float, k: float) -> float:
    return clamp(base + _random_deviation(rng, k) * max_dev, 0.0, 1.0)


def wrapped_random_variation(rng: random.Random, base: float, max_dev: float, k: float) -> float:
    n = base + _random_deviation(rng, k) * max_dev + 1.0
    return n - math.floor(n)


def random_range_int(rng: random.Random, lo: int, hi: int) -> int:
    """UnityEngine.Random.Range(int, int)：hi 不含；lo >= hi 时返回 lo。"""
    return lo if hi <= lo else rng.randrange(lo, hi)


def random_range(rng: random.Random, lo: float, hi: float) -> float:
    """UnityEngine.Random.Range(float, float)：两端都含。"""
    return lo + (hi - lo) * rng.random()


# 颜色：(r, g, b) 0..1 的元组


def hsl2rgb(h: float, s: float, lum: float) -> tuple[float, float, float]:
    r = g = b = lum
    v = lum * (1.0 + s) if lum <= 0.5 else lum + s - lum * s
    if v > 0.0:
        m = lum + lum - v
        sv = (v - m) / v
        h *= 6.0
        sextant = int(h)
        fract = h - sextant
        vsf = v * sv * fract
        mid1, mid2 = m + vsf, v - vsf
        r, g, b = {
            0: (v, mid1, m),
            1: (mid2, v, m),
            2: (m, v, mid1),
            3: (m, mid2, v),
            4: (mid1, m, v),
            5: (v, m, mid2),
        }.get(sextant, (r, g, b))
    return (r, g, b)


def rgb2hsl(c: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = c
    hi, lo = max(r, g, b), min(r, g, b)
    lum = (hi + lo) / 2.0
    if hi == lo:
        return (0.0, 0.0, lum)
    d = hi - lo
    s = d / (2.0 - hi - lo) if lum > 0.5 else d / (hi + lo)
    if hi == r:
        h = (g - b) / d + (6.0 if g < b else 0.0)
    elif hi == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return (h / 6.0, s, lum)


def color_lerp(a, b, t: float):
    """Color.Lerp（t 夹到 0..1），按元素对齐（3 或 4 元）。"""
    t = clamp01(t)
    return tuple(x + (y - x) * t for x, y in zip(a, b))
