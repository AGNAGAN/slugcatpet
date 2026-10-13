"""跳跃转移链分派（控制路径专用，y↓）；degvec 返回 y↑ 向量，取 vy 时翻号。"""

from __future__ import annotations

from ..core.units import lerp, inv_lerp
from . import vmath


def dispatch(body, inp0) -> None:
    """郊狼窗口与跳跃预输入均>0 时按优先级分派转移；否则无操作。"""
    if not (body._ctrl_can_jump > 0 and body._ctrl_want_jump > 0):
        return
    body._ctrl_can_jump = 0
    body._ctrl_want_jump = 0
    body.aerobic_increase(body.stats.jump_aerobic)
    c0, c1 = body.chunk0, body.chunk1
    a = body.animation
    rd = body._ctrl_roll_direction
    flip = body.facing

    if a == "Roll":
        _roll_to_rocket(body, c0, c1, rd)
        return
    if a == "BellySlide":
        _belly_to_flip_or_rocket(body, c0, c1, rd, inp0)
        return

    if a == "DownOnFours" and c1.on_floor and inp0.downDiagonal == flip:
        body.animation = "BellySlide"
        body._ctrl_roll_direction = flip
        body._ctrl_roll_counter = 0
        body.standing = False
        return

    body.animation = None

    if body.standing:
        if 0 < body._ctrl_slide_counter < 10:
            _flip_skid_jump(body, c0, c1)
        else:
            _standard_jump(body, c0, c1)
    else:
        _crouch_jump(body, c0, c1, inp0)


def _flip_skid_jump(body, c0, c1) -> None:
    """站立急刹翻跳（y 翻），按种族取速度。"""
    s = body.stats
    sd = body._ctrl_slide_direction
    c0.vy = s.flip_head
    c1.vy = s.flip_feet
    c0.vx *= 0.5
    c1.vx *= 0.5
    c0.vx -= sd * 4.0
    body.jump_boost = s.flip_boost
    body.animation = "Flip"
    body._ctrl_slide_counter = 0


def _roll_to_rocket(body, c0, c1, rd) -> None:
    c1.vx = 0.0
    c1.vy = 0.0
    c1.x += 5.0 * rd
    c1.y -= 5.0
    c0.x = c1.x + 5.0 * rd
    c0.y = c1.y - 5.0
    t = inv_lerp(0.0, 25.0, body._ctrl_roll_counter)
    ang = rd * lerp(60.0, 35.0, t)
    speed = lerp(9.5, 13.1, t)
    vx, vy = vmath.degvec(ang)  # y↑ 向量，此时未翻
    vx *= speed
    vy *= speed
    m = body.stats.roll_rocket_vx_mult
    c0.vx = vx * m
    c0.vy = -vy  # y 翻
    c1.vx = vx * m
    c1.vy = -vy
    body.animation = "RocketJump"
    body._ctrl_roll_direction = 0


def _belly_to_flip_or_rocket(body, c0, c1, rd, inp0) -> None:
    """BellySlide 跳出：whiplash||反向x → Flip 路径1（后空翻）；否则 RocketJump 路径2（滑铲火箭）。"""
    s = body.stats
    if body._ctrl_whiplash or inp0.x == -rd:
        body.animation = "Flip"
        body.standing = True
        c0.y -= 14.0  # 无砖格，不做原版的后退瞬移
        c0.vx = rd * (-s.backflip_vx)
        c0.vy = s.backflip_c0_vy
        c1.vx = rd * (-s.backflip_vx)
        c1.vy = s.backflip_c1_vy
        body._ctrl_roll_direction = -rd
        body._ctrl_whiplash = False
        body.jump_boost = 0.0
    else:
        launch_vx = s.belly_rocket_vx
        launch_vy = s.belly_rocket_vy
        c1.x += 5.0 * rd
        c1.y -= 5.0
        c0.x = c1.x + 5.0 * rd
        c0.y = c1.y - 5.0
        c1.vx = rd * launch_vx
        c1.vy = -launch_vy
        c0.vx = rd * launch_vx
        c0.vy = -launch_vy
        body.animation = "RocketJump"
        body._ctrl_rocket_from_belly = True
        body._ctrl_roll_direction = 0


def _standard_jump(body, c0, c1) -> None:
    """站立跳（y 翻），按种族取速度，不碰 vx。"""
    body.feet_stuck = None
    body.crawl_anchor = None
    body.crawl_pose = 0.0
    c0.vy = body.stats.jump_head
    c1.vy = body.stats.jump_feet
    body.jump_boost = body.stats.jump_boost


def _crouch_jump(body, c0, c1, inp0) -> None:
    """趴/蹲跳 + 超级扑跳（y 翻），蓄力满 20 触发扑射。"""
    pounce_speed = 1.5
    dir_x = inp0.x
    if body._ctrl_super_launch >= 20:
        body._ctrl_super_launch = 0
        pounce_speed = body.stats.pounce_super
        dir_x = 1 if c0.x > c1.x else -1
        body._ctrl_sim_hold = 6
    c0.y -= 6.0
    if c0.on_floor:
        c0.vy -= 3.0
        if dir_x == 0:
            c0.vy -= 3.0
    c1.vy -= 4.0
    body.jump_boost = 6.0
    if dir_x != 0 and ((c0.x > c1.x) == (dir_x > 0)):
        c0.vx += dir_x * pounce_speed
        c1.vx += dir_x * pounce_speed
