"""手动操控时的杆上动作：按键切换抓杆、爬、吊、翻、站和起跳。"""

from __future__ import annotations

from ..planning import climbmoves as M
from . import moves_jump as mj

V_GRAB = 10.0  # 头和竖杆在同一格就抓得到
V_GRAB_STILL = 30.0  # 站在地上不按左右时，相邻一格的竖杆也抓得到
H_GRAB = 10.0  # 头扫过横杆那格就抓得到
TIP_GRAB = 20.0  # 臀在杆顶上方一格内按上就站上杆尖
REACH_UP = (32.0, 52.0)  # 站在横杆上按上能抓到的上方横杆高度差
CROSS = 10.0  # 头或臀在交叉横杆那格里
SLIDE_UP = 17  # 竖杆上按上加跳往上窜的 tick 数
TIP_RUN_CAP = 3.6  # 站杆尖时按左右的跑速上限
NO_GRAB_TICKS = 5  # 离杆后这么多 tick 内不再抓杆
SKIP_TOL = (7.5, 22.5)  # 踩杆再跳：臀离横杆这么近才算卡准（普通 / 宽松）
SKIP_CD = (6, 3)  # 踩杆再跳后这么多 tick 内不能再踩
SKIP_MISS = (12, 6)  # 没卡准时的罚时：普通累加，宽松直接设为该值
SKIP_MISS_MAX = 30


def _bars(body):
    fn = getattr(body, "_ctrl_bars", None)
    return fn() if fn is not None else ()


def _press(inp0, inp1, key, v):
    return getattr(inp0, key) == v and getattr(inp1, key) != v


def _take_jump(body):
    """跳跃预输入还在就消耗掉并返回 True。"""
    if body._ctrl_want_jump > 0:
        body._ctrl_want_jump = 0
        body._ctrl_jump_taken = True
        return True
    return False


def _leave(body):
    M.release(body)
    body._ctrl_bar = None
    body._ctrl_pull = None
    body._ctrl_nograb = NO_GRAB_TICKS
    body._ctrl_can_jump = 0
    body.standing = True


def _lerpmap(v, a, b, c, d, exp):
    t = min(1.0, max(0.0, (v - a) / (b - a)))
    return c + (d - c) * t**exp


# 抓杆


def try_grab(body, inp0, inp1):
    """不在杆上时按上：抓横杆、竖杆或站上杆尖；抓住返回 True。"""
    if body._ctrl_nograb > 0:
        body._ctrl_nograb -= 1
        return False
    if inp0.y <= 0 or body.room_gravity <= 0.0 or body.swimming:
        return False
    if body.bodyMode not in ("Default", "Stand", "WallClimb"):
        return False
    c0, c1 = body.chunk0, body.chunk1
    bars = _bars(body)
    if _press(inp0, inp1, "y", 1):
        for bar in bars:
            if bar.vertical and abs(c1.x - bar.x) < CROSS and bar.y0 - TIP_GRAB <= c1.y < bar.y0:
                _attach(body, bar, "BeamTip")
                c1.vx = c1.vy = 0.0
                return True
    hit = None
    ly = getattr(c0, "last_y", c0.y)
    lo, hi = min(ly, c0.y) - H_GRAB, max(ly, c0.y) + H_GRAB
    for bar in bars:
        if not bar.vertical and lo <= bar.y <= hi and bar.x0 <= c0.x <= bar.x1:
            hit = ("H", bar)
            break
    still = c1.on_floor and inp0.x == 0
    reach = V_GRAB_STILL if still else V_GRAB
    best = None
    for bar in bars:
        if bar.vertical and bar.y0 <= c0.y <= bar.y1:
            d = abs(c0.x - bar.x)
            if d < reach and (best is None or d < best[0]):
                best = (d, bar)
    if best is not None:
        hit = ("V", best[1])
    if hit is None:
        return False
    k, bar = hit
    if k == "H":
        _attach(body, bar, "HangFromBeam")
        M.grab_beam(body, bar, c0.x)
        c1.vy *= 0.25
    else:
        if abs(c0.vx) > 5.0 and abs(c0.x - bar.x) < V_GRAB:
            facing = 1 if c0.vx > 0 else -1
        else:
            facing = 1 if c0.x >= bar.x else -1
        _attach(body, bar, "ClimbOnBeam")
        M.attach_vertical(body, bar, facing)
    return True


def _attach(body, bar, anim):
    body.stop_walk()
    body.feet_stuck = None
    body.crawl_anchor = None
    body.jump_boost = 0.0
    body._ctrl_can_jump = 0
    body._ctrl_bar = bar
    body._ctrl_pull = None
    body._ctrl_slide_up = 0
    M.grip(body, bar)
    body.animation = anim


def pole_skip(body, inp0):
    """空中臀经过横杆时按住左右再按跳：踩着杆再跳一次，没卡准加罚时；跳了返回 True。"""
    c0, c1 = body.chunk0, body.chunk1
    s = body.stats
    loose = 1 if s.pole_skip_loose else 0
    fall = abs(c1.last_y - c1.y)
    if loose:
        ok = fall < 50.0 and c1.vy > -15.0 and body.animation in (None, "Flip", "RocketJump", "Roll")
    else:
        ok = body.standing and body.animation is None and fall < 20.0 and c1.vy > -5.0 and c0.y < c1.y - 5.0
    if not ok or body.on_floor() or body.room_gravity <= 0.0 or body.swimming:
        return False
    hit = None
    for bar in _bars(body):
        if bar.vertical or not bar.x0 <= c1.x <= bar.x1:
            continue
        near = abs(c1.y - bar.y) < M.TILE / 2 or (loose and abs(c1.y + M.TILE / 2 - bar.y) < M.TILE / 2)
        if near and min(abs(bar.y - c1.y), abs(bar.y - c1.last_y)) < SKIP_TOL[loose]:
            hit = bar
            break
    if hit is None or inp0.x == 0 or inp0.y > 0 or body._ctrl_pole_skip > 0:
        miss = SKIP_MISS[loose]
        body._ctrl_pole_skip = miss if loose else min(SKIP_MISS_MAX, body._ctrl_pole_skip + miss)
        return False
    c0.vy = s.pole_skip_head
    c1.vy = s.pole_skip_feet
    dy = hit.y - M.STAND_HOVER - c1.y
    c0.y += dy
    c1.y += dy
    body.jump_boost = s.pole_skip_boost
    body._ctrl_pole_skip = SKIP_CD[loose]
    body._ctrl_want_jump = 0
    body._ctrl_can_jump = 0
    return True


def from_zerog(body):
    """重力恢复时失重抓着的杆接着抓住；没抓着返回 False。"""
    pole = getattr(body, "zerog_pole", None)
    if pole is None:
        return False
    bar = next((b for b in _bars(body) if b.obj is pole), None)
    if bar is None:
        body.zerog_pole = None
        return False
    _attach(body, bar, "ClimbOnBeam" if bar.vertical else "HangFromBeam")
    M.grab_from_zerog(body, bar)
    return True


def hold(body, bar, anim):
    """进入操控时接着抓住已经在抓的杆。"""
    _attach(body, bar, anim)


# 杆上每 tick


def ctrl_pole_update(body):
    """在杆上时每 tick 调：按动画处理按键，推一 tick。"""
    bar = getattr(body, "_ctrl_bar", None)
    if bar is None or not any(b.obj is bar.obj for b in _bars(body)):
        _leave(body)
        return
    bar = body._ctrl_bar = next(b for b in _bars(body) if b.obj is bar.obj)
    inp = body._ctrl_input
    inp0, inp1 = inp[0], inp[1]
    if body._ctrl_want_jump > 0:
        body._ctrl_want_jump -= 1
    elif inp0.jmp and not inp1.jmp:
        body._ctrl_want_jump = 5
    last_flip = body.facing
    if inp0.x != 0:
        body.facing = inp0.x
    anim = body.animation
    if anim == "ClimbOnBeam":
        _climb(body, bar, inp0, inp1, last_flip)
    elif anim == "GetUpToBeamTip":
        if _take_jump(body):
            _stand_jump(body)
        elif M.tip_up_tick(body, bar) is None:
            _leave(body)
    elif anim == "BeamTip":
        _tip(body, bar, inp0, inp1)
    elif anim == "HangFromBeam":
        _hang(body, bar, inp0, inp1)
    elif anim == "GetUpOnBeam":
        if body._ctrl_pull is None:
            body._ctrl_pull = M.PullUpMotion(body, bar, body.facing)
        r = body._ctrl_pull.step()
        if r is None:
            _leave(body)
        elif r:
            body._ctrl_pull = None
    elif anim == "StandOnBeam":
        _stand(body, bar, inp0, inp1)
    else:
        _leave(body)


def _climb(body, bar, inp0, inp1, last_flip):
    c0, c1 = body.chunk0, body.chunk1
    if _take_jump(body):
        if _pole_jump(body, inp0):
            return
    iy = 1 if inp0.y > 0 else (-1 if inp0.y < 0 else 0)
    M.climb_tick(body, bar, iy, clamp=False)
    _slide_up(body)
    if inp0.x != 0 and inp1.x != inp0.x and inp0.x == body.facing == last_flip:
        for o in _bars(body):
            if o.vertical or not (o.x0 <= bar.x <= o.x1):
                continue
            if abs(c0.y - o.y) < CROSS and not c1.on_floor:
                _attach(body, o, "HangFromBeam")
                M.grab_beam(body, o, bar.x)
                return
            if abs(c1.y - (o.y - M.STAND_HOVER)) < CROSS:
                _attach(body, o, "StandOnBeam")
                c1.x = min(max(bar.x, o.x0 + 2.0), o.x1 - 2.0)
                M.stand_tick(body, o, 0)
                return
    if c1.on_floor and inp0.y < 0:
        _leave(body)
        return
    if c0.y < bar.y0:
        if c0.y > bar.y0 - 2.0 * CROSS:
            body.animation = "GetUpToBeamTip"
        else:
            _leave(body)
    elif c0.y > bar.y1:
        _leave(body)


def _pole_jump(body, inp0):
    """从竖杆上起跳；只往上窜、还在杆上时返回 False。"""
    c0, c1 = body.chunk0, body.chunk1
    if inp0.x == 0:
        if inp0.y > 0:
            if body._ctrl_slide_up < 1:
                k = body.stats.pole_slide_up_fac
                for c in (c0, c1):
                    c.y -= 4.5 * k
                    c.vy -= 2.0 * k
                body._ctrl_slide_up = SLIDE_UP
            return False
        _leave(body)
        c0.vy = -2.0
        if inp0.y > -1:
            c0.vx = 2.0 * body.facing
        return True
    _leave(body)
    body.pole_jump(body.facing)
    return True


def _slide_up(body):
    n = body._ctrl_slide_up
    if n <= 0:
        return
    n -= 1
    body._ctrl_slide_up = n
    c0, c1 = body.chunk0, body.chunk1
    if n > 8:
        body.pole_frame = 12
    s = body.stats
    if n > 14:
        c0.y -= 2.0 * s.pole_slide_up_lift
        c1.y -= 2.0 * s.pole_slide_up_lift
    c0.vy -= _lerpmap(n, 17.0, 0.0, 3.0, -1.2, 0.45) * s.pole_slide_up_fac
    c1.vy -= _lerpmap(n, 17.0, 0.0, 1.5, -1.4, 0.45) * s.pole_slide_up_fac


def _stand_jump(body):
    _leave(body)
    body.aerobic_increase(body.stats.jump_aerobic)
    mj._standard_jump(body, body.chunk0, body.chunk1)


def _tip(body, bar, inp0, inp1):
    c0, c1 = body.chunk0, body.chunk1
    if _take_jump(body):
        _stand_jump(body)
        return
    ok = M.tip_step(body, bar)
    c0.vy -= inp0.y * 0.1
    c0.vx += inp0.x * 0.1
    M.run_accel(body, inp0.x, TIP_RUN_CAP)
    if _press(inp0, inp1, "y", 1):
        _leave(body)
        c1.vy += 1.0
    elif _press(inp0, inp1, "y", -1) or not ok:
        _leave(body)


def _hang(body, bar, inp0, inp1):
    c0 = body.chunk0
    if _press(inp0, inp1, "y", -1):
        _leave(body)
        return
    up = _press(inp0, inp1, "y", 1)
    if up:
        for o in _bars(body):
            if o.vertical and abs(c0.x - o.x) < V_GRAB and o.y0 <= c0.y <= o.y1:
                _attach(body, o, "ClimbOnBeam")
                M.attach_vertical(body, o, 1 if c0.x >= o.x else -1)
                return
    if up or _press(inp0, inp1, "jmp", True):
        body._ctrl_pull = M.PullUpMotion(body, bar, body.facing or 1)
        body.facing = body._ctrl_pull.facing
        body.animation = "GetUpOnBeam"
        body._ctrl_pull.step()
        return
    M.hang_tick(body, bar, inp0.x)


def _stand(body, bar, inp0, inp1):
    c0, c1 = body.chunk0, body.chunk1
    if _take_jump(body):
        _stand_jump(body)
        return
    if _press(inp0, inp1, "y", -1):
        _leave(body)
        return
    if _press(inp0, inp1, "y", 1):
        for o in _bars(body):
            if not o.vertical and o.x0 <= c0.x <= o.x1 and REACH_UP[0] <= bar.y - o.y <= REACH_UP[1]:
                c0.y -= 8.0
                c1.y -= 8.0
                _attach(body, o, "HangFromBeam")
                M.grab_beam(body, o, c0.x)
                return
    ix = inp0.x
    if ix and not bar.x0 + 2.0 < c1.x + ix * 2.0 < bar.x1 - 2.0:
        _leave(body)  # 走出横杆端头就掉下去
        return
    M.stand_tick(body, bar, ix)
