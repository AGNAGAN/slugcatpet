"""鳃绘制（槽位 under_face）。"""

from __future__ import annotations

import math

from ...core.gfxmath import _lerp
from ...core.vecmath import _ang_from_up, _rot
from ...appearance import accessory_color
from ...rendering.primitives import blit

EFFECT = (223, 45, 234)


def draw_gills(gfx, g, p, atlas, ts, acc):
    hx_i = _lerp(gfx.head.lx, gfx.head.x, ts)
    hy_i = _lerp(gfx.head.ly, gfx.head.y, ts)
    d0x = _lerp(gfx._last_draw0[0], gfx.draw0[0], ts)
    d0y = _lerp(gfx._last_draw0[1], gfx.draw0[1], ts)
    d1x = _lerp(gfx._last_draw1[0], gfx.draw1[0], ts)
    d1y = _lerp(gfx._last_draw1[1], gfx.draw1[1], ts)
    if gfx.sleep_curl > 0.0:
        side = 1.0 if d0x >= d1x else -1.0
        hx_i += side * 2.0 * gfx.sleep_curl
        hy_i -= 1.0 * gfx.sleep_curl
    hox, hoy = getattr(gfx, "_breath_head_off", (0.0, 0.0))
    ox, oy = gfx.face_offset_at(ts)
    fx = hx_i + ox + hox
    fy = hy_i + oy + hoy

    gf = g.flat
    hip_d = math.hypot(d0x - d1x, d0y - d1y)
    f1x, f1y = _lerp(d1x, d0x, gf), _lerp(d1y, d0y + hip_d, gf)
    body_axis = _ang_from_up(d0x - f1x, d0y - f1y)
    pvx, pvy = _rot(1.0, 0.0, body_axis)
    gh = g.graphic_height or 1.0
    n = len(g.scales)
    half = n // 2
    xf = []
    for k in range(n):
        sc = g.scales[k]
        bx = _lerp(sc.lx, sc.x, ts)
        by = -_lerp(sc.ly, sc.y, ts)  # 鳞内部 y↑ → pet y↓
        if k < half:
            off, rot_off, scale_x = -5.0, 0.0, -sc.width
        else:
            off, rot_off, scale_x = 5.0, 180.0, sc.width
        anchor_x, anchor_y = fx + pvx * off, fy + pvy * off
        rotation = _ang_from_up(bx - anchor_x, by - anchor_y) + rot_off
        xf.append((anchor_x, anchor_y, rotation, scale_x, sc.length / gh))
    gill_col = gfx._color("GILLS", gfx.BODY)
    effect = accessory_color(acc, gfx._gcol)
    for ax_, ay_, rot, sxx, syy in xf:
        blit(p, atlas, "LizardScaleA3", ax_, ay_, rot, sxx, syy, gill_col, ax=0.5, ay=0.9)
    for ax_, ay_, rot, sxx, syy in xf:
        blit(p, atlas, "LizardScaleB3", ax_, ay_, rot, sxx, syy, effect, ax=0.5, ay=0.9)
