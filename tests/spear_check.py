"""矛的边界检查：扎墙 / 拔出 / 友伤 / 串蝙蝠 / 打果子 / 迎面相撞 / 带光标 / 角色差异等，逐条断言。"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from behavior_check import SEED, _make_app, _setup_env  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def make_win(pets=("survivor",), **params):
    from slugcatpet.platform import cursorfx

    cursorfx._IS_WIN = False
    from slugcatpet import skins

    skins.configure(False)
    skins.reload()
    from slugcatpet.window import PetWindow

    p = {"seed": SEED, "pets": [{"id": f"pet-{i}", "variant": v} for i, v in enumerate(pets)]}
    p.update(params)
    win = PetWindow(params=p)
    win.anim.stop()
    cur = [None]
    win.cursor_logical = lambda: cur[0]
    win._test_cursor = cur
    return win


def tick(win, n=1):
    for _ in range(n):
        win._do_tick()


def thrower(variant="survivor", x=0.0, y=0.0, exhausted=False):
    from slugcatpet.characters import get as get_cat_def

    c0 = SimpleNamespace(x=x, y=y, vx=0.0, vy=0.0)
    return SimpleNamespace(
        chunk0=c0, stats=get_cat_def(variant).stats, exhausted=exhausted, hand_of=lambda obj: None
    )


def launch(win, s, by, dx, dy=0, aim=None):
    """不经猫手，按 by 的身份把矛 s 从 by.chunk0 处扔出。"""
    from slugcatpet.core.creature import Throw

    c0 = by.chunk0
    s.x, s.y = c0.x + dx * 10.0, c0.y + dy * 10.0 - 4.0
    s.last_x, s.last_y = s.x, s.y
    s.on_thrown(Throw(by, dx, dy, 0.5 if by.exhausted else 1.0, aim))
    s.state = "free"


def spear(win, x=100.0, y=100.0):
    s = win.place("spear", x, y)
    assert s is not None
    return s


def park_pets(win):
    """把猫挪到右下角、免得挡路。"""
    for i, pet in enumerate(win.pets):
        b = pet.body
        for c in (b.chunk0, b.chunk1):
            c.x = c.last_x = win._WL - 40.0 - i * 30.0
            c.vx = c.vy = 0.0


def run_until(win, cond, limit=200):
    for _ in range(limit):
        tick(win)
        if cond():
            return True
    return False


# 扎墙


@case
def sticks_near_wall():
    win = make_win()
    park_pets(win)
    s = spear(win)
    gv = win.geometry_version
    by = thrower(x=win._WL - 120.0, y=win._HL * 0.4)
    launch(win, s, by, 1)
    assert run_until(win, lambda: s.mode != "thrown")
    assert s.mode == "wall", s.mode
    assert s.state == "stuck"
    assert s.kind == "horizontal" and not s.grounded
    assert abs(s.ax - win._WL) < 1e-6 and abs(s.bx - (win._WL - 40.0)) < 1e-6
    assert s in win.items_affording("climbable")
    assert s not in win.items_affording("throwable")
    assert win.geometry_version > gv
    tick(win, 30)
    assert s.mode == "wall" and s.state == "stuck"


@case
def far_stick_is_a_chance():
    win = make_win()
    park_pets(win)
    stuck = 0
    n = 60
    for i in range(n):
        win.clear_kind("spear")
        s = spear(win)
        s._rng.seed(1000 + i)
        by = thrower(x=win._WL - 420.0, y=win._HL * 0.3)
        launch(win, s, by, 1)
        run_until(win, lambda: s.mode != "thrown")
        stuck += s.mode == "wall"
    assert 0.15 * n < stuck < 0.55 * n, stuck


@case
def never_sticks_beyond_range():
    win = make_win()
    park_pets(win)
    for i in range(10):
        win.clear_kind("spear")
        s = spear(win)
        s._rng.seed(i)
        by = thrower(variant="hunter", x=win._WL - 760.0, y=win._HL * 0.3)
        launch(win, s, by, 1)
        run_until(win, lambda: s.mode != "thrown")
        assert s.mode != "wall"


@case
def one_spear_per_tile():
    win = make_win()
    park_pets(win)
    a, b = spear(win), spear(win, 200.0)
    for s in (a, b):
        by = thrower(x=win._WL - 100.0, y=win._HL * 0.4)
        launch(win, s, by, 1)
        run_until(win, lambda: s.mode != "thrown")
    assert a.mode == "wall" and b.mode != "wall", (a.mode, b.mode)


@case
def slow_spear_bounces():
    win = make_win()
    park_pets(win)
    s = spear(win)
    by = thrower(x=win._WL - 100.0, y=win._HL * 0.4, exhausted=True)
    launch(win, s, by, 1)
    run_until(win, lambda: s.mode != "thrown")
    assert s.mode == "free"


@case
def floor_and_ceiling():
    from slugcatpet.planning.pole_reach import _vpoles

    win = make_win()
    park_pets(win)
    down, up = spear(win), spear(win, 300.0)
    launch(win, down, thrower(x=400.0, y=win._HL - 60.0), 0, 1)
    launch(win, up, thrower(x=600.0, y=80.0), 0, -1)
    run_until(win, lambda: down.mode != "thrown" and up.mode != "thrown")
    assert down.mode == "wall" and down.kind == "vertical" and down.grounded
    assert abs(down.ay - win._HL) < 1e-6 and abs(down.by - (win._HL - 40.0)) < 1e-6
    assert up.mode == "wall" and up.kind == "vertical" and not up.grounded
    vp = _vpoles(win.pets[0])
    assert down in vp and up not in vp
    old = win._HL
    win._items_floor_shift(old, old - 30.0)
    assert abs(down.ay - (old - 30.0)) < 1e-6


@case
def weak_and_strong_throwers():
    win = make_win()
    park_pets(win)
    s = spear(win)
    launch(win, s, thrower("monk", 300.0, 300.0), 1)
    assert s.throw_frames == 18 and s.damage < 1.0 and abs(s.vx - 40.0 * 0.77) < 1e-6
    s2 = spear(win, 200.0)
    launch(win, s2, thrower("hunter", 300.0, 300.0), 1)
    assert s2.damage == 1.25 and abs(s2.vx - 48.0) < 1e-6
    s3 = spear(win, 300.0)
    launch(win, s3, thrower("survivor", 300.0, 300.0), 0, -1)
    assert s3.damage == 0.8 and abs(s3.vy + 40.0 * 0.87) < 1e-6


# 拔出 / 移除 / 上限


@case
def mouse_pulls_out():
    win = make_win()
    park_pets(win)
    s = spear(win)
    launch(win, s, thrower(x=win._WL - 100.0, y=win._HL * 0.4), 1)
    run_until(win, lambda: s.mode != "thrown")
    assert s.mode == "wall"
    gv = win.geometry_version
    assert win._begin_item_drag((s.x - 15.0, s.y))
    tick(win)
    assert s.mode == "free" and s.state == "mouse"
    assert s not in win.items_affording("climbable")
    assert win.geometry_version > gv
    win._end_item_drag()
    assert s.state == "free" and s.fling


@case
def user_fling_never_sticks():
    win = make_win()
    park_pets(win)
    s = spear(win, win._WL - 60.0, win._HL * 0.4)
    assert win._begin_item_drag((s.x, s.y))
    win._step_item_drag(win._drag[0])
    s.vx = 14.0
    win._end_item_drag()
    for _ in range(60):
        tick(win)
        assert s.mode != "wall"


@case
def remove_stuck_spear():
    win = make_win()
    park_pets(win)
    s = spear(win)
    launch(win, s, thrower(x=win._WL - 100.0, y=win._HL * 0.4), 1)
    run_until(win, lambda: s.mode != "thrown")
    gv = win.geometry_version
    assert win._remove_at((s.x, s.y))
    assert s not in win.spears and win.geometry_version > gv


@case
def shared_cap():
    win = make_win()
    for i in range(6):
        spear(win, 100.0 + i * 30.0)
    win.spears[0].mode = "wall"
    assert win.place("spear", 500.0, 100.0) is None


# 猫


def _aim_at_cat(win, target, by_variant="survivor", dx=1):
    for pet in win.pets:
        if pet is not target:
            for c in (pet.body.chunk0, pet.body.chunk1):
                c.x = c.last_x = 30.0
    tb = target.body
    c0 = tb.chunk0
    return thrower(by_variant, c0.x - dx * 200.0, c0.y + 4.0)


@case
def friendly_fire_off_passes_through():
    win = make_win(("survivor", "monk"))
    target = win.pets[1]
    tick(win, 5)
    s = spear(win)
    launch(win, s, _aim_at_cat(win, target), 1)
    tick(win, 8)
    assert target.behavior.state not in ("Stunned", "Dead")
    assert s.stuck_in is None


@case
def friendly_fire_kills_and_falls_out_on_revive():
    win = make_win(("survivor", "monk"), friendly_fire=True)
    target = win.pets[1]
    target.body.karma = target.body.karma_max
    tick(win, 5)
    s = spear(win)
    launch(win, s, _aim_at_cat(win, target, "hunter"), 1)
    assert run_until(win, lambda: s.mode != "thrown", 20)
    assert s.mode == "body", s.mode
    assert target.behavior.state == "Dead"
    assert s.state == "stuck"
    assert run_until(win, lambda: not target.body.dead, 3000)
    tick(win, 2)
    assert s.mode == "free" and s.state == "free"


@case
def weak_hit_stuns_then_second_kills():
    win = make_win(("monk", "survivor"), friendly_fire=True)
    target = win.pets[1]
    tick(win, 5)
    s = spear(win)
    launch(win, s, _aim_at_cat(win, target, "monk"), 1)
    assert run_until(win, lambda: s.mode != "thrown", 20)
    assert s.mode == "body" and target.behavior.state == "Stunned"
    assert 0.6 <= target.body.wounds < 1.0
    assert run_until(win, lambda: s.mode != "body", 400)
    tick(win, 2)
    s2 = spear(win, 200.0)
    launch(win, s2, _aim_at_cat(win, target, "monk"), 1)
    run_until(win, lambda: s2.mode != "thrown", 20)
    assert target.body.dead


@case
def thrower_not_hit_by_own_spear():
    win = make_win(("survivor",), friendly_fire=True)
    pet = win.pets[0]
    tick(win, 5)
    s = spear(win)
    b = pet.body
    b.grab(s, "l")
    b.throw(s, 1, 0.0)
    tick(win, 5)
    assert s.stuck_in is None and pet.behavior.state != "Stunned"


# 小东西


@case
def batflies_get_impaled():
    win = make_win()
    park_pets(win)
    y = win._HL * 0.3
    flies = [win.place("batfly", 400.0 + i * 25.0, y) for i in range(3)]
    for f in flies:
        f.x = f.last_x = f.x
        f.y = f.last_y = y
    s = spear(win)
    launch(win, s, thrower(x=200.0, y=y + 4.0 + 1.5), 1)
    tick(win, 8)
    hit = [f for f, _ in s.impaled]
    assert hit, [(f.x, f.y) for f in flies]
    assert all(f.dead for f in hit)
    tick(win, 2)
    f = hit[0]
    assert math.hypot(f.x - s.x, f.y - s.y) < 20.0
    f.state = "mouse"
    tick(win)
    assert f not in [g for g, _ in s.impaled]


@case
def hanging_fruit_knocked_loose():
    win = make_win()
    park_pets(win)
    f = win.place("fruit", 500.0, win._HL * 0.3)
    tick(win, 30)
    assert f.state == "hanging", f.state
    s = spear(win)
    launch(win, s, thrower(x=300.0, y=f.y + 4.0), 1)
    assert run_until(win, lambda: s.mode != "thrown", 20)
    assert s.mode == "free"
    assert run_until(win, lambda: f.state == "free", 80)


@case
def spears_clash_head_on():
    win = make_win()
    park_pets(win)
    y = win._HL * 0.35
    a, b = spear(win, 100.0), spear(win, 200.0)
    launch(win, a, thrower(x=300.0, y=y), 1)
    launch(win, b, thrower(x=700.0, y=y), -1)
    assert run_until(win, lambda: a.mode != "thrown" and b.mode != "thrown", 20)
    assert a.mode == "free" and b.mode == "free"
    assert a.vibrate > 0 and b.vibrate > 0


@case
def spear_clashes_with_stone():
    win = make_win()
    park_pets(win)
    y = win._HL * 0.35
    st = win.place("stone", 600.0, y)
    st.vx, st.vy = -30.0, -3.0
    st.thrown_by_cat = True
    s = spear(win)
    launch(win, s, thrower(x=350.0, y=y), 1)
    assert run_until(win, lambda: s.mode != "thrown", 20)
    assert s.mode == "free" and not st.in_flight()


# 光标


@case
def cursor_rides_and_is_pinned():
    win = make_win()
    park_pets(win)
    y = win._HL * 0.4
    win._test_cursor[0] = (win._WL - 220.0, y)
    s = spear(win)
    launch(win, s, thrower(x=win._WL - 330.0, y=y + 4.0 + 1.5), 1)
    tick(win, 3)
    ride = getattr(win, "_spear_ride", None)
    assert ride is not None and win.cursor_hijack is ride[1]
    assert run_until(win, lambda: s.mode != "thrown", 20)
    assert s.mode == "wall" and win.cursor_hijack is not None
    tick(win, 110)
    assert win.cursor_hijack is not None
    tick(win, 15)
    assert win.cursor_hijack is None


@case
def cursor_freed_when_spear_fails():
    win = make_win()
    park_pets(win)
    y = win._HL * 0.4
    win._test_cursor[0] = (win._WL - 700.0, y)
    s = spear(win)
    s._rng.seed(3)
    launch(win, s, thrower(x=win._WL - 800.0, y=y + 5.5), 1)
    tick(win, 3)
    assert getattr(win, "_spear_ride", None) is not None
    run_until(win, lambda: s.mode != "thrown", 40)
    tick(win, 2)
    assert s.mode != "wall" and win.cursor_hijack is None


@case
def cursor_untouched_when_hijack_off():
    win = make_win(cursor_hijack=False)
    park_pets(win)
    y = win._HL * 0.4
    win._test_cursor[0] = (win._WL - 220.0, y)
    s = spear(win)
    launch(win, s, thrower(x=win._WL - 330.0, y=y + 5.5), 1)
    tick(win, 3)
    assert win.cursor_hijack is None


# 瞄准


@case
def aimed_throw_arcs_to_target():
    win = make_win()
    park_pets(win)
    by = thrower("survivor", 300.0, win._HL - 40.0)
    s = spear(win)
    origin = (by.chunk0.x + 10.0, by.chunk0.y - 4.0)
    target = (650.0, win._HL - 220.0)
    aim = s.aim_for(by, 1, origin, target)
    assert aim is not None and aim[1] < 0.0
    launch(win, s, by, 1, aim=aim)
    best = 1e9
    for _ in range(30):
        tick(win)
        best = min(best, math.hypot(s.x - target[0], s.y - target[1]))
        assert s.rot == (1.0, 0.0) or s.mode != "thrown"
    assert best < 12.0, best


# 角色


@case
def saint_never_wields_spears():
    from slugcatpet.brain.hands import can_wield

    win = make_win(("saint", "hunter"))
    s = spear(win)
    saint, hunter = win.pets[0].body, win.pets[1].body
    saint.temper = hunter.temper = -0.9
    assert not can_wield(saint, s)
    assert can_wield(hunter, s)
    hunter.temper = -0.3
    assert not can_wield(hunter, s)


@case
def low_temper_prefers_spear():
    from slugcatpet.behaviors.anger.thrower import weapon_score

    win = make_win(("hunter",))
    fsm = win.pets[0].behavior
    s, st = spear(win), win.place("stone", 100.0, 100.0)
    fsm.body.temper = -0.9
    assert weapon_score(fsm, s, 300.0) < weapon_score(fsm, st, 150.0)
    fsm.body.temper = -0.3
    assert weapon_score(fsm, s, 300.0) > weapon_score(fsm, st, 150.0)


@case
def gourmand_spear_throw():
    win = make_win(("gourmand",))
    pet = win.pets[0]
    tick(win, 5)
    b = pet.body
    b.exhausted = False
    b.aerobic = 0.0
    s = spear(win)
    b.grab(s, "l")
    vx0 = b.chunk0.vx
    b.throw(s, 1, 0.0)
    assert b.aerobic == 1.0 and s.damage == 3.0
    assert b.chunk0.vx > vx0 + 9.0
    s2 = spear(win, 200.0)
    b.exhausted = True
    b.grab(s2, "l")
    b.throw(s2, 1, 0.0)
    assert s2.damage == 0.3


@case
def dragged_cat_throws_spear_toward_cursor():
    win = make_win(("hunter",))
    pet = win.pets[0]
    tick(win, 5)
    s = spear(win)
    b = pet.body
    b.grab(s, "l")
    pet.behavior.hands.adopt(s, "weapon")
    c0 = b.chunk0
    pet.behavior.hands._smack(s, (c0.x, c0.y - 60.0))
    assert s.mode == "thrown" and s.throw_dir == (0, -1)


@case
def stone_throw_unchanged_by_skill():
    win = make_win(("monk",))
    pet = win.pets[0]
    tick(win, 5)
    st = win.place("stone", 100.0, 100.0)
    b = pet.body
    b.grab(st, "l")
    want_vx = b.chunk0.vx * 0.2 + 50.0
    want_vy = b.chunk0.vy * 0.5 - 3.0
    b.throw(st, 1, 50.0, up=3.0)
    assert st.vx == want_vx and st.vy == want_vy
    assert st.thrown_by_cat


@case
def cat_grab_pulls_stuck_spear():
    win = make_win(("hunter",))
    park_pets(win)
    s = spear(win)
    launch(win, s, thrower(x=win._WL - 100.0, y=win._HL * 0.4), 1)
    run_until(win, lambda: s.mode != "thrown")
    assert s.mode == "wall"
    gv = win.geometry_version
    win.pets[0].body.grab(s, "l")
    tick(win)
    assert s.mode == "free" and s.wall is None and win.geometry_version > gv
    assert s not in win.items_affording("climbable")


@case
def angry_cat_throws_spear_at_cursor():
    win = make_win(("hunter",))
    pet = win.pets[0]
    b = pet.body
    tick(win, 5)
    b.temper = -0.9
    s = spear(win, b.chunk0.x + 60.0, win._HL - 20.0)
    tick(win, 60)
    win._test_cursor[0] = (b.chunk0.x + 260.0, b.chunk0.y - 40.0)
    from slugcatpet.brain.fsm import ANGER_TOTAL

    pet.behavior.anger = ANGER_TOTAL
    pet.behavior._transition("PostThrowWander")
    thrown = run_until(win, lambda: s.mode == "thrown", 1500)
    assert thrown, (pet.behavior.state, s.state, s.mode)


@case
def mildly_angry_cat_leaves_spear():
    win = make_win(("hunter",))
    pet = win.pets[0]
    b = pet.body
    tick(win, 5)
    s = spear(win, b.chunk0.x + 60.0, win._HL - 20.0)
    tick(win, 60)
    from slugcatpet.brain.fsm import ANGER_TOTAL

    for _ in range(600):
        b.temper = -0.3
        if pet.behavior.anger <= 0:
            pet.behavior.anger = ANGER_TOTAL
        tick(win)
        assert b.hand_of(s) is None


@case
def one_spear_unless_dual_wield():
    from slugcatpet.control.grasp import GraspControl

    win = make_win(("hunter", "spearmaster"))
    park_pets(win)
    tick(win, 5)
    for pet, dual in zip(win.pets, (False, True)):
        b = pet.body
        b.grab(spear(win, b.chunk0.x, b.chunk0.y), "l")
        s2 = spear(win, b.chunk0.x, b.chunk0.y)
        assert b.can_hold(s2) == dual
        assert (GraspControl(pet)._pickup_candidate() is s2) == dual
        assert b.can_hold(win.place("stone", b.chunk0.x, b.chunk0.y))


# 水


@case
def free_spear_sinks():
    win = make_win()
    park_pets(win)
    win.set_water(True)
    tick(win, 400)
    s = spear(win, 400.0, win.water_y + 30.0)
    tick(win, 200)
    assert s.y > win.water_y + 30.0


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    only = sys.argv[1:]
    with tempfile.TemporaryDirectory(prefix="slugcatpet-spear-") as home:
        home = Path(home)
        _setup_env(home)
        os.chdir(home)
        _make_app(home)
        failed = 0
        for fn in CASES:
            if only and fn.__name__ not in only:
                continue
            try:
                fn()
                print(f"[ok]   {fn.__name__}")
            except Exception:
                failed += 1
                print(f"[FAIL] {fn.__name__}")
                traceback.print_exc()
        print(f"{len(CASES) - failed if not only else '-'} passed, {failed} failed")
        os.chdir(ROOT)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
