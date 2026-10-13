"""行为检查：固定种子和脚本化输入下逐 tick 比对状态、位置和渲染帧，确认改动没有意外改变行为。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = Path(__file__).resolve().parent / "baseline"
SEED = 20261012
ROUND = 3
HASH_SEED = "0"
FRAME_EVERY = 50
SCREEN = {"name": "check", "x": 0, "y": 0, "width": 1920, "height": 1080, "logicalDpi": 96, "dpr": 1}


def _cursor_park(t, win):
    return (win._WL * 0.92, win._HL * 0.12)


def _cursor_sweep(t, win):
    W, H = win._WL, win._HL
    if (t // 400) % 3 == 2:
        return (W * 0.45, H * 0.62)
    return (W * (0.5 + 0.4 * math.sin(t / 90.0)), H * (0.5 + 0.15 * math.sin(t / 37.0)))


def _follow(pet_idx, dx, fy, jitter=0.0):
    def f(t, win):
        c = win.pets[pet_idx].body.chunk0
        return (c.x + dx + jitter * math.sin(t / 7.0), win._HL * fy)

    return f


def _follow_low(pet_idx, dx, above):
    def f(t, win):
        c = win.pets[pet_idx].body.chunk0
        return (c.x + dx, win._HL - above)

    return f


def _on_body(pet_idx):
    def f(t, win):
        b = win.pets[pet_idx].body
        return ((b.chunk0.x + b.chunk1.x) * 0.5, (b.chunk0.y + b.chunk1.y) * 0.5)

    return f


def _phases(*spec):
    def f(t, win):
        cur = spec[0][1]
        for start, fn in spec:
            if t >= start:
                cur = fn
        return cur(t, win)

    return f


SCENARIOS = {
    "items": {
        "doc": "无能力三猫 + 果子/石头/竖杆/横杆/黏菌/蝙蝠/灯，光标扫动，中途拖拽一只猫",
        "pets": ["survivor", "monk", "hunter"],
        "ticks": 5000,
        "cursor": _cursor_sweep,
        "events": [
            (50, "place_fruit", 0.2, 0.35),
            (60, "place_fruit", 0.7, 0.3),
            (80, "place_stone", 0.35, 0.6),
            (100, "place_pole", 0.55, 0.45, "vpole"),
            (120, "place_pole", 0.3, 0.62, "hpole"),
            (400, "drag", 0, 0.0, -120.0, 40),
            (900, "place_slimemold", 0.12, 0.2),
            (1300, "place_batfly", 0.45, 0.3),
            (1800, "place_lamp", 0.8, 0.5),
            (2600, "place_fruit", 0.4, 0.25),
        ],
    },
    "env": {
        "doc": "涨水 → 退水 → 无重力 → 暴风雪，含圣徒/溪流/白猫",
        "pets": ["saint", "rivulet", "survivor"],
        "ticks": 4500,
        "cursor": _cursor_sweep,
        "events": [
            (100, "place_fruit", 0.35, 0.35),
            (400, "water", True),
            (1600, "water", False),
            (2000, "zerog", True),
            (2700, "zerog", False),
            (2900, "blizzard", True),
        ],
    },
    "cursor_play": {
        "doc": "光标依次停在圣徒/溪流/工匠旁：舔光标、后空翻劫持、低好感扑咬",
        "pets": ["saint", "rivulet", "artificer"],
        "ticks": 5400,
        "cursor": _phases(
            (0, _cursor_park),
            (200, _follow(0, 30.0, 0.62)),
            (1800, _follow_low(1, 60.0, 110.0)),
            (3400, _on_body(2)),
        ),
        "events": [
            (3300, "set", 2, "temper", -0.8),
        ],
    },
    "trouble": {
        "doc": "砸晕→生气→扔石头/无石可扔；低好感满业力圣徒被砸→超度；杀死弹窗→舌头闪避；冬眠；死亡复活；趋暖",
        "pets": ["survivor", "saint", "monk"],
        "ticks": 6000,
        "cursor": _cursor_sweep,
        "events": [
            (60, "place_stone", 0.15, 0.7),
            (70, "place_stone", 0.85, 0.7),
            (100, "set", 2, "food", "max"),
            (300, "fling_stone", 0),
            (1500, "set", 1, "temper", -0.6),
            (1505, "set", 1, "karma", "max"),
            (1520, "fling_stone", 1),
            (2600, "fling_stone", 0),
            (2640, "clear_stones"),
            (3400, "set", 1, "temper", 0.5),
            (3420, "request_kill", 1),
            (4300, "kill", 2),
            (4600, "place_lamp", 0.9, 0.85),
            (4620, "set", 0, "cold", 0.9),
        ],
    },
    "hands": {
        "doc": "吃饱顺手留果子带去睡、醒来先吃；好感低揣石头、被拎起、被抢、消气放下",
        "pets": ["survivor", "hunter"],
        "ticks": 6000,
        "cursor": _cursor_park,
        "events": [
            (20, "set", 0, "food", 6),
            (25, "place_fruit", 0.25, 0.95),
            (26, "place_fruit", 0.32, 0.95),
            (27, "place_fruit", 0.4, 0.95),
            (30, "set", 1, "food", 6),
            (31, "set", 1, "temper", -0.6),
            (35, "place_stone", 0.7, 0.95),
            (36, "place_stone", 0.78, 0.95),
            (1500, "drag", 1, 0.0, -120.0, 40),
            (2600, "snatch", 1),
            (3600, "set", 1, "temper", 0.6),
        ],
    },
    "spears": {
        "doc": "矛：好感很低的猎手拿矛扔光标、扎墙成杆、扎地成竖杆、串蝙蝠、打吊果、无重力与水中、开友伤后扎猫",
        "pets": ["survivor", "hunter", "gourmand"],
        "ticks": 6000,
        "cursor": _cursor_sweep,
        "events": [
            (20, "place_spear", 0.3, 0.95),
            (21, "place_spear", 0.55, 0.95),
            (22, "place_stone", 0.7, 0.95),
            (25, "place_fruit", 0.5, 0.3),
            (30, "set", 1, "temper", -0.9),
            (300, "fling_stone", 1),
            (900, "throw_spear", 0, 1, 0),
            (1000, "throw_spear", 2, -1, 0),
            (1100, "throw_spear", 0, 0, 1),
            (1300, "place_batfly", 0.5, 0.35),
            (1400, "throw_spear", 2, 1, 0),
            (1900, "clear", "spear"),
            (2000, "zerog", True),
            (2250, "move_pet", 0, 0.08),
            (2252, "throw_spear", 0, -1, 0),
            (2400, "move_pet", 2, 0.6),
            (2402, "throw_spear", 2, 0, -1),
            (2600, "zerog", False),
            (2800, "water", True),
            (3100, "move_pet", 2, 0.9),
            (3102, "throw_spear", 2, 1, 0),
            (3600, "water", False),
            (3700, "clear", "spear"),
            (4000, "friendly_fire", True),
            (4090, "move_pet", 1, 0.3),
            (4091, "move_pet", 0, 0.45),
            (4092, "throw_spear", 1, 1, 0),
            (4300, "move_pet", 2, 0.85),
            (4302, "throw_spear", 2, 1, 0),
            (4800, "drag", 1, 0.0, -120.0, 40),
            (5200, "set", 1, "temper", 0.6),
        ],
    },
}


def _setup_env(home: Path):
    # 图集从本机已导入的目录复制一份（SLUGCATPET_ASSETS 可指定来源）
    src = Path(os.environ.get("SLUGCATPET_ASSETS") or Path.home() / ".slugcatpet" / "assets")
    dst = home / "assets"
    if src.is_dir() and not dst.exists():
        dst.mkdir(parents=True)
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, dst / f.name)
    os.environ["SLUGCATPET_HOME"] = str(home)
    (home / "screen.json").write_text(json.dumps({"screens": [SCREEN]}), encoding="utf-8")
    # configfile 用相对路径：绝对路径的盘符冒号会被 Qt 当成平台参数分隔符
    os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=screen.json"
    for k in (
        "SLUGCATPET_FORCE_ENERGY",
        "SLUGCATPET_FORCE_TEMPER",
        "SLUGCATPET_FORCE_FOOD",
        "SLUGCATPET_PETS",
        "SLUGCATPET_DEBUG",
    ):
        os.environ.pop(k, None)
    sys.path.insert(0, str(ROOT))


def _make_app(home: Path):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        here = os.getcwd()
        os.chdir(home)
        try:
            app = QApplication([])
        finally:
            os.chdir(here)
    return app


def _fling_stone(win, pet):
    c = pet.body.chunk0
    side = -1.0 if c.x > win._WL * 0.5 else 1.0
    s = win.place("stone", c.x - side * 90.0, c.y - 30.0)
    if s is None:
        s = win.stones[-1]
        s.x, s.y = c.x - side * 90.0, c.y - 30.0
        s.last_x, s.last_y = s.x, s.y
    s.vx, s.vy = side * 16.0, 2.0
    s.fling = True


def _throw_spear(win, pet, dx, dy):
    b = pet.body
    s = win.place("spear", b.chunk0.x, b.chunk0.y)
    if s is None:
        return
    side = b.free_hand()
    if side is None:
        b.release(b.grasps["l"], to_free=True)
        side = "l"
    b.grab(s, side)
    b.throw(s, dx, 0.0, dir_y=dy)


def _apply_event(win, ev, drag_state):
    kind = ev[1]
    W, H = win._WL, win._HL
    if kind in ("place_fruit", "place_stone", "place_slimemold", "place_batfly", "place_lamp", "place_spear"):
        win.place(kind[len("place_") :], W * ev[2], H * ev[3])
    elif kind == "place_pole":
        win.place(ev[4], W * ev[2], H * ev[3])
    elif kind == "water":
        win.set_water(ev[2])
    elif kind == "zerog":
        win.set_zerog(ev[2])
    elif kind == "blizzard":
        win.blizzard_on = ev[2]
        win.blizzard_timer = 0
    elif kind == "drag":
        pet = win.pets[ev[2]]
        c = pet.body.chunk0
        drag_state.update(pet=pet, x=c.x, y=c.y, dx=ev[3], dy=ev[4], n=ev[5], t=0)
        pet.behavior.on_press((c.x, c.y))
    elif kind == "set":
        body = win.pets[ev[2]].body
        val = ev[4]
        if val == "max":
            val = {"food": body.food_max, "karma": body.karma_max}[ev[3]]
        setattr(body, ev[3], val)
    elif kind == "clear_stones":
        win.clear_kind("stone")
    elif kind == "clear":
        win.clear_kind(ev[2])
    elif kind == "move_pet":
        b = win.pets[ev[2]].body
        dx = W * ev[3] - b.chunk1.x
        for c in (b.chunk0, b.chunk1):
            c.x += dx
            c.last_x += dx
            c.vx = c.vy = 0.0
    elif kind == "kill":
        win.pets[ev[2]].behavior.kill()
    elif kind == "fling_stone":
        _fling_stone(win, win.pets[ev[2]])
    elif kind == "throw_spear":
        _throw_spear(win, win.pets[ev[2]], ev[3], ev[4])
    elif kind == "friendly_fire":
        win.set_friendly_fire(ev[2])
    elif kind == "request_kill":
        win.request_kill(win.pets[ev[2]])
    elif kind == "snatch":
        held = win.pets[ev[2]].body.held_items()
        if held and win._begin_item_drag((held[0].x, held[0].y)):
            win._end_item_drag()
    else:
        raise ValueError(kind)


def _row(win):
    out = []
    for pet in win.pets:
        b = pet.body
        beh = pet.behavior
        out.append(
            [
                beh.state if beh is not None else None,
                b.bodyMode,
                getattr(b, "animation", None),
                round(b.chunk0.x, ROUND),
                round(b.chunk0.y, ROUND),
                round(b.chunk1.x, ROUND),
                round(b.chunk1.y, ROUND),
                round(b.energy, ROUND + 1),
                round(b.temper, ROUND + 1),
                b.food,
                round(b.cold, ROUND + 1),
            ]
        )
    items = [
        round(sum(o.x + o.y for o in group), 1)
        for group in (win.fruits, win.stones, win.slimemolds, win.batflies)
    ]
    if win.spears:
        items.append(round(sum(o.x + o.y for o in win.spears), 1))
    out.append(items)
    return out


FIELDS = (
    "state",
    "bodyMode",
    "animation",
    "c0.x",
    "c0.y",
    "c1.x",
    "c1.y",
    "energy",
    "temper",
    "food",
    "cold",
)


def _frame_hash(win) -> str:
    from PySide6.QtGui import QImage

    win._ts = 1.0
    img = QImage(win.size(), QImage.Format.Format_ARGB32)
    img.fill(0)
    win.render(img)
    _check_painted_bounds(win, img)
    return hashlib.md5(bytes(img.constBits())).hexdigest()[:16]


def _check_painted_bounds(win, img):
    """画到的像素必须都在记录的范围内，否则局部重绘会留残影。"""
    import numpy as np

    a = np.frombuffer(img.constBits(), np.uint32).reshape(img.height(), -1)[:, : img.width()]
    ys, xs = np.nonzero(a)
    if not len(xs):
        return
    r = win._painted
    if not (
        r.left() <= xs.min() and xs.max() <= r.right() and r.top() <= ys.min() and ys.max() <= r.bottom()
    ):
        raise AssertionError(
            f"painted pixels {xs.min()},{ys.min()}..{xs.max()},{ys.max()} outside recorded bounds {r}"
        )


def run_scenario(name: str, home: Path) -> tuple[list, dict]:
    sc = SCENARIOS[name]
    random.seed(SEED)  # 全局 random（爆跳/气泡/爆炸特效）
    app = _make_app(home)
    from slugcatpet.platform import cursorfx

    cursorfx._IS_WIN = False  # 光标劫持走 mock，不动真实鼠标
    from slugcatpet import skins

    skins.configure(False)
    skins.reload()
    from slugcatpet.window import PetWindow

    params = {"seed": SEED, "pets": [{"id": f"pet-{i}", "variant": v} for i, v in enumerate(sc["pets"])]}
    win = PetWindow(params=params)
    win.anim.stop()
    cur = [None]
    win.cursor_logical = lambda: cur[0]
    events = {}
    for ev in sc["events"]:
        events.setdefault(ev[0], []).append(ev)
    drag = {}
    rows = []
    frames = {}
    for t in range(sc["ticks"]):
        cur[0] = sc["cursor"](t, win)
        for ev in events.get(t, ()):
            _apply_event(win, ev, drag)
        if drag:
            drag["t"] += 1
            k = drag["t"] / drag["n"]
            cur[0] = (drag["x"] + drag["dx"] * k, drag["y"] + drag["dy"] * k)
            if drag["t"] >= drag["n"]:
                drag["pet"].behavior.on_release()
                drag.clear()
        win._do_tick()
        rows.append(_row(win))
        if t % FRAME_EVERY == 0:
            frames[str(t)] = _frame_hash(win)
    for pet in win.pets:
        pet.dismiss_kill_dialog()
    win.close()
    app.processEvents()
    return rows, frames


def _baseline_path(name):
    return BASELINE_DIR / f"{name}.json.gz"


def _first_divergence(want, got):
    for t, (rw, rg) in enumerate(zip(want, got)):
        if rw == rg:
            continue
        for i, (pw, pg) in enumerate(zip(rw, rg)):
            if pw == pg:
                continue
            if i == len(rw) - 1:
                return t, "world items (fruit/stone/slime/batfly position sums)", pw, pg, None
            for f, a, b in zip(FIELDS, pw, pg):
                if a != b:
                    return t, f"pet {i} {f}", a, b, (pw, pg)
        return t, "row shape", rw, rg, None
    if len(want) != len(got):
        return min(len(want), len(got)), "length", len(want), len(got), None
    return None


def _child(args):
    name = args.scenario
    with tempfile.TemporaryDirectory(prefix="slugcatpet-check-") as home:
        home = Path(home)
        _setup_env(home)
        t0 = time.perf_counter()
        rows, frames = run_scenario(name, home)
        dt = time.perf_counter() - t0
    path = _baseline_path(name)
    if args.cmd == "record":
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(
                {"seed": SEED, "round": ROUND, "rows": rows, "frames": frames}, f, separators=(",", ":")
            )
        print(f"[record] {name}: {len(rows)} ticks ({dt:.1f}s)")
        return 0
    if not path.exists():
        print(f"[missing] {name}: no baseline, run `record` first")
        return 1
    with gzip.open(path, "rt", encoding="utf-8") as f:
        base = json.load(f)
    got = json.loads(json.dumps(rows))  # 与基线同经 JSON 往返（tuple→list）
    div = _first_divergence(base["rows"], got)
    if div is not None:
        t, where, a, b, ctx = div
        print(f"[DIFF]   {name}: first divergence at tick {t}: {where}: baseline={a!r} now={b!r}")
        if ctx is not None:
            print(f"         baseline pet row: {ctx[0]}")
            print(f"         current  pet row: {ctx[1]}")
        return 1
    bad = [t for t, h in base.get("frames", {}).items() if frames.get(t) != h]
    if bad:
        print(
            f"[DIFF]   {name}: physics identical, but {len(bad)} rendered frames "
            f"differ (first at tick {min(bad, key=int)})"
        )
        return 1
    print(f"[ok]     {name}: {len(rows)} ticks identical ({dt:.1f}s)")
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="replace")  # 非 UTF-8 控制台不因中文崩溃
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("record", "check"))
    ap.add_argument("-s", "--scenario", choices=list(SCENARIOS))
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.child:
        return _child(args)
    env = dict(os.environ, PYTHONHASHSEED=HASH_SEED, PYTHONIOENCODING="utf-8")
    names = [args.scenario] if args.scenario else list(SCENARIOS)
    me = str(Path(__file__).resolve())
    procs = [
        (
            n,
            subprocess.Popen(
                [sys.executable, me, args.cmd, "--child", "-s", n],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
            ),
        )
        for n in names
    ]
    failed = False
    for n, p in procs:
        out, _ = p.communicate()
        if out.strip():
            print(out.rstrip())
        if p.returncode not in (0, 1):
            print(f"[ERROR]  {n}: child exited with {p.returncode}")
        failed |= p.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
