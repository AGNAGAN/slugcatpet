"""多猫互动压力测试：长时间离屏运行，自动统计几类互动异常。"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SPECIES = ("survivor", "monk", "hunter", "saint", "rivulet", "artificer")
ROSTERS = {
    1: ("survivor", "monk", "hunter", "saint", "rivulet"),
    2: ("artificer", "survivor", "saint", "rivulet", "monk"),
    3: ("survivor", "monk", "hunter", "saint", "rivulet", "artificer"),
    4: ("hunter", "hunter", "survivor", "survivor"),
}

CURSOR_STATES = {"CursorLick", "RivSnatch", "PyroMaul"}
STAND_STATES = {"IdleStand", "FetchFruit", "AngryStone", "PostThrowWander", "PostThrowStand",
                "SeekWarmth"}
IGNORE_FLIP = {"Airborne", "Dragged", "Stunned", "Dead"}

KINDS = ("same_target", "makeway_pingpong", "makeway_repeat", "stuck", "flipflop",
         "tip_evict", "tip_pingpong", "cursor_fight", "stacked")
DOC = {
    "same_target": "两只以上同时奔向同一物品（持续 ≥20 tick 的次数）",
    "makeway_pingpong": "A 给 B 让路后 400 tick 内 B 又给 A 让路",
    "makeway_repeat": "同一对 400 tick 内重复让路",
    "stuck": "奔向目标 300 tick 内几乎没挪动",
    "flipflop": "X→Y→X 且各段都短于 30 tick",
    "tip_evict": "杆顶被挤下来",
    "tip_pingpong": "同一对在同一根杆顶 1200 tick 内互相挤",
    "cursor_fight": "两只以上同时在抢光标（tick 数）",
    "stacked": "两只站着的猫叠在一起 ≥120 tick 的次数",
}


def _events(seed, W_ticks):
    rng = random.Random(seed * 7919)
    ev = [
        (20, "place_pole", 0.3, 0.45, "vpole"),
        (25, "place_pole", 0.62, 0.5, "vpole"),
        (30, "place_pole", 0.48, 0.72, "hpole"),
        (35, "place_lamp", 0.85, 0.6),
        (40, "place_fruit", 0.2, 0.3),
        (45, "place_fruit", 0.5, 0.82),
        (50, "place_fruit", 0.75, 0.25),
        (55, "place_stone", 0.15, 0.8),
        (60, "place_stone", 0.55, 0.8),
        (65, "place_slimemold", 0.4, 0.2),
    ]
    for t in range(600, W_ticks, 600):
        ev.append((t, "place_fruit", rng.uniform(0.1, 0.9), rng.uniform(0.2, 0.85)))
    for t in range(900, W_ticks, 1500):
        ev.append((t, "hungry", rng.randrange(6)))
        ev.append((t + 1, "hungry", rng.randrange(6)))
    for t in range(1700, W_ticks, 2300):
        ev.append((t, "anger", rng.randrange(6)))
    w0 = int(W_ticks * 0.45)
    ev += [(w0, "water", True), (w0 + 1800, "water", False)]
    z0 = int(W_ticks * 0.72)
    ev += [(z0, "zerog", True), (z0 + 900, "zerog", False)]
    return sorted(ev, key=lambda e: e[0])


def _cursor(t, win):
    W, H = win._WL, win._HL
    ph = (t // 900) % 4
    if ph == 0:
        return (W * 0.92, H * 0.12)
    if ph == 1:
        return (W * (0.5 + 0.4 * math.sin(t / 90.0)), H * (0.55 + 0.15 * math.sin(t / 37.0)))
    if ph == 2:
        pets = [p for p in win.pets if p.body is not None]
        c = pets[(t // 3600) % len(pets)].body.chunk0
        return (c.x + 40.0, win._HL - 110.0)
    return (W * 0.45, H * 0.62)


class Meter:
    def __init__(self, n):
        self.n = n
        self.count = {k: 0 for k in KINDS}
        self.activity = defaultdict(int)
        self.detail = defaultdict(int)
        self._pursuit = {}                 # (target id, frozenset pair) → 连续 tick
        self._approach = [None] * n        # (start tick, minx, maxx, target)
        self._seq = [[] for _ in range(n)]  # [(state, start)]
        self._yields = []                  # (t, yielder, shover)
        self._tip = {}                     # pole id → (occupant, since)
        self._tip_left = {}                # pole id → (pet, t)
        self._evicts = []                  # (t, pole id, loser, winner)
        self._stack = {}
        self._prev_state = [None] * n

    def tick(self, t, win):
        pets = win.pets
        info = [self._read(p) for p in pets]
        self._same_target(t, info)
        self._stuck(t, info, pets)
        self._states(t, info)
        self._tips(t, info)
        self._cursor(info)
        self._stacked(info, pets)

    @staticmethod
    def _read(p):
        beh = p.behavior
        st = beh.state if beh is not None else None
        tgt = None
        phase = None
        pole = None
        if st == "FetchFruit":
            f = getattr(beh.state_obj("FetchFruit"), "fetcher", None)
            if f is not None and f.phase == "approach":
                tgt = f.target
        elif st == "AngryStone":
            th = getattr(beh.state_obj("AngryStone"), "thrower", None)
            if th is not None and th.phase == "approach":
                tgt = th.target
        elif st == "PoleClimb":
            pc = getattr(beh.state_obj("PoleClimb"), "climber", None)
            if pc is not None:
                pole, phase = pc.pole, pc.phase
        return {"state": st, "target": tgt, "pole": pole, "phase": phase}

    def _same_target(self, t, info):
        groups = defaultdict(list)
        for i, d in enumerate(info):
            if d["target"] is not None:
                groups[id(d["target"])].append(i)
        live = set()
        for tid, idx in groups.items():
            for a in idx:
                for b in idx:
                    if a < b:
                        key = (tid, a, b)
                        live.add(key)
                        n = self._pursuit.get(key, 0) + 1
                        self._pursuit[key] = n
                        if n == 20:
                            self.count["same_target"] += 1
        for key in list(self._pursuit):
            if key not in live:
                del self._pursuit[key]

    def _stuck(self, t, info, pets):
        for i, d in enumerate(info):
            x = pets[i].body.chunk1.x
            a = self._approach[i]
            if d["target"] is None:
                self._approach[i] = None
                continue
            if a is None or a[3] is not d["target"]:
                self._approach[i] = [t, x, x, d["target"], False]
                continue
            a[1], a[2] = min(a[1], x), max(a[2], x)
            if not a[4] and t - a[0] >= 300:
                if a[2] - a[1] < 12.0:
                    self.count["stuck"] += 1
                    a[4] = True
                else:
                    self._approach[i] = [t, x, x, d["target"], False]

    def _states(self, t, info):
        for i, d in enumerate(info):
            st = d["state"]
            if st == self._prev_state[i]:
                continue
            self._prev_state[i] = st
            self.activity[st] += 1
            if st == "MakeWay":
                self._on_yield(t, i, info)
            seq = self._seq[i]
            seq.append((st, t))
            if len(seq) > 3:
                del seq[0]
            if len(seq) == 3:
                (x0, t0), (y, t1), (x1, t2) = seq
                if (x0 == x1 and x0 != y and t2 - t1 < 30 and t1 - t0 < 30
                        and not ({x0, y} & IGNORE_FLIP)):
                    self.count["flipflop"] += 1
                    self.detail[f"{x0}>{y}>{x1}"] += 1

    def _on_yield(self, t, i, info):
        shover = self._shover_of(i)
        if shover is None:
            return
        for (t0, y, s) in self._yields:
            if t - t0 > 400:
                continue
            if y == shover and s == i:
                self.count["makeway_pingpong"] += 1
            elif y == i and s == shover:
                self.count["makeway_repeat"] += 1
        self._yields.append((t, i, shover))
        self._yields = [e for e in self._yields if t - e[0] <= 400]

    def _shover_of(self, i):
        o = self._pets[i].social.yielding_to(self._pets[i])
        if o is None:
            return None
        for j, q in enumerate(self._pets):
            if q is o:
                return j
        return None

    def _tips(self, t, info):
        occ = {}
        for i, d in enumerate(info):
            if d["pole"] is not None and d["phase"] == "tip":
                occ.setdefault(id(d["pole"]), i)
        for pid in set(self._tip) | set(occ):
            prev = self._tip.get(pid)
            cur = occ.get(pid)
            if prev is not None and prev != cur:
                self._tip_left[pid] = (prev, t)
            if cur is not None and prev != cur:
                left = self._tip_left.get(pid)
                if left is not None and left[0] != cur and t - left[1] <= 60:
                    self.count["tip_evict"] += 1
                    for (t0, p0, lo, wi) in self._evicts:
                        if p0 == pid and lo == cur and wi == left[0] and t - t0 <= 1200:
                            self.count["tip_pingpong"] += 1
                            break
                    self._evicts.append((t, pid, left[0], cur))
            if cur is None:
                self._tip.pop(pid, None)
            else:
                self._tip[pid] = cur

    def _cursor(self, info):
        if sum(1 for d in info if d["state"] in CURSOR_STATES) >= 2:
            self.count["cursor_fight"] += 1

    def _stacked(self, info, pets):
        live = set()
        for a in range(len(pets)):
            for b in range(a + 1, len(pets)):
                if info[a]["state"] not in STAND_STATES or info[b]["state"] not in STAND_STATES:
                    continue
                ba, bb = pets[a].body, pets[b].body
                if not (ba.on_floor() and bb.on_floor()):
                    continue
                if abs(ba.chunk1.x - bb.chunk1.x) < 10.0:
                    live.add((a, b))
                    n = self._stack.get((a, b), 0) + 1
                    self._stack[(a, b)] = n
                    if n == 120:
                        self.count["stacked"] += 1
        for k in list(self._stack):
            if k not in live:
                del self._stack[k]


def run_seed(seed, ticks, home):
    sys.path.insert(0, str(ROOT / "tests"))
    import behavior_check as G
    G._setup_env(home)
    random.seed(seed)
    app = G._make_app(home)
    from slugcatpet.platform import cursorfx
    cursorfx._IS_WIN = False
    from slugcatpet import skins
    skins.configure(False)
    skins.reload()
    from slugcatpet.window import PetWindow
    roster = ROSTERS[seed]
    win = PetWindow(params={"seed": seed, "max_pets": 6,
                            "pets": [{"id": f"pet-{i}", "variant": v}
                                     for i, v in enumerate(roster)]})
    win.anim.stop()
    cur = [None]
    win.cursor_logical = lambda: cur[0]
    events = defaultdict(list)
    for ev in _events(seed, ticks):
        events[ev[0]].append(ev)
    m = Meter(len(win.pets))
    m._pets = win.pets
    eaten = 0
    occ = defaultdict(int)
    for t in range(ticks):
        cur[0] = _cursor(t, win)
        for ev in events.get(t, ()):
            kind = ev[1]
            if kind == "hungry":
                win.pets[ev[2] % len(win.pets)].body.food = 0
            elif kind == "anger":
                pet = win.pets[ev[2] % len(win.pets)]
                pet.body.temper = -0.7
                G._fling_stone(win, pet)
            else:
                G._apply_event(win, ev, {})
        food0 = sum(p.body.food for p in win.pets)
        win._do_tick()
        eaten += max(0, sum(p.body.food for p in win.pets) - food0)
        m.tick(t, win)
        for p in win.pets:
            occ[p.behavior.state] += 1
    act = dict(m.activity)
    for pet in win.pets:
        pet.dismiss_kill_dialog()
    win.close()
    app.processEvents()
    return {"seed": seed, "ticks": ticks, "count": m.count, "eaten": eaten,
            "detail": dict(m.detail), "time": dict(occ),
            "entries": {k: act.get(k, 0) for k in ("FetchFruit", "PoleClimb", "HPole",
                                                     "MakeWay", "AngryStone", "CursorLick",
                                                     "RivSnatch", "PyroMaul", "IdleStand")}}


def _child(args):
    with tempfile.TemporaryDirectory(prefix="slugcatpet-social-") as home:
        res = run_seed(args.seed, args.ticks, Path(home))
    print("RESULT " + json.dumps(res))


def _run(args):
    results = []
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8")
    for s in args.seeds:
        p = subprocess.run([sys.executable, __file__, "_child", "--seed", str(s),
                            "--ticks", str(args.ticks)], env=env, capture_output=True,
                           text=True, encoding="utf-8")
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")), None)
        if line is None:
            print(p.stdout[-2000:], p.stderr[-4000:])
            raise SystemExit(f"seed {s} failed")
        r = json.loads(line[7:])
        results.append(r)
        print(f"seed {s}: " + "  ".join(f"{k}={r['count'][k]}" for k in KINDS)
              + f"  eaten={r['eaten']}")
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1), encoding="utf-8")
    _table(results)


def _table(results, before=None):
    print()
    for k in KINDS:
        now = sum(r["count"][k] for r in results)
        if before is None:
            print(f"{k:18s} {now:6d}   {DOC[k]}")
        else:
            was = sum(r["count"][k] for r in before)
            print(f"{k:18s} {was:6d} → {now:<6d} {DOC[k]}")


def _compare(args):
    a = json.loads(Path(args.before).read_text(encoding="utf-8"))
    b = json.loads(Path(args.after).read_text(encoding="utf-8"))
    for ra, rb in zip(a, b):
        print(f"seed {ra['seed']}: " + "  ".join(
            f"{k}={ra['count'][k]}→{rb['count'][k]}" for k in KINDS))
        print("   entries: " + "  ".join(
            f"{k}={ra['entries'][k]}→{rb['entries'][k]}" for k in ra["entries"])
              + f"  eaten={ra['eaten']}→{rb['eaten']}")
    _table(b, a)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4])
    r.add_argument("--ticks", type=int, default=12000)
    r.add_argument("--out")
    c = sub.add_parser("_child")
    c.add_argument("--seed", type=int)
    c.add_argument("--ticks", type=int)
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("before")
    cmp_.add_argument("after")
    args = ap.parse_args()
    {"run": _run, "_child": _child, "compare": _compare}[args.cmd](args)


if __name__ == "__main__":
    main()
