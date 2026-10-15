"""跳跃、劫持光标这类状态共用的收尾函数。"""

from __future__ import annotations

# ctx 是各状态自己的命名空间：dirty 表示有动作残留要清，hj 是持有的光标劫持句柄或 None


def clear_motion(body, ctx):
    """清掉 animation、jump_boost 和走路；没有 ANIM_RESET 兜底，结束时必须调。"""
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
    """光标劫持被外部解除（Ctrl+Alt+Q 或被别的顶替）。"""
    return ctx.hj is not None and (win.cursor_hijack is not ctx.hj or not ctx.hj.active)


def leak_watch(fsm, state_name, ctx):
    """每 tick 回调：被抓、被砸晕这类不走 brk 的打断后，清掉动作残留。"""

    def watch():
        if fsm.state != state_name and getattr(ctx, "dirty", False):
            clear_motion(fsm.body, ctx)

    return watch
