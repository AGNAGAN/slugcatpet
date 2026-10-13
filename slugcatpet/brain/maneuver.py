"""跳跃 / 光标劫持类独占状态共用的收尾工具。"""
from __future__ import annotations

# ctx：各状态的私有命名空间；dirty=有运动残留待清理，hj=持有的光标劫持句柄（无则 None）


def clear_motion(body, ctx):
    """无 ANIM_RESET 兜底：终止必清 animation / jump_boost / 走停。"""
    body.animation = None
    body.jump_boost = 0.0
    body.walk_speed_target = None
    body.stop_walk()
    ctx.dirty = False


def stand_facing(body, d):
    body.set_posture(True)
    if d != 0:
        body.facing = 1 if d > 0 else -1


def release_hold(win, ctx):
    hj = ctx.hj
    if hj is not None:
        if win.cursor_hijack is hj:
            win.stop_cursor_hijack()
        else:
            hj.release()
        ctx.hj = None


def hold_lost(win, ctx) -> bool:
    """光标劫持被外部解除（Ctrl+Alt+Q / 被顶替）。"""
    return ctx.hj is not None and (win.cursor_hijack is not ctx.hj or not ctx.hj.active)


def leak_watch(fsm, state_name, ctx):
    """ticker：被旁路打断（被抓 / 被砸晕不走 brk）时只清运动残留。"""
    def watch():
        if fsm.state != state_name and getattr(ctx, "dirty", False):
            clear_motion(fsm.body, ctx)
    return watch
