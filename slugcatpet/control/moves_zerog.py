"""手动控制的失重移动（y↓）：只把输入转成意图，运动积分仍在 _step_zerog 里。"""

from __future__ import annotations

import math

from ..core.creature import _in_beam, _is_vertical
from ..planning.climbmoves import release


def _poles(body):
    fn = getattr(body, "_ctrl_bars", None)
    return [b.obj for b in fn()] if fn is not None else []


def _beam_at(body, x, y, vertical):
    for p in _poles(body):
        if _is_vertical(p) == vertical and _in_beam(p, x, y):
            return p
    return None


def _try_grab(body, inp0, inp1, entered):
    """游着按方向经过杆、或刚进失重时头在杆上，就抓住。"""
    c0 = body.chunk0
    lx, ly = getattr(c0, "last_x", c0.x), getattr(c0, "last_y", c0.y)
    h = _beam_at(body, c0.x, c0.y, False)
    v = _beam_at(body, c0.x, c0.y, True)
    if entered and (h or v):
        body.zerog_pole = v or h
        return True
    up = -c0.vy
    if (
        h is not None
        and (inp0.x != 0 or (inp0.y != 0 and (inp0.y > 0) != (up > 0)))
        and (inp1.x == 0 or not _in_beam(h, lx, ly))
    ):
        body.zerog_pole = h
        return True
    if (
        v is not None
        and (inp0.y != 0 or (inp0.x != 0 and (inp0.x > 0) != (c0.vx > 0)))
        and (inp1.y == 0 or not _in_beam(v, lx, ly))
    ):
        body.zerog_pole = v
        return True
    return False


def _on_pole(body, inp0, inp1):
    """抓着杆时换杆、蹬开。"""
    c0 = body.chunk0
    pole = body.zerog_pole
    if inp0.x != 0 and inp0.y == 0 and _is_vertical(pole):
        body.zerog_pole = _beam_at(body, c0.x, c0.y, False) or pole
    elif inp0.y != 0 and inp0.x == 0 and not _is_vertical(pole):
        body.zerog_pole = _beam_at(body, c0.x, c0.y, True) or pole
    body.zerog_pole_intent = (float(inp0.x), float(-inp0.y))
    if not (inp0.jmp and not inp1.jmp):
        return
    ux = uy = 0.0
    if inp0.x != 0 or inp0.y != 0:
        d = math.hypot(inp0.x, inp0.y)
        ux, uy = inp0.x / d, -inp0.y / d
        crossing = _beam_at(body, c0.x, c0.y, True) and _beam_at(body, c0.x, c0.y, False)
        if not crossing:
            if body.standing and inp0.x == 0:
                uy *= 0.1
            elif not body.standing and inp0.y == 0:
                ux *= 0.1
    body.zerog_pole_kick(ux, uy)


def ctrl_zerog_update(body) -> None:
    inp = body._ctrl_input
    inp0, inp1 = inp[0], inp[1]
    entered = not getattr(body, "_ctrl_was_zerog", False)
    body._ctrl_was_zerog = True
    if body.on_pole:
        release(body)
        body._ctrl_bar = None
    # 跳跃预输入；能不能蹬墙看 body.canJump
    if body._ctrl_want_jump > 0:
        body._ctrl_want_jump -= 1
    elif inp0.jmp and not inp1.jmp:
        body._ctrl_want_jump = 5
    if inp0.x > 0:
        body.facing = 1
    elif inp0.x < 0:
        body.facing = -1
    tongue = getattr(body, "_ctrl_tongue", None)
    if tongue is not None and body.zerog_pole is None:
        tongue.update(body, inp0, inp1, body.canJump)
    if body.zerog_pole is not None or _try_grab(body, inp0, inp1, entered):
        _on_pole(body, inp0, inp1)
        body._ctrl_want_jump = 0
        return
    on_wall = body.canJump > 0
    ix, iy = float(inp0.x), float(-inp0.y)  # 输入向上为正，换成 y↓
    if ix != 0.0 or iy != 0.0:
        d = math.hypot(ix, iy)
        ux, uy = ix / d, iy / d
        body.zerog_swim(ux, uy, on_wall)
        if on_wall and body._ctrl_want_jump > 0:
            body.request_zerog_kick(ux, uy)
            body._ctrl_want_jump = 0
    elif on_wall and body._ctrl_want_jump > 0:
        body.request_zerog_kick()
        body._ctrl_want_jump = 0
    pyro = getattr(body, "_ctrl_pyro", None)
    if pyro is not None:
        pyro.update(body, inp0, inp1, body._ctrl_want_jump, body.canJump)
