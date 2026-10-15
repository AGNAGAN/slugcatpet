"""手动控制的滑铲、翻滚、翻跳、火箭跳：每帧受力和共用计数器（y↓）。perpendicular 返回的方向是反的，施力时 += 和 -= 对调。"""

from __future__ import annotations
import math

from . import vmath
from ..core.units import lerp

# 手动控制用的计数器和标志，首次用到时建
_SLIDE_DEFAULTS = {
    "_ctrl_roll_direction": 0,  # Roll、BellySlide 的横向方向
    "_ctrl_roll_counter": 0,
    "_ctrl_whiplash": False,  # 滑铲中按了反方向，这时起跳变成 Flip
    "_ctrl_rocket_from_belly": False,  # 这次 RocketJump 由滑铲起跳，落地可接 Roll
    "_ctrl_exit_belly": 0,  # 滑铲时没按滑铲方向的帧数
    "_ctrl_stop_rolling": 0,  # Roll 被顶住的帧数，超过 6 结束
    "_ctrl_super_launch": 0,  # 趴着蓄力的帧数，满 20 超级扑跳
    "_ctrl_sim_hold": 0,  # 超级扑跳后自动按住跳的帧数
    "_ctrl_slide_direction": 0,  # 急刹前的跑动方向，和 roll_direction 分开
    "_ctrl_init_slide_counter": 0,  # 同向跑的帧数，够了反向才会急刹
    "_ctrl_skid_cooldown": 0,  # 急刹冷却，防止左右连按时连续急刹
    "_ctrl_slide_counter": 0,
    "_ctrl_allow_roll": 0,  # 还能落地翻滚的帧数
    "_ctrl_consistent_dd": 0,  # 连续同向 downDiagonal 帧数
    "_ctrl_fall_speed": 0.0,  # 最后一次离地时的下坠速度
    "_ctrl_prev_floor": True,
}

BELLY_PERIOD = 15.0
DEFAULT_DYN = 3.6  # Default bodyMode 跑速上限


def ensure(body) -> None:
    for k, v in _SLIDE_DEFAULTS.items():
        if not hasattr(body, k):
            setattr(body, k, v)


def clear_flags(body) -> None:
    a = body.animation
    if body._ctrl_rocket_from_belly and a != "RocketJump":
        body._ctrl_rocket_from_belly = False
    if body._ctrl_whiplash and a != "BellySlide":
        body._ctrl_whiplash = False


def movement_increments(body) -> None:
    if body._ctrl_roll_direction != 0:
        body._ctrl_roll_counter += 1
        endless = body.animation == "Roll" and _endless_roll(body)
        if body.bodyMode != "Default" or (body._ctrl_roll_counter > 200 and not endless):
            body._ctrl_roll_counter = 0
            body._ctrl_roll_direction = 0


def super_launch_charge(body, move_x, inp0, inp1) -> None:
    c0, c1 = body.chunk0, body.chunk1
    decay_flag = 1 if body._ctrl_super_launch > 0 else 0
    if body.bodyMode == "Crawl" and c0.on_floor and c1.on_floor:
        if move_x == 0 and inp0.y == 0:
            decay_flag = 0
            body._ctrl_want_jump = 0
            if inp0.jmp and body._ctrl_super_launch < 20:
                body._ctrl_super_launch += 1
        if not inp0.jmp and inp1.jmp:
            body._ctrl_want_jump = 1
    # 衰减留到 dispatch 之后，否则扑跳读不到满蓄力
    body._ctrl_sl_decay = decay_flag


def skid_update(body, move_x) -> None:
    c0, c1 = body.chunk0, body.chunk1
    sd = body._ctrl_slide_direction
    if body._ctrl_skid_cooldown > 0:
        body._ctrl_skid_cooldown -= 1
    if body._ctrl_slide_counter > 0:
        body._ctrl_slide_counter += 1
        if body._ctrl_slide_counter > 20 or move_x != -sd:
            body._ctrl_slide_counter = 0
        n = -math.sin(body._ctrl_slide_counter / 20.0 * math.pi * 0.5) + 0.5
        c0.vx += n * 3.5 * sd - sd * (0.8 if n < 0 else 0.5)
        c1.vx += n * 3.5 * sd + sd * 0.5
    elif move_x != 0:
        if move_x == sd:
            if body._ctrl_init_slide_counter < 30:
                body._ctrl_init_slide_counter += 1
        else:
            if (
                body._ctrl_init_slide_counter > body.stats.skid_init_thresh
                and (c0.vx > 0) == (sd > 0)
                and abs(c0.vx) > 1.0
                and body._ctrl_skid_cooldown <= 0
            ):
                body._ctrl_slide_counter = 1
                body._ctrl_skid_cooldown = 20
            else:
                body._ctrl_slide_direction = move_x
            body._ctrl_init_slide_counter = 0
    elif body._ctrl_init_slide_counter > 0:
        body._ctrl_init_slide_counter -= 1


def update_allow_roll(body) -> None:
    if body._ctrl_allow_roll > 0:
        body._ctrl_allow_roll -= 1
    floor = getattr(body, "_floor_h", body.H)
    if (not body.on_floor()) and (floor - body.chunk1.y) > 20.0:
        body._ctrl_allow_roll = 15


def update_consistent_dd(body, inp0, inp1) -> None:
    if inp0.downDiagonal != 0 and inp0.downDiagonal == inp1.downDiagonal:
        body._ctrl_consistent_dd += 1
    else:
        body._ctrl_consistent_dd = 0


def try_land_roll(body, inp0) -> None:
    if inp0.downDiagonal == 0 or body.animation == "Roll":
        return
    speed = body._ctrl_fall_speed
    from_flip = body.animation == "Flip"
    from_rocket_belly = body.animation == "RocketJump" and body._ctrl_rocket_from_belly
    if not (speed > 12.0 or from_flip or from_rocket_belly):
        return
    if body._ctrl_allow_roll <= 0:
        return
    if body._ctrl_consistent_dd <= (1 if speed > 24.0 else 6):
        return
    c0, c1 = body.chunk0, body.chunk1
    if from_rocket_belly:  # 两节身体位置微调（y↓）
        c1.vy -= 3.0
        c1.y -= 3.0
        c0.vy += 3.0
        c0.y += 3.0
    body.animation = "Roll"
    body._ctrl_roll_direction = inp0.downDiagonal
    body._ctrl_roll_counter = 0
    c0.vx = lerp(c0.vx, 9.0 * inp0.x, 0.7)
    c1.vx = lerp(c1.vx, 9.0 * inp0.x, 0.7)
    body.standing = False


def anim_forces(body, move_x, inp0, inp1) -> None:
    a = body.animation
    if a == "BellySlide":
        _belly_slide(body, inp0, inp1)
    elif a == "Roll":
        _roll(body, inp0)
    elif a == "RocketJump":
        _rocket_jump(body)
    elif a == "Flip":
        _flip(body)


def _belly_slide(body, inp0, inp1) -> None:
    """滑铲每帧受力；只按平地算，不处理斜面和穿平台下落。"""
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    rd = body._ctrl_roll_direction
    rc = body._ctrl_roll_counter
    if rc < 6 and not body.stats.belly_no_kick:
        c1.vy -= 2.7
        c1.vx -= 9.1 * rd
    else:
        c1.vy += 0.5
    s = body.stats
    spd = s.belly_slide_spd_tired if body.exhausted else s.belly_slide_spd
    c0.vx += spd * rd * _sin(rc / BELLY_PERIOD)
    c0.vy += 2.3
    for c in (c0, c1):
        if c.cy == 0:
            c.vx *= 0.5
    if inp0.x != rd and inp0.downDiagonal != rd:
        body._ctrl_exit_belly += 1
    else:
        body._ctrl_exit_belly = 0
    if rc > 5 and inp0.x == -rd:
        body._ctrl_whiplash = True
    jmp_edge = inp0.jmp and not inp1.jmp
    if (
        (rc > 8 and body._ctrl_exit_belly > 6)
        or rc > 15
        or (jmp_edge and 0 < rc < body.stats.belly_jump_cancel_window)
    ):
        c0.vy = 0.0
        c1.vy = 0.0
        body._ctrl_roll_direction = 0
        body.animation = None
        body.standing = inp0.y == 1  # pet 无天花板，恒真
        for c in (c0, c1):
            if abs(c.vx) > 8.0:
                c.vx *= 0.5
                c.vy *= 0.5
    else:
        body.standing = False


def _roll(body, inp0) -> None:
    """翻滚每帧受力，只按平地算。"""
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    rd = body._ctrl_roll_direction
    # perp 反号，c0 用 -=、c1 用 +=
    perp_x, perp_y = vmath.perpendicular(c1.x, c1.y, c0.x, c0.y)
    c0.vx *= 0.9
    c0.vy *= 0.9
    c1.vx *= 0.9
    c1.vy *= 0.9
    body.aerobic_increase(0.01)
    torque_x = perp_x * 2.0 * rd
    torque_y = perp_y * 2.0 * rd
    c0.vx -= torque_x
    c0.vy -= torque_y
    c1.vx += torque_x
    c1.vy += torque_y
    stuck = c0.cx == rd or c1.cx == rd
    if body.walk_min is not None:  # 走位边界夹住也算顶住
        edge = body.walk_max if rd > 0 else body.walk_min
        stuck = stuck or (c0.x - edge) * rd >= 0.0
    if c0.on_floor or c1.on_floor:
        c0.vx += 1.1 * rd
        c1.vx += 1.1 * rd
        body._ctrl_can_jump = max(getattr(body, "_ctrl_can_jump", 0), 5)
    else:
        stuck = True
    body._ctrl_stop_rolling = (body._ctrl_stop_rolling + 1) if stuck else 0
    rc = body._ctrl_roll_counter
    head_above = c0.y < c1.y
    capped = not _endless_roll(body)
    if (
        (
            ((rc > 15 and inp0.y > -1 and inp0.downDiagonal == 0) or (rc > 30 and capped) or inp0.x == -rd)
            and head_above
        )
        or (rc > 60 and capped)
        or body._ctrl_stop_rolling > 6
    ):
        body._ctrl_roll_direction = 0
        body.animation = None
        body.standing = inp0.y > -1


def _endless_roll(body) -> bool:
    return body.endless_roll and not body.exhausted


def _rocket_jump(body) -> None:
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    body.standing = False
    c1.vx *= 0.99
    c1.vy *= 0.99
    nx, ny = vmath.normalize(c0.vx, c0.vy)  # 速度已是 pet 空间，直接归一
    c0.vx += nx
    c0.vy += ny
    c1.vx -= nx
    c1.vy -= ny
    c0.vy -= 0.1
    c1.vy -= 0.1
    if c1.cx != 0 or c1.cy != 0:
        body.animation = None


def _flip(body) -> None:
    """翻跳每帧受力：力矩方向取 _ctrl_slide_direction 而不是 _ctrl_roll_direction，碰到东西就结束。"""
    c0, c1 = body.chunk0, body.chunk1
    body.bodyMode = "Default"
    sd = getattr(body, "_ctrl_slide_direction", 0)  # 从滑铲转来的 Flip 沿用上次的值
    mult = 0.38  # 急刹翻跳和普通翻跳用同一力矩，免得转太多圈
    torque_x, torque_y = vmath.perpendicular(c1.x, c1.y, c0.x, c0.y)
    k = sd * mult
    torque_x *= k
    torque_y *= k
    # perp 反号，c0 用 +=、c1 用 -=
    c0.vx += torque_x
    c0.vy += torque_y
    c1.vx -= torque_x
    c1.vy -= torque_y
    body.standing = False
    for c in (c0, c1):
        if c.cx != 0 or c.cy != 0:
            body.animation = None
            body.standing = c0.y < c1.y
            break


def _sin(x):
    return math.sin(x * math.pi)
