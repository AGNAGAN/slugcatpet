"""屏幕左右边缘当原版的管道口：叼着猎物钻出屏幕去吃，过一阵再从边缘钻回来。

钻出照 Creature.Update 的 enteringShortCut：各节（连同叼着的猎物）每 tick 往洞口拽 4.5px，
蜥蜴自己的节全到洞口才算钻进去。钻回原版是 SpitOutOfShortCut 直接放到洞口格；
屏幕边缘没有洞口格可放，这里让身体排成一条从屏幕外平移进来。
钻进 / 屏幕外 / 钻回期间不跑物理和 AI，由物品层跳过碰撞、夹回和绘制。
"""

from __future__ import annotations

from .rw import V2, dir_vec, dist_less

ENTER, AWAY, EMERGE = "enter", "away", "emerge"
PULL = 4.5
HOLE_DEPTH = 40.0  # 洞口在屏幕边缘外这么远，身体被拽出去时是平着滑出画面
AWAY_TICKS = (400, 800)  # 10–20 s
FLOOR_EXIT_CHANCE = 0.7  # 钻回时走最底一行的概率（够得着的话）


def exit_tiles(T, breed) -> list:
    """两侧边缘列里这个品种站得住的格：[(tile, side)]，side -1 左 / +1 右。"""
    out = []
    for side, tx in ((-1, 0), (1, T.cols - 1)):
        for ty in range(T.rows):
            if T.accessible((tx, ty), breed):
                out.append(((tx, ty), side))
    return out


def side_of(T, tile) -> int:
    """格在边缘列上返回 side，否则 0。"""
    if tile[0] <= 0:
        return -1
    if tile[0] >= T.cols - 1:
        return 1
    return 0


def _hole(T, tile, side) -> V2:
    x = -HOLE_DEPTH if side < 0 else T.WL + HOLE_DEPTH
    return V2(x, T.middle_of(tile).y)


def begin_enter(L, tile, side) -> None:
    L.sc_phase = ENTER
    L.sc_hole = _hole(L.terrain, tile, side)
    L.sc_rad_add = 0.9


def update(L, T) -> None:
    if L.sc_phase == ENTER:
        _enter(L)
    elif L.sc_phase == AWAY:
        L.sc_timer -= 1
        if L.sc_timer <= 0:
            _begin_emerge(L, T)
    elif L.sc_phase == EMERGE:
        _emerge(L)


def _enter(L) -> None:
    if L.stunned:
        L.sc_phase = None
        return
    L.sc_rad_add += 0.2
    hole = L.sc_hole
    rad = max(10.0, L.sc_rad_add)
    outside = 0
    g = L.grasps[0]
    prey = g.grabbed if g is not None else None
    for obj in (L, prey):
        if obj is None:
            continue
        for c in obj.body_chunks:
            c.vel = c.vel * 0.06
            if not dist_less(c.pos, hole, rad):
                if obj is L:
                    c.last_pos = c.pos
                    outside += 1
                c.pos = c.pos + dir_vec(c.pos, hole) * PULL
            else:
                c.pos = hole
                if obj is L:
                    c.last_pos = hole
    gm = L.graphics_module
    gm.update()
    gm.sucked_into_shortcut(hole)
    if outside == 0:
        _sucked_in(L, prey)


def _sucked_in(L, prey) -> None:
    """钻进去了：猎物带走（物品层把它直接移除，不淡出），开始在屏幕外吃。"""
    L.lose_all_grasps()
    if prey is not None:
        prey.taken_away = True
    L.ai.reset_eating()
    L.sc_phase = AWAY
    L.sc_timer = L.rng.randrange(*AWAY_TICKS)


def _begin_emerge(L, T) -> None:
    rng = L.rng
    tiles = exit_tiles(T, L.lizard_params)
    if not tiles:
        tiles = [((0, 0), -1), ((T.cols - 1, 0), 1)]
    floor = [t for t in tiles if t[0][1] == 0]
    tile, side = rng.choice(floor if floor and rng.random() < FLOOR_EXIT_CHANCE else tiles)
    y = T.middle_of(tile).y
    edge = 0.0 if side < 0 else T.WL
    step = L.body_chunk_connections[0].distance
    for i, c in enumerate(L.body_chunks):
        x = edge + side * (c.rad + i * step)  # 头在最里，身体往屏幕外排
        c.pos = c.last_pos = c.last_last_pos = V2(x, y)
        c.vel = V2()
    L.sc_dir = -side
    L.sc_phase = EMERGE
    L.graphics_module.reset()


def _emerge(L) -> None:
    d = V2(L.sc_dir * PULL, 0.0)
    for c in L.body_chunks:
        c.last_pos = c.pos
        c.pos = c.pos + d
        c.vel = d
    L.graphics_module.update()
    T = L.terrain
    if all(c.rad <= c.pos.x <= T.WL - c.rad for c in L.body_chunks):
        L.sc_phase = None
        L.pos_tile = T.tile_of(L.body_chunks[0].pos)
