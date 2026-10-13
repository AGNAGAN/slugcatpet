"""SlugcatGraphics：sprites 由代码定义，每帧从物理算位姿 / 帧 / 色。"""

from __future__ import annotations
import math
import re

from ..core.units import K_VEL, K_IMP, damp60, clampf, inv_lerp
from ..core.vecmath import _ang_from_up, _rot
from ..core.gfxmath import _hsl2rgb, _lerp, SHOULDER_OFF_X, SHOULDER_OFF_Y, TAIL_RAD
from ..core.creature import CARRY_OFF_X, CARRY_OFF_Y, HANDS, _slerp2 as _slerp

HEAD_AIR = damp60(0.99)
HEAD_CONNECT_RAD = 3.0
HEAD_ELASTIC = 0.2 * K_IMP
HEAD_ADAPT_RETAIN = 0.3
HEAD_EXAGGERATE = 0.1
HEAD_TARGET_LERP = 0.20
HEAD_PRELEAD = 3.0

LEGS_AIR = HEAD_AIR
LEGS_CONNECT_RAD = 4.0
LEGS_ELASTIC = 0.25 * K_IMP
LEGS_ADAPT_RETAIN = 0.5
LEGS_EXAGGERATE = 0.1
LEGS_HOST_Y = 10.0 * K_VEL

HUNT_SPEED = 7.0 * K_VEL
HAND_QUICKNESS = 0.5
SHOULDER_RAD = 20.0

CRAWL_HUNT_SPEED = 12.0
CRAWL_QUICKNESS = 0.7

THROW_FOLLOW_TICKS = 5
THROW_SNAP_DIST = 40.0
ATTACH_TICKS = 4  # 抓到后物体并入手的帧数
HOLD_REACH = 20.0  # 手持时手离上身的最远距离
BITE_HEAD_NUDGE = 2.0

_NO_ARM_AIM = {"l": None, "r": None}

SLEEP_CURL_RATE = 0.01 * K_VEL
BLINK_MIN, BLINK_MAX = 2, 1800  # 自驱 blink 间隔（tick）
SLEEP_BLINK_PROB = 1.0 / 30.0  # 睡着睁眼的猫每 tick 眨一下的概率

_COLD_ICY = (0.8, 0.8, 1.0)


def _lerp3(a, b, t):
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _cold_blend(old01, hyp):
    b = _lerp3(old01, _COLD_ICY, hyp)
    return _lerp3(old01, b, 0.92)


LOOK_LEAN_VCAP = 0.10  # 竖直 body-lean 上限
FACE_SIDE_DEADZONE = 0.18  # 朝向信号在死区内保持上一 tick
FACE_SIDE_HYST = 0.30  # 反向信号超过此值才翻面


TAIL_ROOT = 6.0  # 原皮尾根宽，各猫种都一样


def tail_profile(tail: dict, default=TAIL_RAD):
    """DMS 尾巴参数 → 每段半径（段数即 length）与根宽；皮肤没设尾巴时用猫种的 default，根宽固定。"""
    if not any(tail.get(k) for k in ("length", "wideness", "roundness")):
        return tuple(default), TAIL_ROOT
    n = int(round(clampf(tail.get("length") or 4.0, 2.0, 15.0)))
    w = tail.get("wideness") or 1.0
    r = tail.get("roundness") or 0.0
    rads = tuple(
        (6.0 + (1.0 - 6.0) * ((i + 1.0) / n) ** w) * (1.0 + math.sin(i / n * math.pi) * r) for i in range(n)
    )
    return rads, rads[0]


from .graphics_draw import GraphicsDrawMixin
from .. import tuning
from ..appearance import base_colors
from ..characters import default_def


def _latch(s, sig):
    if sig > FACE_SIDE_DEADZONE and (s > 0.0 or sig > FACE_SIDE_HYST):
        return 1.0
    if sig < -FACE_SIDE_DEADZONE and (s < 0.0 or sig < -FACE_SIDE_HYST):
        return -1.0
    return s


class GenericBone:
    __slots__ = ("x", "y", "vx", "vy", "lx", "ly", "pinned")

    def __init__(self, x, y):
        self.x = self.lx = x
        self.y = self.ly = y
        self.vx = self.vy = 0.0
        self.pinned = False

    def update(self, air=HEAD_AIR):
        self.lx, self.ly = self.x, self.y
        self.x += self.vx
        self.y += self.vy
        self.vx *= air
        self.vy *= air

    def connect_to_point(
        self,
        px,
        py,
        host_vx,
        host_vy,
        connect_rad=HEAD_CONNECT_RAD,
        elastic=HEAD_ELASTIC,
        adapt_retain=HEAD_ADAPT_RETAIN,
        exaggerate=HEAD_EXAGGERATE,
    ):
        dx, dy = px - self.x, py - self.y
        if elastic > 0:
            self.vx += dx * elastic
            self.vy += dy * elastic
        self.vx += host_vx * exaggerate
        self.vy += host_vy * exaggerate
        d = math.hypot(dx, dy)
        if d > connect_rad and d > 1e-6:
            ux, uy = dx / d, dy / d
            corr = connect_rad - d
            vecx, vecy = ux * corr, uy * corr
            self.x -= vecx
            self.y -= vecy
            self.vx -= vecx
            self.vy -= vecy
        self.vx = host_vx + (self.vx - host_vx) * adapt_retain
        self.vy = host_vy + (self.vy - host_vy) * adapt_retain


class HeadBone(GenericBone):
    """头部骨。"""


class Hand:
    __slots__ = ("x", "y", "lx", "ly", "vx", "vy", "j", "active", "retract_counter", "mode", "reached")

    def __init__(self, sx, sy, j):
        self.x = self.lx = sx
        self.y = self.ly = sy
        self.vx = self.vy = 0.0
        self.j = j
        self.active = False
        self.retract_counter = 0
        self.mode = "Retracted"
        self.reached = True

    def update(self, sx, sy, target, speed=HUNT_SPEED, quickness=HAND_QUICKNESS):
        """sx,sy=肩点；target=绝对目标或 None（收回）。"""
        self.lx, self.ly = self.x, self.y

        if target is not None:
            retracting = False
            self.mode = "HuntAbsolutePosition"
            self.active = True
        else:
            retracting = True
            self.active = False

        hunt_target = target

        if retracting and self.mode != "Retracted":
            self.retract_counter += 1
            if self.retract_counter > 5:
                self.mode = "HuntAbsolutePosition"
                k = min(1.0, (self.retract_counter - 5) * 0.05)
                self.x += (sx - self.x) * k
                self.y += (sy - self.y) * k
                speed = 1.0 + self.retract_counter * 0.2
                quickness = 1.0
                hunt_target = (sx, sy)
                if math.hypot(self.x - sx, self.y - sy) < 2.0 and self.reached:
                    self.mode = "Retracted"
        else:
            self.retract_counter -= 10
            if self.retract_counter < 0:
                self.retract_counter = 0

        if self.mode == "Retracted":
            self.vx = 0.0
            self.vy = 0.0
            self.x = sx
            self.y = sy
            self.reached = True
        elif self.mode == "HuntAbsolutePosition":
            if hunt_target is not None:
                tx, ty = hunt_target
                dx, dy = tx - self.x, ty - self.y
                d = math.hypot(dx, dy)
                if d < speed:
                    self.vx, self.vy = dx, dy
                    self.reached = True
                else:
                    ux, uy = dx / d, dy / d
                    self.vx += (ux * speed - self.vx) * quickness
                    self.vy += (uy * speed - self.vy) * quickness
                    self.reached = False
                self.x += self.vx
                self.y += self.vy
        if self.mode != "Retracted":
            sdx, sdy = sx - self.x, sy - self.y
            sd = math.hypot(sdx, sdy)
            if sd > SHOULDER_RAD and sd > 1e-6:
                ux, uy = sdx / sd, sdy / sd
                corr = SHOULDER_RAD - sd
                self.x -= ux * corr
                self.y -= uy * corr
                self.vx -= ux * corr
                self.vy -= uy * corr


class SlugcatGraphics(GraphicsDrawMixin):
    def __init__(self, body, layout=None, atlas=None, cat=None, look=None):
        self.body = body
        self.atlas = atlas
        self.cat = cat or default_def()
        self.look = look
        self.BODY = tuple(self.cat.body_color)
        self.EYE = tuple(self.cat.eye_color)

        self.tail_segs = None
        # 绘制层：槽位 → [fn(gfx, painter, atlas, ts)]；能力用 layers，配件用 acc_layers（换配件时重建）
        self.layers = {slot: [] for slot in self.LAYER_SLOTS}
        self.acc_layers = {slot: [] for slot in self.LAYER_SLOTS}
        self.face_pose = ("", 0.0, 0.0, 0.0)

        c0, c1 = body.chunk0, body.chunk1
        self.head = HeadBone(c0.x, c0.y - HEAD_PRELEAD)
        self.legs = GenericBone(c1.x, c1.y + 2.0)
        self.legs_dir = [0.0, 1.0]
        self.hands = [Hand(c0.x - 1, c0.y, 0), Hand(c0.x + 1, c0.y, 1)]
        self.hand_aim = {"l": None, "r": None}
        self.spear_dir = 0.0
        self._throw = None
        self._held_prev = [None, None]
        self._attach = [0, 0]
        self._nudge0 = 0.0  # 咬一口时上身绘制位置的单帧竖直偏移

        self.draw0 = [c0.x, c0.y]
        self.draw1 = [c1.x, c1.y]
        self._last_draw0 = list(self.draw0)
        self._last_draw1 = list(self.draw1)

        self.look_at = None
        self.look_dir = (0.0, 0.0)
        self.sleeping = False
        self.sleep_curl = 0.0
        self.dead = False
        self.stunned = False
        self.blink = 0
        self._blink_rng = _Rng(12345)
        self._shiver_rng = _Rng(0xC01D)  # 发抖用，独立于 blink
        self._asc_rng = _Rng(0xA5C)  # 飞升彩脸，每 tick 抽一次
        self.anim_frame = 0
        self.disbalance = 0.0
        self.balance_counter = 0.0
        self.last_look_dir = (0.0, 0.0)
        self.head_frame_override = None
        self.face_rot_k = 0.0  # 脸的旋转 = 头角度 × 此系数（绘制时按插值后的头角度算）
        self.face_scale_x = 1.0
        self.head_scale_x = 1.0
        self._face_side = 1.0
        self._head_side = 1.0
        self.face_offset = (0.0, 2.0)
        self._last_face_offset = self.face_offset

        fam = self.cat.frames
        self._head_frames = self._family_frames(*fam["head"])
        self._face_frames = self._family_frames(*fam["face"])
        self._face_blink_frames = self._family_frames(*fam["face_blink"])
        self._face_a_frames = self._family_frames(*fam["face_open"]) if "face_open" in fam else []
        self._face_mirror_frames = self._family_frames(*fam["face_mirror"]) if "face_mirror" in fam else []
        self._leg_walk_frames = self._family_frames(*fam["legs_walk"])
        self._leg_crawl_frames = self._family_frames(*fam["legs_crawl"])
        air_key, air_frame = fam["legs_air"]
        self._leg_air_frame = (
            air_frame
            if self.atlas is not None and self.atlas.atlases[air_key].has(air_frame)
            else (self._leg_walk_frames[0] if self._leg_walk_frames else fam["legs_walk"][1] + "0")
        )

        self.ascension = None
        self._asc_face_color = None

        self._legs_scale_x = 1.0
        self._gcol = {}  # 皮肤组色（已叠寒冷）
        self.apply_skin()

    def apply_skin(self, atlas=None):
        if atlas is not None:
            self.atlas = atlas
        a = self.atlas
        self._body0, self.EYE, self._skin_colors = base_colors(
            self.look, self.cat, dict(getattr(a, "colors", {}) or {})
        )
        self._gcol = {}
        self._tail_rad, self._tail_root = tail_profile(
            getattr(a, "tail", {}) or {}, self.cat.tail_rad or TAIL_RAD
        )
        has = getattr(a, "has_group", None)
        self._tail_tex = bool(has and has("TAIL"))
        hidden = getattr(a, "hidden", None)
        self._tail_hidden = bool(hidden and hidden("TAIL"))
        self._tail_asym = bool(getattr(a, "tail_asym", False))

    def _color(self, grp, default):
        return self._gcol.get(grp, default)

    def _update_asc_color(self):
        """飞升时脸随机变色；色相、饱和、亮度量化存桶，tint 缓存有界。"""
        if self.ascension is None or self.dead:
            self._asc_face_color = None
            return
        r = self._asc_rng
        rh = (min(int(r._next() / 0x7FFFFFFF * 6.0), 5) + 0.5) / 6.0
        rs = (min(int(r._next() / 0x7FFFFFFF * 2.0), 1) + 0.5) / 2.0
        rl = (min(int(r._next() / 0x7FFFFFFF * 3.0), 2) + 0.5) / 3.0
        cr, cg, cb = _hsl2rgb(rh, rs, rl)
        self._asc_face_color = (int(cr * 255), int(cg * 255), int(cb * 255))

    @property
    def facing(self):
        return self.body.facing

    @property
    def bodyMode(self):
        return self.body.bodyMode

    def is_moving(self):
        b = self.body
        return b.is_moving() or b.move_dir != 0

    def body_axis(self):
        return _ang_from_up(self.draw0[0] - self.draw1[0], self.draw0[1] - self.draw1[1])

    def update(self):
        """每帧推进，在 body.step() 之后调用。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        self._update_asc_color()

        if b.cold > 0.0:
            base = self._body0
            base01 = (base[0] / 255.0, base[1] / 255.0, base[2] / 255.0)
            cq = round(b.cold * 12) / 12
            r, g, bl = _cold_blend(base01, cq)
            self.BODY = (int(r * 255), int(g * 255), int(bl * 255))
        else:
            self.BODY = self._body0
        if self._skin_colors:
            if b.cold > 0.0:
                cq = round(b.cold * 12) / 12
                gc = {}
                for grp, c in self._skin_colors.items():
                    r, g, bl = _cold_blend((c[0] / 255.0, c[1] / 255.0, c[2] / 255.0), cq)
                    gc[grp] = (int(r * 255), int(g * 255), int(bl * 255))
                self._gcol = gc
            else:
                self._gcol = self._skin_colors

        self._last_draw0, self._last_draw1 = list(self.draw0), list(self.draw1)
        self.draw0 = [c0.x, c0.y]
        self.draw1 = [c1.x, c1.y]
        if b.bodyMode == "Stand":
            if b.is_moving() or b.move_dir != 0:
                self.anim_frame += 1
                if self.anim_frame > 6:
                    self.anim_frame = 0
            else:
                self.anim_frame = 0
        elif b.bodyMode == "Crawl":
            if (b.is_moving() or b.move_dir != 0) and abs(c1.vx) > 0.5:
                self.anim_frame += 1
                if self.anim_frame > 10:
                    self.anim_frame = 0
            else:
                self.anim_frame = 0
        elif b.bodyMode == "ClimbingOnBeam":
            anim = getattr(b, "animation", None)
            if anim in ("ClimbOnBeam", "HangFromBeam", "GetUpOnBeam"):
                self.anim_frame = (self.anim_frame + 1) % 20
            elif anim == "StandOnBeam":
                self.anim_frame = (self.anim_frame + 1) % 7 if abs(c1.vx) > 0.5 else 0
            else:
                self.anim_frame = 0
        elif b.bodyMode == "ZeroG":
            self.anim_frame = (self.anim_frame + 1) % 240
        else:
            self.anim_frame = 0

        self._apply_drawpos_offsets()
        if b.lungs_exhausted and not self.dead:
            # 憋气透支时随 swim_cycle 喘粗气
            sc = math.sin(b.swim_cycle * 2.0 * math.pi)
            self.head.vy -= sc * 1.0
            self.draw0[1] -= sc * 2.5
        if self._nudge0:
            self.draw0[1] += self._nudge0
            self._nudge0 = 0.0
        self._update_blink()

        self.last_look_dir = self.look_dir
        self._update_look()
        if b.exhausted or b.lungs_exhausted:
            self.look_dir = (0.0, 0.0)

        lx, ly = self.look_dir
        if not self.dead and (lx or ly):
            if b.standing:
                ly_c = clampf(ly, -LOOK_LEAN_VCAP, LOOK_LEAN_VCAP)
                if not (b.is_moving() or b.move_dir != 0):
                    self.head.vx -= lx * 0.5
                    self.head.vy -= ly_c * 0.5
                self.draw0[0] -= lx * 2
                self.draw0[1] -= ly_c * 2
            else:
                self.head.vx += lx * K_IMP
                self.head.vy += ly * K_IMP

        tx = self.draw0[0] + (self.draw1[0] - self.draw0[0]) * HEAD_TARGET_LERP
        ty = self.draw0[1] + (self.draw1[1] - self.draw0[1]) * HEAD_TARGET_LERP
        ddx, ddy = self.draw0[0] - self.draw1[0], self.draw0[1] - self.draw1[1]
        dd = math.hypot(ddx, ddy) or 1.0
        if b.bodyMode == "Crawl":
            tx += ddx / dd * HEAD_PRELEAD * 2.5
            ty += ddy / dd * HEAD_PRELEAD
        else:
            tx += ddx / dd * HEAD_PRELEAD
            ty += ddy / dd * HEAD_PRELEAD
        self.head.update(HEAD_AIR)
        hang = getattr(b, "animation", None) == "HangFromBeam"
        self.head.connect_to_point(tx, ty, c0.vx, c0.vy, connect_rad=0.0 if hang else HEAD_CONNECT_RAD)

        if b.cold_gain > 0.0:
            amt = inv_lerp(0.0, 0.0007, b.cold_gain) * 2.0
            if amt > 0.0:
                ang = 6.28318530718 * self._shiver_rng.random()
                self.head.vx += math.cos(ang) * amt
                self.head.vy += math.sin(ang) * amt

        target = 1.0 if self.sleeping else 0.0
        if self.sleep_curl < target:
            self.sleep_curl = min(target, self.sleep_curl + SLEEP_CURL_RATE)
        elif self.sleep_curl > target:
            self.sleep_curl = max(target, self.sleep_curl - SLEEP_CURL_RATE * 1.5)

        self._apply_sleep_curl_pose()

        self._last_face_offset = self.face_offset
        self._update_face_pose()
        self._update_legs()
        self._update_hands()

    def _apply_drawpos_offsets(self):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        flip = b.facing
        af = self.anim_frame
        TAU = 2.0 * math.pi

        if b.bodyMode == "Stand":
            c = clampf(abs(c1.vx) - 0.2, 0.0, 1.0)
            self.draw0[0] += flip * 6.0 * c
            self.draw0[1] -= math.cos((af + 0.0) / 6.0 * TAU) * 2.0
            self.draw1[0] -= flip * (1.5 - af / 6.0) * 1.0
            self.draw1[1] -= 2.0 + math.sin((af + 0.0) / 6.0 * TAU) * 4.0

        elif b.bodyMode == "Crawl":
            sway_slow = math.sin(af / 21.0 * TAU)
            sway_fast = math.cos(af / 14.0 * TAU)
            hip_drop = 0.0 if getattr(b, "_ctrl_super_launch", 0) > 19 else 1.0  # 自主态无该字段则不拱
            self.draw0[0] += sway_fast * flip * 2.0
            self.draw0[1] -= 1.5 * sway_slow + 3.0
            self.head.vy -= 0.5 * sway_slow + 0.5
            self.head.vx += -1.0 if c0.x < c1.x else 1.0
            self.draw1[0] += -3.0 * sway_slow * flip
            self.draw1[1] -= -1.5 * sway_fast + 7.0 - 3.0 * hip_drop

        elif b.bodyMode == "ClimbingOnBeam":
            anim = getattr(b, "animation", None)
            if anim == "ClimbOnBeam":
                ph = af / 20.0 * TAU
                self.draw0[0] += flip * 2.5 + flip * 0.5 * math.sin(ph)
                self.draw1[0] += flip * 2.5 * math.cos(ph)
            elif anim in ("BeamTip", "StandOnBeam"):
                if anim == "StandOnBeam":
                    self.draw1[1] -= 3.0
                sway = math.sin(self.balance_counter / 300.0 * TAU) / (abs(c1.vx) + 1.0)
                self.draw0[0] += sway * (self.disbalance + 20.0) * tuning.BAL_SWAY_X
                self.draw0[1] -= sway * self.disbalance * tuning.BAL_SWAY_Y

        elif b.bodyMode == "ZeroG":
            ddx, ddy = self.draw0[0] - self.draw1[0], self.draw0[1] - self.draw1[1]
            dl = math.hypot(ddx, ddy) or 1.0
            sway = math.sin(af / 240.0 * TAU) * 1.2
            self.draw0[0] += (-ddy / dl) * sway
            self.draw0[1] += (ddx / dl) * sway

        elif b.bodyMode == "Swimming":
            sc = math.sin(b.swim_cycle * TAU)
            if b.swim_mode == "deep" or getattr(b, "swim_input_x", 0) != 0:
                dvx, dvy = c1.x - c0.x, c1.y - c0.y
                dl = math.hypot(dvx, dvy) or 1.0
                px, py = -dvy / dl, dvx / dl
                self.draw1[0] += px * sc * 5.0
                self.draw1[1] += py * sc * 5.0

    def _update_blink(self):
        if self.dead:
            self.blink = 0
            return
        self.blink -= 1
        if self.blink < -self._blink_rng.randint(BLINK_MIN, BLINK_MAX):
            self.blink = self._blink_rng.randint(4, self._blink_rng.randint(4, 15))
        if self.sleeping and self.sleep_curl > 0.5:
            if not self.body.stats.sleep_eyes_open:
                self.blink = max(2, self.blink)
            elif self._blink_rng.random() < SLEEP_BLINK_PROB:
                self.blink = 2
            else:
                self.blink = min(2, self.blink)
        if self.body.lungs_exhausted:
            self.blink = max(self.blink, 1)
        if self.body.exhausted:
            self.blink = max(self.blink, 1)

    def _apply_sleep_curl_pose(self):
        s = self.sleep_curl
        if s <= 0.0:
            return
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        side = 1.0 if c0.x >= c1.x else -1.0
        cx = (c0.x + c1.x) * 0.5
        cy = (c0.y + c1.y) * 0.5
        k = s * 0.2
        self.draw0[0] += (cx - self.draw0[0]) * k
        self.draw0[1] += (cy - self.draw0[1]) * k - 2.0 * s
        self.draw1[0] += (cx - self.draw1[0]) * k - 3.0 * side * s
        self.draw1[1] += (cy - self.draw1[1]) * k - 2.0 * s
        self.head.vx *= 1.0 - 0.4 * s
        self.head.vy *= 1.0 - 0.4 * s
        self.head.x += (cx + side * 5.0 - self.head.x) * (0.5 * s)
        self.head.y += (cy + 3.0 - self.head.y) * (0.5 * s)

    def _apply_sleep_tail_curl(self):
        """尾巴睡眠蜷曲推进，在 tail.step() 之后调用。"""
        s = self.sleep_curl
        if s <= 0.0 or self.tail_segs is None:
            return
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        side = 1.0 if c0.x >= c1.x else -1.0
        d1x, d1y = self.draw1[0], self.draw1[1]
        n = len(self.tail_segs)
        for i, seg in enumerate(self.tail_segs):
            t = i / (n - 1) if n > 1 else 0.0
            seg.vx *= 1.0 - 0.2 * s
            seg.vy *= 1.0 - 0.2 * s
            sin_t = math.sin(t * math.pi)
            tx = d1x + (sin_t * 25.0 - t * 10.0) * (-side)
            ty = d1y + _lerp(-5.0, 15.0, t)
            k = 0.1 * s
            seg.x += (tx - seg.x) * k
            seg.y += (ty - seg.y) * k

    def _update_look(self):
        if self.look_at is None or self.dead:
            self.look_dir = (0.0, 0.0)
            return
        lx = self.look_at[0] - self.head.x
        ly = self.look_at[1] - self.head.y
        d = math.hypot(lx, ly)
        if d < 1e-6:
            self.look_dir = (0.0, 0.0)
            return
        self.look_dir = (lx / d, ly / d)

    def _update_face_pose(self):
        """按物理帧定头脸的帧号覆盖、朝向和脸偏移；头角度与脸旋转在绘制时按插值位置算。"""
        b = self.body
        body_x, body_y = self.draw0
        hip_x, hip_y = self.draw1
        hx, hy = self.head.x, self.head.y
        base_x = (hip_x + body_x) * 0.5
        base_y = (hip_y + body_y) * 0.5
        head_ang = _ang_from_up(hx - base_x, hy - base_y)
        look_x = self.look_dir[0] * 3.0 * (1.0 - self.sleep_curl)
        look_y = self.look_dir[1] * 3.0 * (1.0 - self.sleep_curl)
        self.head_frame_override = None
        self.face_rot_k = 0.0
        if self.sleep_curl > 0.0:
            side = 1.0 if body_x >= hip_x else -1.0
            self.face_rot_k = 1.0 - self.sleep_curl
            self.face_scale_x = side
            look_x -= 4.0 * side * self.sleep_curl
            look_y += 2.0 * self.sleep_curl
        elif self.dead or self.stunned:
            self.face_rot_k = 1.0
            self.face_scale_x = self._face_side
            look_x = look_y = 0.0
        elif b.bodyMode == "Crawl":
            self.head_frame_override = 7
            self.face_scale_x = 1.0 if body_x >= hip_x else -1.0
            look_x = 0.0
        elif b.bodyMode in ("ZeroG", "Swimming"):
            self.face_rot_k = 1.0
            self.face_scale_x = self._latch_face(head_ang)
        elif b.bodyMode == "Stand" and (b.is_moving() or b.move_dir != 0):
            self.head_frame_override = 6
            self.face_scale_x = 1.0 if head_ang >= 0 else -1.0
            look_x = 0.0
        else:
            self.face_scale_x = self._latch_face(look_x if abs(look_x) >= FACE_SIDE_DEADZONE else head_ang)
        self.face_offset = (look_x, look_y + 2.0)
        self._head_side = _latch(self._head_side, head_ang)
        self.head_scale_x = self._head_side

    def face_offset_at(self, ts):
        """插值后的脸偏移（相对头心）。"""
        (lx, ly), (cx, cy) = self._last_face_offset, self.face_offset
        return (_lerp(lx, cx, ts), _lerp(ly, cy, ts))

    def head_pose_at(self, ts):
        """插值并叠上呼吸偏移后的头心与头角度（相对躯干中点，未计睡眠蜷缩）。"""
        hox, hoy = getattr(self, "_breath_head_off", (0.0, 0.0))
        cox, coy = getattr(self, "_breath_chest_off", (0.0, 0.0))
        hx = _lerp(self.head.lx, self.head.x, ts) + hox
        hy = _lerp(self.head.ly, self.head.y, ts) + hoy
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts) + cox
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts) + coy
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)
        return hx, hy, _ang_from_up(hx - (d0x + d1x) * 0.5, hy - (d0y + d1y) * 0.5)

    def _latch_face(self, sig):
        self._face_side = _latch(self._face_side, sig)
        return self._face_side

    def _update_legs(self):
        b = self.body
        c1 = b.chunk1
        self.legs.update(LEGS_AIR)

        anim = getattr(b, "animation", None)
        if b.bodyMode == "ClimbingOnBeam" and anim in (
            "ClimbOnBeam",
            "BeamTip",
            "StandOnBeam",
            "HangFromBeam",
            "GetUpOnBeam",
        ):
            c0 = b.chunk0
            if anim == "ClimbOnBeam":
                ph = self.anim_frame / 20.0 * 2.0 * math.pi
                tx = c0.x + (-b.facing) * (5.0 - math.sin(ph))
                ty = c0.y + 16.0 + 5.0 * math.cos(ph)
                self.legs.connect_to_point(
                    tx,
                    ty,
                    0.0,
                    0.0,
                    connect_rad=0.0,
                    elastic=LEGS_ELASTIC,
                    adapt_retain=LEGS_ADAPT_RETAIN,
                    exaggerate=LEGS_EXAGGERATE,
                )
                self.legs_dir[1] += 1.0
            elif anim == "BeamTip":
                self.legs.connect_to_point(
                    c1.x,
                    c1.y + 8.0,
                    0.0,
                    10.0,
                    connect_rad=0.0,
                    elastic=LEGS_ELASTIC,
                    adapt_retain=LEGS_ADAPT_RETAIN,
                    exaggerate=LEGS_EXAGGERATE,
                )
                dx = c1.x - self.draw0[0]
                dy = (c1.y + 10.0) - self.draw0[1]
                dl = math.hypot(dx, dy) or 1.0
                self.legs_dir[0] += dx / dl
                self.legs_dir[1] += dy / dl
            elif anim == "StandOnBeam":
                tx = c1.x + self.legs_dir[0] * 8.0
                ty = c1.y - 1.0
                self.legs.connect_to_point(
                    tx,
                    ty,
                    c1.vx,
                    LEGS_HOST_Y,
                    connect_rad=5.0,
                    elastic=LEGS_ELASTIC,
                    adapt_retain=LEGS_ADAPT_RETAIN,
                    exaggerate=LEGS_EXAGGERATE,
                )
                self.legs_dir[1] += 1.0
            else:
                tx = c1.x + self.legs_dir[0] * 8.0
                ty = c1.y + (5.0 if anim == "HangFromBeam" else 2.0)
                self.legs.connect_to_point(
                    tx,
                    ty,
                    c1.vx,
                    LEGS_HOST_Y,
                    connect_rad=LEGS_CONNECT_RAD,
                    elastic=LEGS_ELASTIC,
                    adapt_retain=LEGS_ADAPT_RETAIN,
                    exaggerate=LEGS_EXAGGERATE,
                )
                self.legs_dir[0] += c1.vx * 0.01
                self.legs_dir[1] += c1.vy * 0.01 + 0.05
            d = math.hypot(self.legs_dir[0], self.legs_dir[1]) or 1.0
            self.legs_dir[0] /= d
            self.legs_dir[1] /= d
            return

        if b.bodyMode == "ZeroG":
            c0 = b.chunk0
            dx, dy = c1.x - c0.x, c1.y - c0.y
            dl = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dl, dy / dl
            self.legs.connect_to_point(
                c1.x + ux * 4.0,
                c1.y + uy * 4.0,
                c1.vx,
                c1.vy,
                connect_rad=LEGS_CONNECT_RAD,
                elastic=0.0,
                adapt_retain=0.8,
                exaggerate=0.0,
            )
            self.legs_dir[0] = ux
            self.legs_dir[1] = uy
            self.legs.vx += ux * 0.2
            self.legs.vy += uy * 0.2
            d = math.hypot(self.legs_dir[0], self.legs_dir[1]) or 1.0
            self.legs_dir[0] /= d
            self.legs_dir[1] /= d
            return

        if c1.on_floor:
            tx = c1.x + self.legs_dir[0] * 8.0
            ty = c1.y - 1.0
            self.legs.connect_to_point(
                tx,
                ty,
                c1.vx,
                LEGS_HOST_Y,
                connect_rad=5.0,
                elastic=LEGS_ELASTIC,
                adapt_retain=LEGS_ADAPT_RETAIN,
                exaggerate=LEGS_EXAGGERATE,
            )
            self.legs_dir[0] -= b.chunk1.on_slope if hasattr(b.chunk1, "on_slope") else 0.0
            self.legs_dir[1] += 1.0
        else:
            tx = c1.x + self.legs_dir[0] * 8.0
            ty = c1.y + 2.0
            self.legs.connect_to_point(
                tx,
                ty,
                c1.vx,
                LEGS_HOST_Y,
                connect_rad=LEGS_CONNECT_RAD,
                elastic=LEGS_ELASTIC,
                adapt_retain=LEGS_ADAPT_RETAIN,
                exaggerate=LEGS_EXAGGERATE,
            )
            self.legs_dir[0] += c1.vx * 0.01
            self.legs_dir[1] += c1.vy * 0.01 + 0.05

        d = math.hypot(self.legs_dir[0], self.legs_dir[1]) or 1.0
        self.legs_dir[0] /= d
        self.legs_dir[1] /= d

    def throw_object(self, side, obj):
        """出手后几帧内让投掷手追着物体甩出去。"""
        self._throw = (side, obj, THROW_FOLLOW_TICKS)

    def _walk_ix(self):
        b = self.body
        if b.move_dir:
            return 1 if b.move_dir > 0 else -1
        if b.is_moving():
            return 1 if b.walk_target_x > b.chunk1.x else -1
        return 0

    def _update_spear_dir(self):
        """走路时手持物下垂摆动的混合量，随行走方向渐变。"""
        ix = self._walk_ix() if self.body.bodyMode == "Stand" else 0
        if ix:
            self.spear_dir = clampf(self.spear_dir + ix * 0.1, -1.0, 1.0)
        elif self.spear_dir < 0.0:
            self.spear_dir = min(self.spear_dir + 0.05, 0.0)
        elif self.spear_dir > 0.0:
            self.spear_dir = max(self.spear_dir - 0.05, 0.0)

    def bite(self, side):
        """咬一口：手连同食物贴到胸口，头朝手一顿，胸口上抬一下，眨眼。"""
        h = self.hands[HANDS.index(side)]
        dx, dy = h.x - self.head.x, h.y - self.head.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            self.head.vx += dx / d * BITE_HEAD_NUDGE
            self.head.vy += dy / d * BITE_HEAD_NUDGE
        self._nudge0 = -1.0
        h.x, h.y = self.draw0
        self.blink = max(self.blink, 5)

    def _hold_target(self, idx, side):
        """手持物时手的目标：上身侧下方，叠加啃食、换手、走路摆动；离胸口不超过 HOLD_REACH。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        sgn = -1.0 if idx == 0 else 1.0
        rx, ry = sgn * CARRY_OFF_X, CARRY_OFF_Y
        e = b.eat_raise[side]
        if e > 0.0:
            s = 0.9 - 0.2 * e
            rx *= s * (1.0 + 0.2 * e)
            ry = ry * s - (2.0 + 2.0 * e)
        rx *= 1.0 - math.sin(b.switch_hands * math.pi)
        k = abs(self.spear_dir)
        if k > 0.0 and b.bodyMode == "Stand":
            ix = self._walk_ix()
            af = self.anim_frame
            d = math.radians(180.0 + sgn * 8.0 + ix * 4.0)
            wx = math.sin(d) * 12.0 - math.cos(af / 12.0 * 2.0 * math.pi) * 4.0 * ix + ix * 2.0
            wy = -math.cos(d) * 12.0 - math.sin(af / 6.0 * 2.0 * math.pi) * 2.0
            rx += (wx - rx) * k
            ry += (wy - ry) * k
        d = math.hypot(rx, ry)
        if d > HOLD_REACH:
            rx, ry = rx * HOLD_REACH / d, ry * HOLD_REACH / d
        ox, oy = _rot(rx, ry, _ang_from_up(c0.x - c1.x, c0.y - c1.y))
        return c0.x + ox, c0.y + oy

    def _pin_held(self):
        """把手持物贴到手上；刚抓到的几帧里物体和手相向靠拢。"""
        b = self.body
        c0 = b.chunk0
        for idx, side in enumerate(HANDS):
            obj = b.grasps[side]
            if obj is None:
                self._attach[idx] = 0
                continue
            h = self.hands[idx]
            obj.last_x, obj.last_y = obj.x, obj.y
            n = self._attach[idx]
            if n > 0:
                k = 1.0 / n
                obj.x += (h.x - obj.x) * k
                obj.y += (h.y - obj.y) * k
                self._attach[idx] = n - 1
            else:
                obj.x, obj.y = h.x, h.y
            if getattr(obj, "throwable", False):
                obj.set_held_direction(*self._held_item_direction(idx, obj))
                obj.behind = self._held_behind(idx)
            else:
                obj.set_rotation_to_grabber(c0.x, c0.y)

    def _held_item_direction(self, idx, obj):
        """手持武器的朝向：站着斜向外，趴着顺身体，爬杆偏向上。"""
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        anim = getattr(b, "animation", None)
        sgn = -1.0 if idx == 0 else 1.0
        dx, dy = obj.x - c0.x, obj.y - c0.y
        d = math.hypot(dx, dy) or 1.0
        vx, vy = dx / d * sgn, dy / d * sgn
        if anim != "HangFromBeam":
            vx, vy = vy, -vx
        if b.bodyMode == "Crawl":
            tx = obj.x + (c0.x - obj.x) * 0.8 - c1.x
            ty = obj.y + (c0.y - obj.y) * 0.8 - c1.y
            d = math.hypot(tx, ty) or 1.0
            vx, vy = tx / d, ty / d
        elif anim == "ClimbOnBeam":
            vy = -abs(vy)
            ax, ay = c0.x - c1.x, c0.y - c1.y
            d = math.hypot(ax, ay) or 1.0
            vx, vy = _slerp(vx, vy, ax / d, ay / d, 0.75)
        return vx, vy

    def _held_behind(self, idx):
        """走路时远侧那只手的武器画到身后。"""
        sd = self.spear_dir
        if sd == 0.0 or self.body.bodyMode != "Stand":
            return False
        return not ((sd > -0.4 and idx == 0) or (sd < 0.4 and idx == 1))

    def _note_grabs(self):
        """手里换了新东西时开始靠拢计数。"""
        b = self.body
        for idx, side in enumerate(HANDS):
            obj = b.grasps[side]
            if obj is not None and obj is not self._held_prev[idx] and b.switch_hands == 0.0:
                self._attach[idx] = ATTACH_TICKS
        self._held_prev = [b.grasps[s] for s in HANDS]

    def _update_hands(self):
        b = self.body
        self._note_grabs()
        self._update_spear_dir()
        spine_ang = self.body_axis()
        crawl_ground_y = getattr(b, "visual_floor_y", b.H) - 4.0
        thr = self._throw
        if thr is not None and (thr[2] <= 0 or self.dead):
            thr = self._throw = None
        for idx, (side, sh_local_sign) in enumerate((("l", -1.0), ("r", +1.0))):
            sx, sy = self._shoulder(sh_local_sign, spine_ang)
            hand = self.hands[0] if side == "l" else self.hands[1]
            held = None if self.dead else b.grasps[side]

            # 优先级：投掷 > hand_aim > arm_aim > 啃食 > 内部姿态 > 手持 > None（收回）
            aim = None if self.dead else self.hand_aim[side]
            if thr is not None and thr[0] == side:
                aim = (thr[1].x, thr[1].y)
            if aim is None and held is not None and self._attach[idx] > 0:
                aim = (held.x, held.y)
            if aim is None and not self.dead:
                aim = getattr(b, "arm_aim", _NO_ARM_AIM).get(side)
            speed = HUNT_SPEED
            quickness = HAND_QUICKNESS
            if aim is None and held is not None and b.eat_raise[side] > 0.0:
                aim = self._hold_target(idx, side)

            if aim is None and not self.dead:
                anim = getattr(b, "animation", None)
                balanced = anim == "StandOnBeam" and self.disbalance <= 0.0
                if (
                    b.bodyMode == "ClimbingOnBeam"
                    and anim in ("ClimbOnBeam", "BeamTip", "StandOnBeam", "HangFromBeam", "GetUpOnBeam")
                    and not (balanced and held is not None)  # 站稳后手持的手不再平衡
                ):
                    aim, speed, quickness = self._beam_hand_target(idx, anim, spine_ang)
                elif b.bodyMode == "Crawl":
                    if self.sleep_curl > 0.0:
                        if held is not None:
                            aim = (sx + sh_local_sign * 2.0, sy + 6.0)  # 睡觉把手持物抱在胸下
                        # 空手缩回贴肩，勿伸向腹部目标
                    else:
                        c0 = b.chunk0
                        vspd = math.hypot(c0.vx, c0.vy)
                        if vspd > 1e-6:
                            lead_x = c0.vx / vspd * 20.0
                        else:
                            lead_x = b.facing * 20.0
                        off_x = -6.0 + 12.0 * idx
                        aim = (c0.x + off_x + lead_x, crawl_ground_y)
                        speed = CRAWL_HUNT_SPEED
                        quickness = CRAWL_QUICKNESS
                elif b.bodyMode == "ZeroG" and getattr(b, "animation", None) == "ZeroGPoleGrab":
                    px = getattr(b, "pole_x", b.chunk0.x)
                    py = getattr(b, "pole_y", b.chunk0.y)
                    pole = getattr(b, "zerog_pole", None)
                    if pole is not None:
                        plx, ply = pole.bx - pole.ax, pole.by - pole.ay
                        pll = math.hypot(plx, ply) or 1.0
                        axu, ayu = plx / pll, ply / pll
                    else:
                        axu, ayu = 0.0, 1.0
                    off = 6.0 * (-1.0 if idx == 0 else 1.0)
                    aim = (px + axu * off, py + ayu * off)
                elif b.bodyMode == "ZeroG":
                    ph = self.anim_frame / 240.0 * 2.0 * math.pi + idx * math.pi
                    ox, oy = _rot(sh_local_sign * 6.0, 8.0 + 2.0 * math.sin(ph), spine_ang)
                    aim = (self.draw0[0] + ox, self.draw0[1] + oy)
                    speed = 3.0
                    quickness = 0.3
                elif b.bodyMode == "Swimming":
                    c0, c1 = b.chunk0, b.chunk1
                    sw = b.swim_cycle
                    paddle_t = sw / 3.0 if sw < 3.0 else (1.0 - (sw - 3.0))
                    ix = getattr(b, "swim_input_x", 0)
                    if b.swim_mode == "deep":
                        stroke = (1.0 - inv_lerp(0.5, 1.0, paddle_t)) ** 1.5
                        ang = math.radians((20.0 + stroke * 140.0) * sh_local_sign)
                        rhx, rhy = math.sin(ang) * 20.0, math.cos(ang) * 20.0
                        if sw < 3.0:
                            rhx *= 0.5
                        spine_phys = _ang_from_up(c0.x - c1.x, c0.y - c1.y)
                        ox, oy = _rot(rhx, -rhy, spine_phys)
                        aim = (c0.x + ox, c0.y + oy)
                    else:
                        ws = getattr(b, "water_surface", None)
                        ahx = c0.x + _lerp(
                            sh_local_sign * 30.0, ix * 10.0 * (-math.sin(paddle_t * 2.0 * math.pi)), 0.5
                        )
                        ahy = (ws.level_at(ahx) + 7.0) if ws is not None else (c0.y + 7.0)
                        sang = math.radians(360.0 * paddle_t * (1.0 if ix == 0 else -ix))
                        srad = sh_local_sign * (5.0 if ix == 0 else 10.0)
                        aim = (ahx + math.sin(sang) * srad, ahy - math.cos(sang) * srad)
                    speed = 5.0
                    quickness = 0.5

            if aim is None and held is not None:
                aim = self._hold_target(idx, side)
            hand.update(sx, sy, aim, speed=speed, quickness=quickness)

        if thr is not None:
            side, obj, n = thr
            h = self.hands[HANDS.index(side)]
            o = self.hands[1 - HANDS.index(side)]
            dx, dy = obj.x - h.x, obj.y - h.y
            d = math.hypot(dx, dy)
            if d < THROW_SNAP_DIST:
                sgn = -1.0 if side == "l" else 1.0
                sx, sy = self._shoulder(sgn, spine_ang)
                ex, ey = obj.x - sx, obj.y - sy
                el = math.hypot(ex, ey)
                k = SHOULDER_RAD / el if el > SHOULDER_RAD else 1.0
                h.x, h.y = sx + ex * k, sy + ey * k
            elif d > 1e-6:
                h.vx += dx / d * 6.0
                h.vy += dy / d * 6.0
            if d > 1e-6:
                o.vx -= dx / d * 3.0
                o.vy -= dy / d * 3.0
            self._throw = (side, obj, n - 1)
        self._pin_held()

    def _beam_hand_target(self, j, anim, axis):
        b = self.body
        c0, c1 = b.chunk0, b.chunk1
        if anim == "ClimbOnBeam":
            px = getattr(b, "pole_x", c1.x)
            flip = b.facing
            ph = self.anim_frame / 20.0 * 2.0 * math.pi
            b_j1 = j == 1
            b_fp = flip == 1
            f = math.cos(ph) if (b_j1 != b_fp) else math.sin(ph)
            cond = b_j1 == b_fp
            off_y_up = (-3.0 if cond else 3.0) + 6.0 * f
            hx = px + (-flip if cond else flip)
            hy = c0.y - off_y_up
            return (hx, hy), HUNT_SPEED, HAND_QUICKNESS
        if anim in ("HangFromBeam", "GetUpOnBeam"):
            beam_y = getattr(b, "pole_y", c0.y)
            sh = 10.0 + 3.0 * math.sin(2.0 * math.pi * self.anim_frame / 20.0)
            hx = c0.x + (-1.0 if j == 0 else 1.0) * sh
            return (hx, beam_y), HUNT_SPEED, HAND_QUICKNESS
        sway = math.sin(2.0 * math.pi * self.balance_counter / 300.0)
        relx = -20.0 + 40.0 * j
        rely_up = -4.0 - 6.0 * sway * (-1.0 if j == 0 else 1.0)
        if anim == "StandOnBeam" and self.disbalance < 40.0:
            s = (40.0 - self.disbalance) / 40.0
            rely_up = rely_up * (1.0 - s) - s * 15.0
            relx = relx * (1.0 - s)
        ox, oy = _rot(relx, -rely_up, axis)
        return (c0.x + ox, c0.y + oy), 5.0, 0.2

    def _shoulder(self, sign, spine_ang):
        """肩点 = draw0 + 绕轴旋转 (±4.5,+3.5)。"""
        ox, oy = _rot(sign * SHOULDER_OFF_X, SHOULDER_OFF_Y, spine_ang)
        return self.draw0[0] + ox, self.draw0[1] + oy

    def tail_root_world(self):
        """尾网根世界坐标 = 75% 臀 + 25% 上身。"""
        return ((self.draw1[0] * 3.0 + self.draw0[0]) / 4.0, (self.draw1[1] * 3.0 + self.draw0[1]) / 4.0)

    def mouth_world(self):
        """逻辑用的嘴位置：脸偏移取前后两帧的中点。"""
        ox, oy = self.face_offset_at(0.5)
        return (self.head.x + ox, self.head.y + oy)

    def _family_frames(self, atlas_key, prefix):
        def idx(name):
            m = re.search(r"(\d+)$", name)
            return int(m.group(1)) if m else -1

        names = [n for n in self.atlas.atlases[atlas_key].frame_names() if re.sub(r"\d+$", "", n) == prefix]
        return sorted(names, key=idx)

    def _face_angle_index(self, ts=1.0):
        look_ox, look_oy = self.face_offset_at(ts)
        look_mag = math.hypot(look_ox, look_oy - 2.0)
        hx, hy, _ang = self.head_pose_at(ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)
        axis_x = (hx - d1x) * (1.0 - look_mag / 3.0)
        ang = abs(_ang_from_up(axis_x, hy - d1y))
        return int(round(ang / 22.5))

    def _head_frame_index(self, head_ang):
        """HeadB 帧号单一真值源：sleep > dead > Crawl > Stand&&moving > ZeroG > 角度基线。"""
        b = self.body
        if self.sleep_curl > 0.0:
            return int(clampf(int(_lerp(7.0, 4.0, self.sleep_curl)), 0, 8))
        if self.dead or self.stunned:
            return 0
        if b.bodyMode == "Crawl":
            return 7
        if b.bodyMode == "Stand" and (b.is_moving() or b.move_dir != 0):
            return 6
        if b.bodyMode == "ZeroG":
            return 0
        return int(round(abs(head_ang / 360.0 * 34.0)))


class _Rng:
    """确定性 LCG（blink/face 用）。"""

    __slots__ = ("s",)

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFF

    def _next(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s

    def randint(self, lo, hi):
        if hi <= lo:
            return lo
        return lo + self._next() % (hi - lo)

    def random(self):
        return self._next() / 2147483647.0
