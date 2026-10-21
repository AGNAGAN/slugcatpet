"""手动控制的贴墙（WallClimb）：左右边缘当墙，贴墙下滑和蹬墙跳（y↓）。

- 墙：走位边界（没有时是屏幕边缘），一节顶到这里就算碰着这边的墙。
- 进入：头碰着墙且按着朝墙的方向；先按着地 / 空中定 bodyMode，再由它覆盖，所以地上顶墙也算。
- 贴墙时头高于臀：可以起跳，并记下离墙宽限（_ctrl_can_wall_jump，符号为蹬开的方向）。
- 下滑：墙不给摩擦；两节都挨着墙时每 tick 往上抵掉一段位移，贴墙越久抵得越少，直到 0。
- 蹬墙跳：离地面一格以内或臀泡在水里时竖直上跳；否则斜着蹬开，之后一小段时间横向输入锁成蹬开的方向。
"""

from __future__ import annotations

from ..core import chunkphys as cp
from ..core.units import lerp
from ..planning.climbmoves import TILE  # 原版按砖格判断「旁边 / 下面是实心」，这里换成离墙或地面不到一格

WALL_JUMP_GRACE = 15
SLIDE_TICKS = 30.0
SLIDE_LIFT = 0.8
JUMP_STUN = 8
UP_LIFT = 10.0  # 竖直上跳时先上提的距离
UP_AIR_FAC = 0.7  # 两节都没着地时竖直上跳打折
TOUCH_EPS = 0.5


def tick_counters(body) -> None:
    """每 tick 在移动之前调（不论这一 tick 走不走移动），按上一 tick 的 bodyMode 计数。"""
    body._ctrl_wall_slide = body._ctrl_wall_slide + 1 if body.bodyMode == "WallClimb" else 0
    cwj = body._ctrl_can_wall_jump
    body._ctrl_can_wall_jump = cwj - 1 if cwj > 0 else (cwj + 1 if cwj < 0 else 0)
    js = body._ctrl_jump_stun
    body._ctrl_jump_stun = js - 1 if js > 0 else (js + 1 if js < 0 else 0)


def contact(body, c) -> int:
    """这一节碰着哪边的墙：+1 右，-1 左，0 没碰。"""
    if c.cx != 0:
        return c.cx
    if c.x >= _limit(body, c, 1) - TOUCH_EPS:
        return 1
    if c.x <= _limit(body, c, -1) + TOUCH_EPS:
        return -1
    return 0


def try_enter(body, inp0) -> None:
    """头碰着墙且按着朝墙方向时把 bodyMode 设为 WallClimb；被带着、被拎着时不进。"""
    c0, c1 = body.chunk0, body.chunk1
    if inp0.x == 0 or contact(body, c0) != inp0.x:
        return
    if body.ride is not None or c0.pinned or c1.pinned:
        return
    body.bodyMode = "WallClimb"


def update(body, inp0) -> None:
    """贴墙这一 tick 的跳跃资格、下滑和水里的臀部上浮。"""
    c0, c1 = body.chunk0, body.chunk1
    if c0.y < c1.y:
        if inp0.x != 0 and inp0.x == contact(body, c0):
            body._ctrl_can_wall_jump = -WALL_JUMP_GRACE * inp0.x
        body._ctrl_can_jump = 1
    if inp0.x != 0 and _by_wall(body, c0, inp0.x) and _by_wall(body, c1, inp0.x):
        t = body._ctrl_wall_slide / SLIDE_TICKS
        lift = cp.GRAVITY * body.room_gravity * lerp(SLIDE_LIFT, 0.0, t)
        c0.y -= lift
        c1.y -= lift
    c1.vy -= body.hip_sub * body.room_gravity


def jump_direction(body) -> int:
    """在墙上起跳时蹬开的方向。"""
    cwj = body._ctrl_can_wall_jump
    if cwj != 0:
        return 1 if cwj > 0 else -1
    side = contact(body, body.chunk0)
    return -side if side != 0 else -body.facing


def try_grace_jump(body, inp0) -> None:
    """刚离墙还在宽限内、按了跳且没按着朝墙方向时蹬墙跳，并清掉跳跃预输入。"""
    cwj = body._ctrl_can_wall_jump
    if cwj == 0 or body._ctrl_want_jump <= 0:
        return
    d = 1 if cwj > 0 else -1
    if inp0.x == -d:
        return
    wall_jump(body, d)
    body._ctrl_want_jump = 0


def wall_jump(body, d: int) -> None:
    """往 d 方向蹬墙跳；贴着地面或臀泡在水里时改成竖直上跳。速度按猫种取，累倒时按气喘打折。"""
    s = body.stats
    c0, c1 = body.chunk0, body.chunk1
    k = 1.0 - 0.5 * body.aerobic if body.exhausted else 1.0
    body.feet_stuck = None
    if _near_floor(body, c1) or _near_floor(body, c0) or body.hip_sub > 0.1:
        if not c0.on_floor and not c1.on_floor and body.submersion == 0.0:
            k *= UP_AIR_FAC
        c0.vy = s.wall_up_head * k
        c1.vy = s.wall_up_feet * k
        lift = UP_LIFT * min(1.0, k)
        c0.y -= lift
        c1.y -= lift
        body.jump_boost = 0.0
    else:
        c0.vy = s.wall_jump_head_vy * k
        c1.vy = s.wall_jump_feet_vy * k
        c0.vx = s.wall_jump_head_vx * k * d
        c1.vx = s.wall_jump_feet_vx * k * d
        body.standing = True
        body.jump_boost = s.wall_jump_boost
        body._ctrl_jump_stun = JUMP_STUN * d
    body._ctrl_can_wall_jump = 0


def _limit(body, c, side: int) -> float:
    """这一节中心能到的最左 / 最右处。"""
    if side > 0:
        lim = body.W - c.rad
        return lim if body.walk_max is None else min(lim, body.walk_max)
    lim = c.rad
    return lim if body.walk_min is None else max(lim, body.walk_min)


def _by_wall(body, c, side: int) -> bool:
    return (_limit(body, c, side) - c.x) * side + c.rad < TILE


def _near_floor(body, c) -> bool:
    return body._floor_h - c.y < TILE
