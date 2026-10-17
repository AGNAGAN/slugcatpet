"""手动控制的跳跃：按当前动作选跳法（y↓）。degvec 返回 y↑ 向量，算 vy 时取反。"""

from __future__ import annotations

from ..core.units import lerp, inv_lerp
from . import vmath


def dispatch(body, inp0) -> None:
    """离地宽限和跳跃预输入都没过期时，按优先级选一种跳法起跳。"""
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
    """站立急刹后的翻跳，速度按猫种取。"""
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
    speed = lerp(9.5, 13.1, t) * body.stats.roll_rocket_spd_fac
    vx, vy = vmath.degvec(ang)  # y↑ 向量
    vx *= speed
    vy *= speed
    m = body.stats.roll_rocket_vx_mult
    c0.vx = vx * m
    c0.vy = -vy  # 换成 y↓
    c1.vx = vx * m
    c1.vy = -vy
    body.animation = "RocketJump"
    body._ctrl_roll_direction = 0


def _belly_to_flip_or_rocket(body, c0, c1, rd, inp0) -> None:
    """腹滑中起跳：whiplash 或反向按方向时后空翻（Flip），否则滑铲火箭跳（RocketJump）。"""
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
    """站立跳，速度按猫种取，不改 vx。"""
    body.feet_stuck = None
    body.crawl_anchor = None
    body.crawl_pose = 0.0
    c0.vy = body.stats.jump_head
    c1.vy = body.stats.jump_feet
    body.jump_boost = body.stats.jump_boost


def _crouch_jump(body, c0, c1, inp0) -> None:
    """趴着或蹲着起跳；蓄力满 20 时变成超级扑跳。"""
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
