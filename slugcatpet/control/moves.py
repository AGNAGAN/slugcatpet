"""手动控制的每 tick 移动：站、跑、跳的入口。"""

from __future__ import annotations

from ..core import creature as cr
from . import moves_posture as mp
from . import moves_slide as ms
from . import moves_jump as mj
from . import moves_pole as mpole


def ctrl_movement_update(body):
    c0, c1 = body.chunk0, body.chunk1
    inp = body._ctrl_input
    inp0, inp1 = inp[0], inp[1]
    body._ctrl_was_zerog = False
    if mpole.from_zerog(body):
        return

    # 离地宽限 _ctrl_can_jump 和跳跃预输入 _ctrl_want_jump，与 body.canJump 无关
    if getattr(body, "_ctrl_want_jump", None) is None:
        body._ctrl_want_jump = 0
        body._ctrl_can_jump = 0
    if body._ctrl_want_jump > 0:
        body._ctrl_want_jump -= 1
    elif inp0.jmp and not inp1.jmp:
        body._ctrl_want_jump = 5
    if body._ctrl_can_jump > 0:
        body._ctrl_can_jump -= 1
    tongue = getattr(body, "_ctrl_tongue", None)
    if tongue is not None:
        tongue.update(body, inp0, inp1, body._ctrl_can_jump)

    ms.ensure(body)
    ms.clear_flags(body)
    if body._ctrl_sim_hold > 0:
        body._ctrl_sim_hold -= 1

    ms.update_allow_roll(body)
    ms.update_consistent_dd(body, inp0, inp1)
    now_floor = body.on_floor()
    if not now_floor:
        body._ctrl_fall_speed = abs(c1.vy)  # 下坠速度，落地时估算冲击用
        body.crawl_anchor = None  # 离地时清掉趴锚，免得落地被旧锚拖回
    if now_floor and not body._ctrl_prev_floor:
        ms.try_land_roll(body, inp0)
    body._ctrl_prev_floor = now_floor

    move_x = inp0.x
    # 蓄力过半且一直按着跳时不能横移
    if getattr(body, "_ctrl_super_launch", 0) > 10 and inp0.jmp and inp1.jmp and inp[2].jmp and inp0.y < 1:
        move_x = 0
    if move_x > 0:
        body.facing = 1
    elif move_x < 0:
        body.facing = -1
    body.move_dir = move_x  # 给 _gait_update 用，否则脸和腿会按静止处理

    mp.toggle_standing(body, inp0, inp1)

    target_sink = 1.0 if not body.standing else 0.0
    body.hip_sink += (target_sink - body.hip_sink) * cr.HIP_SINK_EASE
    body._floor_h = body.H + body.hip_sink * body.crawl_sink

    if body.standing or move_x != 0:
        body.crawl_anchor = None
        body.crawl_pose = max(0.0, body.crawl_pose - 0.08)

    flag = move_x == 0 and body.standing and c1.on_floor
    if body.feet_stuck is not None and not flag:
        body.feet_stuck = None
    elif body.feet_stuck is None and flag:
        body.feet_stuck = [c1.x, body._floor_h - c1.rad]
    if body.feet_stuck is not None:
        body.feet_stuck[0] += (c1.x - body.feet_stuck[0]) * cr.FEET_EASE
        body.feet_stuck[1] = body._floor_h - c1.rad
        if not c1.pinned:
            c1.x = body.feet_stuck[0]
            c1.y = body.feet_stuck[1]

    mp.update_counters(body)
    on_ground = body.on_floor()

    # bodyMode 按身体位置判断而不看 standing，姿势过渡时跟着位置走
    if not on_ground:
        body.bodyMode = "Default"
    elif (c0.y < c1.y - 3.0) and body.animation != "CrawlTurn" and not c0.on_floor:
        body.bodyMode = "Stand"
    else:
        body.bodyMode = "Crawl"

    if mpole.try_grab(body, inp0, inp1):
        return  # 抓住杆，由杆上动作接管

    mp.anim_forces(body, move_x)  # 可能改 bodyMode、清 animation
    ms.anim_forces(body, move_x, inp0, inp1)  # 可能把 bodyMode 设为 Default
    mp.crawl_turn_delay(body)
    mp.posture_entry(body, move_x)
    ms.movement_increments(body)

    if body._ctrl_roll_direction != 0:  # 翻滚、滑铲时横向按翻滚方向
        move_x = body._ctrl_roll_direction

    if on_ground:
        body._ctrl_can_jump = 5

    dyn0 = cr.RUN_UPPER * body.stats.runspeed_fac
    dyn1 = cr.RUN_LOWER * body.stats.runspeed_fac
    if body.bodyMode == "Stand":
        c0.vy += cr.STAND_HEAD
        c1.vy += cr.STAND_FEET
        ms.skid_update(body, move_x)
    elif body.bodyMode == "Default" and body.standing:
        c0.vy += cr.DEF_STAND_HEAD
        c1.vy += cr.DEF_STAND_FEET
    elif body.bodyMode == "Crawl":
        dyn0 = dyn1 = cr.CRAWL_SPEED
        if inp0.y != 0:
            dyn0 = dyn1 = cr.CRAWL_SLOW
        if (move_x > 0) == (c0.x < c1.x):
            dyn0 *= 0.75
            dyn1 *= 0.75
        if move_x == 0 and c1.on_floor and not c0.pinned and not c1.pinned and body._jump_pending is None:
            body._crawl_pose()  # 不把头投影到连接距离的圆上，否则蓄力的着地判定会出错

    if body._ctrl_roll_direction != 0:  # 翻滚、滑铲时用默认跑速上限
        dyn0 = dyn1 = ms.DEFAULT_DYN
    dyn0 *= body.slow_fac(0.5)
    dyn1 *= body.slow_fac(0.5)
    accel = cr.H_ACCEL * body.slow_fac(0.4)
    ms.super_launch_charge(body, move_x, inp0, inp1)

    if body.walk_speed_target is not None:
        dyn0 = min(dyn0, body.walk_speed_target)
        dyn1 = min(dyn1, body.walk_speed_target)
    grounded = c0.on_floor or c1.on_floor
    for c, dyn in ((c0, dyn0), (c1, dyn1)):
        if c.pinned:
            continue
        if move_x < 0:
            step = accel
            if c.vx - step < -dyn:
                step = dyn + c.vx
            if step > 0:
                c.vx -= step
        elif move_x > 0:
            step = accel
            if c.vx + step > dyn:
                step = dyn - c.vx
            if step > 0:
                c.vx += step
        if grounded:
            target = max(-dyn, min(dyn, c.vx)) if move_x != 0 else 0.0
            c.vx += (target - c.vx) * cr.SKID_DAMP

    # 按当前动作选跳法：Roll、BellySlide、DownOnFours、站立跳、蹲跳
    want_pre = body._ctrl_want_jump  # dispatch 会清零，先记下给工匠的钩子用
    can_pre = body._ctrl_can_jump
    mj.dispatch(body, inp0)

    # 蓄力衰减放在 dispatch 之后，扑跳才读得到满蓄力
    if getattr(body, "_ctrl_sl_decay", 0) > 0 and body._ctrl_super_launch > 0:
        body._ctrl_super_launch -= 1

    # 按住跳键跳得更高：离地且按着才加，松开就停
    if on_ground:
        pass
    elif body.jump_boost > 0 and (
        inp0.jmp
        or body._ctrl_sim_hold > 0
        or (getattr(body, "_ctrl_pyro", None) is not None and inp0.pckp and body._ctrl_pyro_jumped)
    ):
        body.jump_boost -= cr.JUMPBOOST_DECAY
        kick = (body.jump_boost + 1) * cr.JUMPBOOST_GAIN
        c0.vy -= kick
        c1.vy -= kick
        if body.jump_boost < 0:
            body.jump_boost = 0.0
    else:
        body.jump_boost = 0.0

    if body.walk_min is not None and move_x != 0:
        for c in (c0, c1):
            if c.x < body.walk_min:
                c.x = body.walk_min
            elif c.x > body.walk_max:
                c.x = body.walk_max

    # 能力的操控钩子（工匠、舌头），没有时为 None
    pyro = getattr(body, "_ctrl_pyro", None)
    if pyro is not None:
        pyro.update(body, inp0, inp1, want_pre, can_pre)
