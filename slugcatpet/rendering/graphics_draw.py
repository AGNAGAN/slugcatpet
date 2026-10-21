"""SlugcatGraphics 的绘制方法（混入类）。"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from ..core.units import clampf
from ..core.vecmath import _ang_from_up, _rot
from ..core.gfxmath import _lerp, SHOULDER_OFF_Y, ARM_DIV, ARM_MAX
from .primitives import blit
from .tailtex import draw_game_tail, game_tail_vertices
from ..skins.resolver import SKIN_KEY

PUP_BODY_SY = 0.5  # 幼崽身体贴图的纵向缩放

TAIL_SUBDIV = 4  # 尾巴每段 Catmull-Rom 细分数


def _catmull_weights(t):
    """Catmull-Rom 在 t 处四个控制点的系数，末项附 t 供宽度插值。"""
    t2 = t * t
    t3 = t2 * t
    return (
        0.5 * (-t + 2.0 * t2 - t3),
        0.5 * (2.0 - 5.0 * t2 + 3.0 * t3),
        0.5 * (t + 4.0 * t2 - 3.0 * t3),
        0.5 * (t3 - t2),
        t,
    )


_TAIL_W = tuple(_catmull_weights(j / TAIL_SUBDIV) for j in range(1, TAIL_SUBDIV + 1))


class GraphicsDrawMixin:
    # 能力 / 配件可插入的绘制槽位：over_tail=尾巴、腿、臀之上，近侧臂之下；under_face=头臂之上；
    # behind_face=紧贴脸下（face_pose 已定）；over_face=脸之上
    LAYER_SLOTS = ("over_tail", "under_face", "behind_face", "over_face")

    def add_layer(self, slot, fn):
        self.layers[slot].append(fn)

    def _run_layers(self, slot, p, atlas, ts):
        for fn in self.layers[slot]:
            fn(self, p, atlas, ts)
        for fn in self.acc_layers[slot]:
            fn(self, p, atlas, ts)

    def draw_sprites(self, p, atlas, timeStacker=1.0):
        """图层从后到前：远侧臂、身、尾、腿、臀、近侧臂、头、脸。"""
        ts = timeStacker
        back = 1 if self.facing > 0 else 0
        self._draw_arms(p, atlas, ts, (back,))
        self._draw_body(p, atlas, ts)
        self._draw_tail(p, ts, atlas)
        floor = getattr(self.body, "visual_floor_y", self.body.H)
        p.save()
        p.setClipRect(-1e4, -1e4, 2e4, floor + 1e4)
        self._draw_legs(p, atlas, ts)
        p.restore()
        self._draw_hips(p, atlas)
        self._run_layers("over_tail", p, atlas, ts)
        self._draw_arms(p, atlas, ts, (1 - back,))
        self._draw_head(p, atlas, ts)
        self._run_layers("under_face", p, atlas, ts)
        self._draw_face(p, atlas, ts)
        self._run_layers("over_face", p, atlas, ts)

    @staticmethod
    def _sd(atlas, frame, side):
        f = getattr(atlas, "sided", None)
        return f(frame, side) if f is not None else frame

    def _motion_side(self, d0x, d0y, d1x, d1y):
        """身/臀不对称朝向：站立看后段横速，爬行看体轴角。"""
        mode = self.bodyMode
        if mode == "Stand":
            vx = self.body.chunk1.vx
            return "L" if vx < -3.0 else ("R" if vx > 3.0 else None)
        if mode == "Crawl":
            ang = _ang_from_up(d0x - d1x, d0y - d1y)
            if -150.0 < ang < -30.0:
                return "L"
            if 30.0 < ang < 150.0:
                return "R"
        return None

    def _draw_tail(self, p, ts=1.0, atlas=None):
        segs = self.tail_segs
        if segs is None or self._tail_hidden:
            return
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)

        cox, coy = getattr(self, "_breath_chest_off", (0.0, 0.0))
        root_x = (d1x * 3.0 + d0x + cox) / 4.0
        root_y = (d1y * 3.0 + d0y + coy) / 4.0

        self._draw_tail_smooth(p, segs, root_x, root_y, ts, atlas)

    def _draw_tail_smooth(self, p, segs, root_x, root_y, ts, atlas=None):
        """原皮：Catmull-Rom 平滑单色尾；皮肤贴图尾：游戏网格。"""
        if self._tail_tex and atlas is not None:
            self._draw_tail_skin(p, segs, root_x, root_y, ts, atlas)
            return
        xs, ys = [root_x], [root_y]
        for g in segs:
            xs.append(g.lx + (g.x - g.lx) * ts)
            ys.append(g.ly + (g.y - g.ly) * ts)
        n = len(segs)
        rad = self._tail_rad
        ws = [self._tail_root] + [rad[i] * segs[i].stretched for i in range(n)]
        ws[n] = 0.0

        cx, cy, cw = [root_x], [root_y], [ws[0]]
        for s in range(n):
            a, d = max(0, s - 1), min(n, s + 2)
            x0, x1, x2, x3 = xs[a], xs[s], xs[s + 1], xs[d]
            y0, y1, y2, y3 = ys[a], ys[s], ys[s + 1], ys[d]
            w0, dw = ws[s], ws[s + 1] - ws[s]
            for b0, b1, b2, b3, t in _TAIL_W:
                cx.append(b0 * x0 + b1 * x1 + b2 * x2 + b3 * x3)
                cy.append(b0 * y0 + b1 * y1 + b2 * y2 + b3 * y3)
                cw.append(w0 + dw * t)
        M = len(cx)
        pts = [None] * (2 * M)  # 左边顺序 + 右边倒序
        for k in range(M):
            kp = k - 1 if k else 0
            kn = k + 1 if k < M - 1 else k
            tx, ty = cx[kn] - cx[kp], cy[kn] - cy[kp]
            tl = math.hypot(tx, ty)
            if tl > 1e-6:
                f = cw[k] / tl
                ox, oy = -ty * f, tx * f
            else:
                ox, oy = -cw[k], 0.0
            pts[k] = QPointF(cx[k] - ox, cy[k] - oy)
            pts[2 * M - 1 - k] = QPointF(cx[k] + ox, cy[k] + oy)

        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        path.setFillRule(Qt.FillRule.WindingFill)  # 防自交留洞
        col = QColor(*self._color("TAIL", self.BODY))
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(col, 0.5))
        p.setBrush(col)
        p.drawPath(path)
        p.restore()

    def _draw_tail_skin(self, p, segs, root_x, root_y, ts, atlas):
        nodes = [(_lerp(sg.lx, sg.x, ts), _lerp(sg.ly, sg.y, ts)) for sg in segs]
        rads = [self._tail_rad[i] * segs[i].stretched for i in range(len(segs))]
        verts = game_tail_vertices((root_x, root_y), nodes, self._tail_root, rads)
        col = QColor(*self._color("TAIL", self.BODY))
        pm = atlas.sprite(SKIN_KEY, "TailTexture", col)
        band = None
        if self._tail_asym:
            # 三条横带的窗口随尾根相对臀部的左右位置滑动
            band = clampf((segs[0].x - self.draw1[0] + 15.0) / 30.0, 0.0, 1.0)
        draw_game_tail(p, verts, pm, band)

    def _draw_arms(self, p, atlas, ts=1.0, which=(0, 1)):
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)

        body_axis = _ang_from_up(d0x - d1x, d0y - d1y)
        cos_axis = abs(math.cos(math.radians(body_axis)))

        anim = getattr(self.body, "animation", None)

        for j in which:
            hand = self.hands[j]
            if hand.mode == "Retracted":
                continue

            hx = _lerp(hand.lx, hand.x, ts)
            hy = _lerp(hand.ly, hand.y, ts)

            if anim in ("ClimbOnBeam", "ZeroGPoleGrab") and hand.reached:
                continue

            sh_spread = 4.5 / (hand.retract_counter + 1.0)
            if anim in ("StandOnBeam", "BeamTip") and self.disbalance <= 40.0:
                sh_spread *= self.disbalance / 40.0
            elif anim == "HangFromBeam":
                sh_spread *= 0.5
            sh_spread *= cos_axis * self.body.stats.shoulder_width

            lx = (-1.0 + 2.0 * j) * sh_spread
            ly = SHOULDER_OFF_Y
            ox, oy = _rot(lx, ly, body_axis)
            sx, sy = d0x + ox, d0y + oy

            dist = math.hypot(sx - hx, sy - hy)
            idx = int(round(clampf(dist / ARM_DIV, 0.0, float(ARM_MAX))))
            element = self._sd(atlas, "PlayerArm" + str(idx), "L" if j == 0 else "R")

            rotation = _ang_from_up(sx - hx, sy - hy) + 90.0

            # scale_y：Crawl 取偏侧号，WallClimb 取朝向，否则叉积符号
            if self.bodyMode == "Crawl":
                scale_y = -1.0 if d0x < d1x else 1.0
            elif self.bodyMode == "WallClimb":
                scale_y = -1.0 if self.facing < 0 else 1.0
            else:
                denom = math.hypot(d0y - d1y, d0x - d1x) or 1.0
                dtl = ((d0y - d1y) * hx - (d0x - d1x) * hy + d0x * d1y - d0y * d1x) / denom
                scale_y = math.copysign(1.0, -dtl) if dtl != 0.0 else 1.0

            blit(
                p,
                atlas,
                element,
                hx,
                hy,
                rotation,
                1.0,
                scale_y,
                self._color("ARMS", self.BODY),
                ax=0.9,
                ay=0.5,
            )

    def _draw_hand_grips(self, p, atlas, ts=1.0):
        """抓握精灵，须在 draw_sprites 与画杆之后单独调。"""
        anim = getattr(self.body, "animation", None)
        grip_elem = (
            "OnTopOfTerrainHand"
            if anim in ("ClimbOnBeam", "ZeroGPoleGrab")
            else "OnTopOfTerrainHand2"
            if anim in ("HangFromBeam", "GetUpOnBeam")
            else None
        )
        if grip_elem is None:
            return
        for j in range(2):
            hand = self.hands[j]
            if hand.mode == "Retracted" or not hand.reached:
                continue
            hx = _lerp(hand.lx, hand.x, ts)
            hy = _lerp(hand.ly, hand.y, ts)
            gy = hy - (0.0 if anim in ("ClimbOnBeam", "ZeroGPoleGrab") else 3.0)
            scale_x = -1.0 if j == 1 else 1.0
            blit(
                p,
                atlas,
                self._sd(atlas, grip_elem, "L" if j == 0 else "R"),
                hx,
                gy,
                0.0,
                scale_x,
                1.0,
                self._color("ARMS", self.BODY),
                ax=0.5,
                ay=0.5,
            )

    def _draw_body(self, p, atlas, ts=1.0):
        """画身体，并算好呼吸偏移和臀的姿态（臀在腿之后由 _draw_hips 画）。"""
        d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
        d0y = _lerp(self._last_draw0[1], self.draw0[1], ts)
        d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
        d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)
        draw0 = [d0x, d0y]
        draw1 = [d1x, d1y]
        sleep = self.sleep_curl
        body_axis = _ang_from_up(draw0[0] - draw1[0], draw0[1] - draw1[1])

        breath = self.body.breath_phase(ts)
        ddx, ddy = draw0[0] - draw1[0], draw0[1] - draw1[1]
        d = math.hypot(ddx, ddy) or 1.0
        ux, uy = ddx / d, ddy / d
        upright = clampf((abs(uy) - 0.3) / 0.2, 0.0, 1.0)
        fatigue = self.body.aerobic
        heave = clampf((fatigue - 0.5) / 0.5, 0.0, 1.0)
        swing = 2.0 * breath - 1.0
        chest_h = swing * heave * 0.5
        head_h = swing * (heave**1.5) * 0.75
        self._breath_head_off = (-ux * head_h, -uy * head_h)
        chest_x = draw0[0] + ux * chest_h
        chest_y = draw0[1] + uy * chest_h
        self._breath_chest_off = (ux * chest_h, uy * chest_h)
        breath_bob = _lerp(0.5, 1.0, fatigue) * breath * (1.0 - upright)
        body_x = chest_x
        body_y = chest_y + 4.0 * sleep - breath_bob  # y↓ 睡眠下沉+起伏
        body_rot = body_axis
        body_sx = self.body.stats.body_width + _lerp(_lerp(-0.05, 0.05, breath) * upright, 0.15, sleep)
        body_sy = PUP_BODY_SY if self.pup else 1.0  # 竖直呼吸走 body_y
        side = self._motion_side(d0x, d0y, d1x, d1y)
        blit(
            p,
            atlas,
            self._sd(atlas, "BodyA", side),
            body_x,
            body_y,
            body_rot,
            body_sx,
            body_sy,
            self._color("BODY", self.BODY),
            ax=0.5,
            ay=0.2105263,
        )

        hip_x = (draw1[0] * 2.0 + chest_x) / 3.0
        hip_y = (draw1[1] * 2.0 + chest_y) / 3.0 + 3.0 * sleep
        tail0 = self.tail_segs[0] if self.tail_segs is not None else None
        if tail0 is not None:
            t0x = _lerp(tail0.lx, tail0.x, ts)
            t0y = _lerp(tail0.ly, tail0.y, ts)
            hip_rot = _ang_from_up(t0x - chest_x, t0y - chest_y)
        else:
            hip_rot = body_axis
        hip_sx = self.body.stats.hip_width + sleep * 0.2 + 0.05 * breath
        hip_sy = 1.0 + sleep * 0.2
        self._hip_pose = (side, hip_x, hip_y, hip_rot, hip_sx, hip_sy)

    def _draw_hips(self, p, atlas):
        side, hip_x, hip_y, hip_rot, hip_sx, hip_sy = self._hip_pose
        blit(
            p,
            atlas,
            self._sd(atlas, "HipsA", side),
            hip_x,
            hip_y,
            hip_rot,
            hip_sx,
            hip_sy,
            self._color("HIPS", self.BODY),
            ax=0.5,
            ay=0.5,
        )

    def _draw_legs(self, p, atlas, ts=1.0):
        if self.bodyMode == "Swimming" and getattr(self.body, "swim_mode", None) == "deep":
            return
        x = _lerp(self.legs.lx, self.legs.x, ts)
        y = _lerp(self.legs.ly, self.legs.y, ts)

        lx, ly = self.legs_dir
        rotation = _ang_from_up(-lx, -ly)

        # 仅部分分支写 ±flip，其余沿用上帧
        facing_sx = 1.0 if self.facing > 0 else -1.0

        af = self.anim_frame
        if self.bodyMode == "ClimbingOnBeam":
            anim = getattr(self.body, "animation", None)
            if anim == "BeamTip":
                element = "LegsAPole"
            elif anim == "StandOnBeam":
                element = "LegsAOnPole" + str(af if af < 7 else 0)
                self._legs_scale_x = facing_sx
            elif anim in ("HangFromBeam", "GetUpOnBeam", "GetUpToBeamTip"):
                element = self._leg_air_frame
            else:
                element = "LegsAVerticalPole"
                self._legs_scale_x = facing_sx
                d1y = _lerp(self._last_draw1[1], self.draw1[1], ts)
                y = clampf(y, d1y - 4.0, d1y + 6.0)
        elif self.bodyMode == "Stand":
            if self.is_moving():
                n = len(self._leg_walk_frames)
                element = self._leg_walk_frames[af % n]
            else:
                element = self._leg_walk_frames[0]
            self._legs_scale_x = facing_sx
        elif self.bodyMode == "Crawl":
            if self.is_moving():
                n = len(self._leg_crawl_frames)
                element = self._leg_crawl_frames[(af // 2) % n]
            else:
                element = self._leg_crawl_frames[0]
            self._legs_scale_x = facing_sx
        elif self.bodyMode == "WallClimb":
            element = "LegsAWall"
            self._legs_scale_x = facing_sx
        else:
            element = self._leg_air_frame

        color = self._color("LEGS", self.BODY)
        element = self._sd(atlas, element, "L" if self._legs_scale_x < 0 else "R")
        blit(p, atlas, element, x, y, rotation, self._legs_scale_x, 1.0, color, ax=0.5, ay=0.75)

    def _draw_head(self, p, atlas, ts=1.0):
        hx_r, hy_r, head_ang = self.head_pose_at(ts)
        frame_idx = self._head_frame_index(head_ang)
        frames = self._head_frames or [self.fam["head"][1] + "0"]
        frame_idx = min(max(frame_idx, 0), len(frames) - 1)
        element = frames[frame_idx]

        scale_x = self.head_scale_x

        s_curl = self.sleep_curl
        if s_curl > 0.0:
            d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
            d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
            side = 1.0 if d0x >= d1x else -1.0
            head_ang = _lerp(head_ang, 45.0 * side, s_curl)
            hx_r += side * 2.0 * s_curl
            hy_r -= 1.0 * s_curl

        blit(
            p,
            atlas,
            self._sd(atlas, element, "L" if scale_x < 0 else "R"),
            hx_r,
            hy_r,
            head_ang,
            scale_x * self.body.stats.head_width,
            1.0,
            self._color("HEAD", self.BODY),
            ax=0.5,
            ay=0.5,
        )

    def _draw_face(self, p, atlas, ts=1.0):
        b = self.body

        hx_i, hy_i, head_ang = self.head_pose_at(ts)
        if self.sleep_curl > 0.0:
            d0x = _lerp(self._last_draw0[0], self.draw0[0], ts)
            d1x = _lerp(self._last_draw1[0], self.draw1[0], ts)
            side = 1.0 if d0x >= d1x else -1.0
            hx_i += side * 2.0 * self.sleep_curl
            hy_i -= 1.0 * self.sleep_curl
        ox, oy = self.face_offset_at(ts)
        fx = hx_i + ox
        fy = hy_i + oy

        rot = head_ang * self.face_rot_k
        sx = self.face_scale_x

        face_color = self._asc_face_color or self._color("FACE", self.EYE)

        face_frames = self._face_frames or [self.fam["face"][1] + "0"]
        blink_frames = self._face_blink_frames or face_frames
        face_a_frames = self._face_a_frames or face_frames
        n_max_a = len(face_a_frames) - 1

        if self.dead:
            element = "FaceDead"
        elif self.stunned:
            element = "FaceStunned"
        elif self.ascension is not None:
            idx = int(clampf(self._face_angle_index(ts), 0, 8))
            element = face_a_frames[min(idx, n_max_a)]
        else:
            if self.blink > 0 or self.sleep_curl > 0.0:
                frames = blink_frames
            else:
                frames = self._face_mirror_frames if sx < 0.0 and self._face_mirror_frames else face_frames
            n_max = len(frames) - 1
            if self.sleep_curl > 0.0:
                awake_idx = 7
                drowsy_idx = int(clampf(int(_lerp(awake_idx, 4.0, self.sleep_curl)), 0, 8))
                idx = int(clampf(int(_lerp(drowsy_idx, 1.0, self.sleep_curl)), 0, 8))
            elif b.bodyMode == "ZeroG":
                idx = 0
            elif b.bodyMode == "Crawl" or (b.bodyMode == "Stand" and b.walking()):
                idx = 4
            else:
                idx = self._face_angle_index(ts)
            idx = int(clampf(idx, 0, 8))
            element = frames[min(idx, n_max)]

        self.face_pose = (element, fx, fy, rot)
        self._run_layers("behind_face", p, atlas, ts)
        element = self._sd(atlas, element, "L" if sx < 0 else "R")
        blit(p, atlas, element, fx, fy, rot, sx, 1.0, face_color, ax=0.5, ay=0.5)
