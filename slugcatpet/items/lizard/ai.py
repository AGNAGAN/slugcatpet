"""LizardAI 子集：Tracker / PreyTracker / AgressionTracker / NoiseTracker / 视觉 / 行为分支。

场上能被蜥蜴看到的「生物」：蛋虫（猎物）、另一只蜥蜴（对手）和光标（不追不怕、只被偶尔看一眼）。
没有威胁（没人让蜥蜴害怕）、雨，所以 UtilityComparer 比较的是 PreyTracker、受伤、对手怒气、
任务（对手的威压让输家离开一阵）、噪音。
ReturnPrey 把屏幕左右边缘当窝口：叼着猎物钻出屏幕去吃（shortcut）；走不到才就地吃。
"""

from __future__ import annotations

import math
from collections import namedtuple
from typing import NamedTuple

from . import shortcut
from .physics import tile_xy, visual_contact
from .rw import (
    V2,
    dir_vec,
    dist_less,
    distance,
    dot,
    inverse_lerp,
    lerp,
    lerp_map,
    manhattan,
    s_curve,
)

_MAX = 3.4e38
EATS, ATTACKS, IGNORES, RIVAL = "Eats", "Attacks", "Ignores", "AgressiveRival"

EIGHT_AND_ZERO = ((0, 0), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1))
FOUR_DIRS = ((-1, 0), (0, -1), (1, 0), (0, 1))

EAT_TICKS = (240, 400)  # 吃一只猎物要这么多 tick
RETURN_PATIENCE = 800  # 叼着猎物走了这么久还没到屏幕边缘，就地吃
CROWD_PENALTY = 4.0
PREY_WEIGHT = 0.6
PREY_SMOOTH = 0.15

Coord = namedtuple("Coord", "tile")


class Relationship(NamedTuple):
    type: str
    intensity: float

    @property
    def go_for_kill(self) -> bool:
        return self.type in (EATS, ATTACKS) and self.intensity > 0.0


# StaticWorld 里的关系。蜥蜴模板层：对蛋虫 Eats 0.45、对任何蜥蜴 AgressiveRival 0.1，下表是各品种的覆盖。
# 与原版不同：蜥蜴之间的 Eats 降成 Attacks（桌宠互咬不会死，也不该被叼出屏幕吃掉）；
# Afraid（蓝怕绿 / 白 / 青）没有威胁模块，按 Ignores。光标不是生物，恒为 Ignores
_STATIC = {
    "green": {
        "eggbug": Relationship(EATS, 0.1),
        "green": Relationship(RIVAL, 0.8),
        "pink": Relationship(RIVAL, 0.2),
        "white": Relationship(RIVAL, 0.05),
        "blue": Relationship(ATTACKS, 0.25),
    },
    "pink": {
        "pink": Relationship(RIVAL, 0.4),
        "green": Relationship(RIVAL, 0.15),
        "blue": Relationship(RIVAL, 0.2),
        "white": Relationship(RIVAL, 0.25),
    },
    "blue": {
        "pink": Relationship(RIVAL, 0.3),
        "blue": Relationship(RIVAL, 0.45),
        "green": Relationship(IGNORES, 0.0),
        "white": Relationship(IGNORES, 0.0),
        "cyan": Relationship(IGNORES, 0.0),
    },
    "white": {
        "eggbug": Relationship(EATS, 0.7),
        "pink": Relationship(RIVAL, 0.15),
        "green": Relationship(RIVAL, 0.05),
        "blue": Relationship(RIVAL, 0.35),
        "white": Relationship(RIVAL, 0.25),
    },
    "red": {
        "red": Relationship(ATTACKS, 1.0),
    },
    "cyan": {
        "cyan": Relationship(RIVAL, 0.075),
        "blue": Relationship(ATTACKS, 0.15),
    },
}
_TEMPLATE = {"eggbug": Relationship(EATS, 0.45)}
_LIZARD_DEFAULT = Relationship(RIVAL, 0.1)
_IGNORES = Relationship(IGNORES, 0.0)


class Behavior:
    """LizardAI.Behavior。"""

    Idle = "Idle"
    Hunt = "Hunt"
    ReturnPrey = "ReturnPrey"
    Frustrated = "Frustrated"
    Injured = "Injured"
    Fighting = "Fighting"
    ActingOutMission = "ActingOutMission"
    InvestigateSound = "InvestigateSound"


class MoveBacklog:
    def __init__(self):
        self.tracked_moves = 10
        self.log: list = []

    def reset(self) -> None:
        self.log.clear()

    def report_new_move(self, connection) -> None:
        if connection is not None and (not self.log or self.log[0] != connection):
            self.log.insert(0, connection)
            if len(self.log) > self.tracked_moves:
                self.log.pop()

    def is_move_in_log(self, test_connection, how_many_steps_back: int) -> bool:
        if test_connection is None or not self.log:
            return False
        for i in range(min(how_many_steps_back, len(self.log))):
            if self.log[i] == test_connection:
                return True
        return False


class StuckTracker:
    """卡住检测（只带 MoveBacklog 子模块）。creature.pos 即蜥蜴所在格。"""

    def __init__(self, ai: LizardAI, track_past_positions: bool, track_not_following_current_goal: bool):
        self.ai = ai
        self.track_past_positions = track_past_positions
        self.track_not_following_current_goal = track_not_following_current_goal
        self.past_positions: list = []
        self.stuck_counter = 0
        self.not_following_path_to_current_goal_counter = 0
        self.not_following_current_goal_max = 200
        self.goal_satisfaction_distance = 3
        self.total_tracked_last_positions = 40
        self.check_past_positions_from = 30
        self.past_pos_stuck_distance = 5
        self.past_stuck_positions_close_to_increment_stuck_counter = 10
        self.min_stuck_counter = 100
        self.max_stuck_counter = 200
        self.satisfied_with_this_position = False
        self.move_backlog = MoveBacklog()

    def update(self) -> None:
        ai = self.ai
        pos = ai.lizard.pos_tile
        effectual = ai.path_finder.destination
        if self.track_not_following_current_goal:
            if self.not_following_path_to_current_goal_counter < self.not_following_current_goal_max and (
                effectual != ai.destination
            ):
                self.not_following_path_to_current_goal_counter += 1
            elif self.not_following_path_to_current_goal_counter > 0:
                self.not_following_path_to_current_goal_counter -= 1
        flag = False
        if self.track_past_positions:
            num = 0
            if (
                not self.satisfied_with_this_position
                and effectual is not None
                and (
                    manhattan(pos, effectual) > self.goal_satisfaction_distance
                    or self.not_following_path_to_current_goal_counter
                    > self.not_following_current_goal_max / 2
                )
            ):
                self.past_positions.insert(0, pos)
                if len(self.past_positions) > self.total_tracked_last_positions:
                    self.past_positions.pop()
                for j in range(self.check_past_positions_from, len(self.past_positions)):
                    q = self.past_positions[j]
                    if math.hypot(pos[0] - q[0], pos[1] - q[1]) < self.past_pos_stuck_distance:
                        num += 1
            if num > self.past_stuck_positions_close_to_increment_stuck_counter:
                flag = True
        if flag:
            self.stuck_counter += 1
        else:
            self.stuck_counter -= 2
        self.stuck_counter = max(0, min(self.max_stuck_counter, self.stuck_counter))

    def reset(self) -> None:
        self.stuck_counter = 0

    def utility(self) -> float:
        return inverse_lerp(self.min_stuck_counter, self.max_stuck_counter, self.stuck_counter)


class CreatureRepresentation:
    """Tracker.CreatureRepresentation。elaborate 的带一个不会移动的「幽灵」（最后见到的格 + 世代）。

    原版 Ghost 会沿连接继续走并分叉出多个假设；这里房间里没有视线遮挡，
    丢视野只因超出视距或在头后方，所以幽灵只计世代（Push 一次 +1），不移动。
    """

    def __init__(self, parent: Tracker, represented, elaborate: bool):
        self.parent = parent
        self.represented_creature = represented
        self.elaborate = elaborate
        self.forget_counter = 0
        self.age = 0
        self.dynamic_relationship: DynamicRelationship | None = None
        self._visual_contact = True
        self._ticks_since_seen = 0
        self.delete_me_next_frame = False
        self.last_seen_tile = represented.pos_tile
        self.generation = 0

    @property
    def visual_contact(self) -> bool:
        if self.represented_creature.realized_creature is None:
            self._visual_contact = False
        return self._visual_contact

    @property
    def ticks_since_seen(self) -> int:
        n = self._ticks_since_seen - self.parent.see_around_corners
        return n if n > 0 else 0

    @property
    def lowest_generation_available(self) -> int:
        return self.generation if self.elaborate else 1

    @property
    def estimated_chance_of_finding(self) -> float:
        num = (self.lowest_generation_available * 10.0 + self.ticks_since_seen) / 4.0
        if self._visual_contact:
            return 1.0
        if num < 45.0:
            return max(0.0, min(1.0, 1.0 / (-(1.0 + math.exp(-(num / 12.0 - 5.0)))) + 1.007))
        return 1.0 / (num - 7.0) * 30.0

    def best_guess_for_position(self) -> Coord:
        return Coord(self.ghost_tile if self.elaborate else self.last_seen_tile)

    @property
    def ghost_tile(self) -> tuple[int, int]:
        return self.last_seen_tile

    def heard_this_creature(self) -> None:
        if self._ticks_since_seen > self.parent.see_around_corners + 5:
            self._ticks_since_seen = (self._ticks_since_seen - self.parent.see_around_corners) // 2

    def make_visible(self) -> None:
        self._ticks_since_seen = 0
        self._visual_contact = True

    def push(self) -> None:
        self.generation += 1

    def destroy(self) -> None:
        self.delete_me_next_frame = True

    def update(self) -> None:
        ai = self.parent.ai
        rep = self.represented_creature
        self.age += 1
        was = self._visual_contact
        self._ticks_since_seen += 1
        if self._ticks_since_seen > self.parent.see_around_corners:
            self._visual_contact = False
            real = rep.realized_creature
            if real is not None:
                for chunk in real.body_chunks:
                    if ai.visual_contact_chunk(chunk):
                        self._ticks_since_seen = 0
                        self._visual_contact = True
                        break
        if self._visual_contact:
            if rep.realized_creature is None:
                self._visual_contact = False
                return
            self.last_seen_tile = rep.pos_tile
            if not was:
                ai.creature_spotted(False, self)
            self.forget_counter = 0
            if self.elaborate:
                self.generation = 0
            return
        self.forget_counter += 1
        if rep.realized_creature is None:
            self.destroy()


class DynamicRelationship:
    def __init__(self, rep: CreatureRepresentation, initial: Relationship):
        self.track_rep = rep
        self.current = initial
        rep.dynamic_relationship = self


class Tracker:
    """Tracker(ai, seeAroundCorners 10, maxTracked 10, framesToRemember -1, ghost 0.35/5/5/10)。"""

    def __init__(self, ai: LizardAI):
        self.ai = ai
        self.see_around_corners = 10
        self.max_tracked_creatures = 10
        self.ghost_dismissal_range = 10
        self.creatures: list[CreatureRepresentation] = []

    @property
    def creatures_count(self) -> int:
        return len(self.creatures)

    def get_rep(self, i: int) -> CreatureRepresentation:
        return self.creatures[i]

    def update(self, room_creatures) -> None:
        ai = self.ai
        L = ai.lizard
        rng = L.rng
        reps = self.creatures
        if reps:
            rep = reps[rng.randrange(len(reps))]
            gt = rep.best_guess_for_position().tile
            if not rep.visual_contact and ai.visual_contact_point(L.terrain.middle_of(gt), 0.0):
                near = manhattan(L.pos_tile, gt) < 2 or (
                    math.hypot(L.pos_tile[0] - gt[0], L.pos_tile[1] - gt[1]) < self.ghost_dismissal_range
                    and ai.visual_contact_point(L.terrain.middle_of(gt), 0.0)
                )
                if near:
                    if rep.elaborate:
                        rep.push()
                    else:
                        rep.destroy()
            if rep.visual_contact and rep.represented_creature.dead and ai.tracker_to_discard_dead(rep):
                rep.destroy()
        crit = room_creatures[rng.randrange(len(room_creatures))] if room_creatures else None
        flag = crit is not None
        for i in range(len(reps) - 1, -1, -1):
            r = reps[i]
            r.update()
            if r.represented_creature is crit:
                flag = False
            if r.delete_me_next_frame:
                ai.forget_relationship(r)
                del reps[i]
        if not flag or crit.realized_creature is None:
            return
        for chunk in crit.body_chunks:
            if ai.visual_contact_chunk(chunk):
                self.creature_noticed(crit)
                break

    def representation_for_creature(self, crit) -> CreatureRepresentation | None:
        for r in self.creatures:
            if r.represented_creature is crit:
                return r
        return None

    def creature_noticed(self, crit) -> CreatureRepresentation | None:
        ai = self.ai
        if crit.realized_creature is None:
            return None
        if crit.dead and ai.tracker_to_discard_dead(crit):
            return None
        rep = CreatureRepresentation(self, crit, elaborate=crit.kind_key != "cursor")
        ai.creature_spotted(True, rep)
        ai.establish_dynamic_relationship(rep)
        self.creatures.append(rep)
        if len(self.creatures) > self.max_tracked_creatures:
            worst, worst_score = None, _MAX
            for r in self.creatures:
                inten = (
                    r.dynamic_relationship.current.intensity
                    if r.dynamic_relationship is not None
                    else ai.static_relationship(r.represented_creature).intensity
                )
                gx, gy = r.best_guess_for_position().tile
                px, py = ai.lizard.pos_tile
                score = inten * 100000.0 + (2.0 if r.visual_contact else 1.0) / (
                    1.0 + math.hypot(gx - px, gy - py)
                )
                score /= lerp(r.forget_counter, 100.0, 0.7)
                if score < worst_score:
                    worst, worst_score = r, score
            if worst is rep:
                rep = None
            worst.destroy()
        return rep

    def see_creature(self, crit) -> None:
        r = self.representation_for_creature(crit)
        if r is not None:
            r.make_visible()
        else:
            self.creature_noticed(crit)


class _TrackedPrey:
    def __init__(self, owner: PreyTracker, rep: CreatureRepresentation):
        self.owner = owner
        self.rep = rep
        self.unreachable_counter = 0
        self.at_position_but_cant_see_counter = 0
        self.last_best_guess = None

    @property
    def reachable(self) -> float:
        o = self.owner
        L = o.ai.lizard
        gt = self.rep.best_guess_for_position().tile
        if L.terrain.solid(gt):
            return 0.0
        return inverse_lerp(o.give_up_on_unreachable_prey, 0.0, self.unreachable_counter) * inverse_lerp(
            200.0, 100.0, self.at_position_but_cant_see_counter
        )

    def update(self) -> None:
        o = self.owner
        ai = o.ai
        L = ai.lizard
        pf = ai.path_finder
        gt = self.rep.best_guess_for_position().tile
        if pf._reach is not None:
            flag = pf.coordinate_reachable_and_getbackable(gt)
            if not flag:
                for d in FOUR_DIRS:
                    if flag:
                        break
                    flag = pf.coordinate_reachable_and_getbackable((gt[0] + d[0], gt[1] + d[1]))
            if flag:
                self.unreachable_counter = 0
            else:
                self.unreachable_counter += 1
        dest = pf.destination
        if (
            self.last_best_guess == gt
            and math.hypot(L.pos_tile[0] - gt[0], L.pos_tile[1] - gt[1]) < 5.0
            and dest is not None
            and math.hypot(dest[0] - gt[0], dest[1] - gt[1]) < 5.0
            and visual_contact(L.terrain, L.terrain.middle_of(L.pos_tile), L.terrain.middle_of(gt))
        ):
            self.at_position_but_cant_see_counter += 5
        else:
            self.at_position_but_cant_see_counter -= 1
        self.at_position_but_cant_see_counter = max(0, min(200, self.at_position_but_cant_see_counter))
        self.last_best_guess = gt

    def path_finder_can_get_to_prey(self) -> bool:
        pf = self.owner.ai.path_finder
        gx, gy = self.rep.best_guess_for_position().tile
        for dx, dy in EIGHT_AND_ZERO:
            t = (gx + dx, gy + dy)
            if pf.coordinate_reachable(t) and pf.coordinate_possible_to_get_back_from(t):
                return True
        for dx, dy in FOUR_DIRS:
            t = (gx + dx * 2, gy + dy * 2)
            if pf.coordinate_reachable(t) and pf.coordinate_possible_to_get_back_from(t):
                return True
        return False

    def attractiveness(self) -> float:
        o = self.owner
        ai = o.ai
        pf = ai.path_finder
        num = ai.dynamic_relationship(self.rep).intensity
        gt = self.rep.best_guess_for_position().tile
        f = o.distance_estimation(ai.lizard.pos_tile, gt)
        f = f**1.5
        f = lerp(f, 1.0, 0.5)
        if not pf.coordinate_reachable(gt):
            num /= 2.0
        if not pf.coordinate_possible_to_get_back_from(gt):
            num /= 2.0
        if not self.path_finder_can_get_to_prey():
            num /= 2.0
        num *= self.rep.estimated_chance_of_finding
        num *= self.reachable
        real = self.rep.represented_creature.realized_creature
        if real is not None and real.grabbed_by:
            grabber = real.grabbed_by[0].grabber
            same = getattr(grabber, "lizard_params", None) is not None
            num *= 1.25 if same else 1.1  # 同祖先 / 别的生物叼着的猎物，兴趣略增
        num /= f
        num *= inverse_lerp(
            o.give_up_on_ghost_generation,
            o.give_up_on_ghost_generation / 2.0,
            self.rep.lowest_generation_available,
        )
        return num


def _guarded(rep) -> bool:
    """猎物正被别的蜥蜴就地吃着（护食，抢不走）：不当作目标，否则会一直贴上去咬。"""
    real = rep.represented_creature.realized_creature
    return real is not None and any(getattr(g.grabber, "eating", False) for g in real.grabbed_by)


class PreyTracker:
    """PreyTracker(ai, 5, 2, 3, 70, 0.5)。"""

    def __init__(self, ai: LizardAI):
        self.ai = ai
        self.max_remembered_creatures = 5
        self.persistance_bias = 2.0
        self.sure_to_get_prey_distance = 3.0
        self.sure_to_lose_prey_distance = 70.0
        self.frustration = 0.0
        self.frustration_speed = 0.0125
        self.give_up_on_unreachable_prey = 400
        self.give_up_on_ghost_generation = 50
        self.prey: list[_TrackedPrey] = []
        self.current: _TrackedPrey | None = None

    @property
    def most_attractive_prey(self) -> CreatureRepresentation | None:
        return self.current.rep if self.current is not None else None

    def distance_estimation(self, a, b) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def utility(self) -> float:
        cur = self.current
        if cur is None:
            return 0.0
        L = self.ai.lizard
        num = self.distance_estimation(L.pos_tile, cur.rep.best_guess_for_position().tile)
        a, b = self.sure_to_get_prey_distance, self.sure_to_lose_prey_distance
        num = lerp(1.0 - inverse_lerp(a, b, num), lerp(a, b, 0.25) / max(num, 1e-6), 0.5)
        return (
            min(
                num,
                cur.rep.estimated_chance_of_finding
                * inverse_lerp(
                    self.give_up_on_ghost_generation,
                    self.give_up_on_ghost_generation / 2.0,
                    cur.rep.lowest_generation_available,
                ),
            )
            * self.ai.dynamic_relationship(cur.rep).intensity ** 0.75
            * cur.reachable
        )

    def add_prey(self, rep: CreatureRepresentation) -> None:
        for p in self.prey:
            if p.rep is rep:
                return
        self.prey.append(_TrackedPrey(self, rep))
        if len(self.prey) > self.max_remembered_creatures:
            worst = min(self.prey, key=lambda p: p.attractiveness())
            worst.rep.destroy()
            self.prey.remove(worst)
        self.update()

    def forget_prey(self, rep: CreatureRepresentation) -> None:
        self.prey = [p for p in self.prey if p.rep is not rep]
        if self.current is not None and self.current.rep is rep:
            self.current = None

    def update(self) -> None:
        best_v = -_MAX
        best = None
        for i in range(len(self.prey) - 1, -1, -1):
            p = self.prey[i]
            p.update()
            v = p.attractiveness()
            p.rep.forget_counter = 0
            if p is self.current:
                v *= self.persistance_bias
            if p.rep.delete_me_next_frame:
                del self.prey[i]
            elif v > best_v and not _guarded(p.rep):
                best_v = v
                best = p
        self.current = best
        if best is not None and not best.path_finder_can_get_to_prey():
            self.frustration = max(0.0, min(1.0, self.frustration + self.frustration_speed))
        else:
            self.frustration = max(0.0, min(1.0, self.frustration - self.frustration_speed * 4.0))


class _AngerRelationship:
    def __init__(
        self, tracker: AgressionTracker, rep: CreatureRepresentation, anger: float, base_anger: float
    ):
        self.tracker = tracker
        self.rep = rep
        self.anger = anger
        self.base_anger = base_anger

    def update(self) -> None:
        ai = self.tracker.ai
        L = ai.lizard
        gx, gy = self.rep.best_guess_for_position().tile
        num = self.base_anger
        num *= inverse_lerp(10.0 + self.base_anger * 70.0, 5.0, manhattan(L.pos_tile, (gx, gy)))
        prey = ai.prey_tracker.most_attractive_prey
        if prey is not None:
            b = inverse_lerp(10.0, 3.0, manhattan((gx, gy), prey.best_guess_for_position().tile))
            num = lerp(num, b, 0.5)
        # 同一个房间，AttractionValueForCreature 对谁都一样，inverseLerp(0.3, 0.6, 1) = 1
        if ai.has_retreated(self.rep.represented_creature):
            num = 0.0  # 输家认输「离开」了 / 伤重退走了（原版它们真的离开房间，赢家的怒气自然散去）
        t = self.tracker
        if self.anger < num:
            self.anger = max(0.0, min(num, self.anger + t.anger_speed_up))
        elif self.anger > num:
            self.anger = max(num, min(1.0, self.anger - t.anger_speed_down))
        self.rep.forget_counter = 0


class AgressionTracker:
    """AgressionTracker(ai, 0.001, 0.001)：对每个对手有一个怒气，最高的是 Fighting 的目标。"""

    def __init__(self, ai: LizardAI, speed_up: float, speed_down: float):
        self.ai = ai
        self.anger_speed_up = speed_up
        self.anger_speed_down = speed_down
        self.creatures: list[_AngerRelationship] = []
        self.highest_anger = 0.0
        self.highest: _AngerRelationship | None = None

    def update(self) -> None:
        self.highest_anger = 0.0
        self.highest = None
        for i in range(len(self.creatures) - 1, -1, -1):
            c = self.creatures[i]
            c.update()
            if c.rep.delete_me_next_frame:
                del self.creatures[i]
            elif c.anger > self.highest_anger:
                self.highest_anger = c.anger
                self.highest = c

    def utility(self) -> float:
        return inverse_lerp(0.35, 1.0, self.highest_anger)

    def agression_target(self) -> CreatureRepresentation | None:
        return self.highest.rep if self.highest is not None else None

    def add_creature(self, rep: CreatureRepresentation, initial: float, base: float) -> None:
        if any(c.rep is rep for c in self.creatures):
            return
        self.creatures.append(_AngerRelationship(self, rep, initial, base))

    def forget_creature(self, rep: CreatureRepresentation) -> None:
        self.creatures = [c for c in self.creatures if c.rep is not rep]

    def increment_anger(self, rep: CreatureRepresentation, add: float) -> None:
        for c in self.creatures:
            if c.rep is rep:
                c.anger = max(0.0, min(1.0, c.anger + add))
                return

    def set_anger(self, rep: CreatureRepresentation, anger: float, base: float) -> None:
        for c in self.creatures:
            if c.rep is rep:
                c.anger = max(0.0, min(1.0, anger))
                if base != -1.0:
                    c.base_anger = max(0.0, min(1.0, base))
                return


class _Source:
    """NoiseTracker.TheorizedSource。"""

    def __init__(self, tracker: NoiseTracker, pos: V2, rep: CreatureRepresentation | None):
        self.tracker = tracker
        self.pos = pos
        self.rep = rep
        self.age = 0
        self.slated = False
        self.last_strength = 0.0

    def update(self) -> None:
        self.age += 1
        if self.rep is not None and self.rep.delete_me_next_frame:
            self.rep = None
        if self.age > self.tracker.forget_time:
            self.slated = True
        self.last_strength = max(10.0, self.last_strength * 0.6)

    def noise_match(self, noise) -> float:
        if self.rep is None:
            return distance(self.pos, noise.pos) + 200.0 + self.age / 5.0
        return self.tracker.noise_match(noise, self.rep) + self.age / 5.0

    def refresh(self, noise) -> None:
        self.pos = noise.pos
        self.age = 0
        self.last_strength = noise.strength
        r = self.rep
        if r is None:
            return
        r.heard_this_creature()
        L = self.tracker.ai.lizard
        T = L.terrain
        t = tile_xy(noise.pos)
        gt = r.best_guess_for_position().tile
        if distance(noise.pos, T.middle_of(gt)) < 100.0 or not r.elaborate:
            r.last_seen_tile = t
        r.generation = 0


class NoiseTracker:
    """NoiseTracker(ai, tracker)：听到的动静归到某个已知生物或一个「不明声源」；
    不明声源多了就去查看（InvestigateSound），第一次听到先扭头（HearSound，见 react_to_noise）。"""

    def __init__(self, ai: LizardAI, tracker: Tracker):
        self.ai = ai
        self.tracker = tracker
        self.sources: list[_Source] = []
        self.ignore_seen_noises = True
        self.forget_time = 1200
        self.hearing_skill = 1.0
        self.mysterious_noises = 0.0
        self.mysterious_noise_counter = 0
        self.sound_to_examine: _Source | None = None

    def utility(self) -> float:
        if self.sound_to_examine is None:
            return 0.0
        return inverse_lerp(1.0, 20.0, self.mysterious_noises) ** 0.5

    @property
    def examine_pos(self) -> tuple[int, int]:
        return tile_xy(self.sound_to_examine.pos)

    def update(self) -> None:
        ai = self.ai
        for i in range(len(self.sources) - 1, -1, -1):
            if self.sources[i].slated:
                del self.sources[i]
                self._update_examine_sound()
            else:
                self.sources[i].update()
        s = self.sound_to_examine
        if s is not None:
            m = manhattan(ai.lizard.pos_tile, tile_xy(s.pos))
            if m < 3 or (m < 10 and ai.visual_contact_point(s.pos, 0.0)):
                s.slated = True
                self._update_examine_sound()
        if self.mysterious_noise_counter > 0:
            self.mysterious_noise_counter -= 1
        elif self.mysterious_noises > 0.0:
            self.mysterious_noises = max(0.0, self.mysterious_noises - 0.0125)

    def how_interesting(self, noise) -> float:
        src = noise.source
        if getattr(src, "is_creature", False) and getattr(src, "lizard_params", None) is not None:
            return noise.interesting * 0.1  # 同一祖先（都是蜥蜴）
        return noise.interesting

    def noise_match(self, noise, rep: CreatureRepresentation) -> float:
        if rep.visual_contact and self.ignore_seen_noises:
            return _MAX
        return distance(noise.pos, self.ai.lizard.terrain.middle_of(rep.best_guess_for_position().tile))

    def heard_noise(self, noise) -> None:
        ai = self.ai
        L = ai.lizard
        tr = self.tracker
        if not dist_less(
            L.body_chunks[0].pos,
            noise.pos,
            noise.strength * self.hearing_skill,
        ):
            return
        if self.ignore_seen_noises:
            if ai.visual_contact_point(noise.pos, 0.0):
                return
            rp = tr.representation_for_creature(noise.source) if noise.source.is_creature else None
            if rp is None:
                for g in noise.source.grabbed_by:
                    rp = tr.representation_for_creature(g.grabber)
                    if rp is not None:
                        break
            if rp is not None and rp.visual_contact:
                return
        best, src = _MAX, None
        for sc in self.sources:
            m = sc.noise_match(noise)
            lim = (
                lerp_map(sc.rep.ticks_since_seen, 20.0, 600.0, 200.0, 1000.0) if sc.rep is not None else 300.0
            )
            if m < best and m < lim:
                best, src = m, sc
        if src is not None:
            if src.rep is None and src.age > 10:
                self.mysterious_noises += self.how_interesting(noise)
                self.mysterious_noise_counter = 200
            src.refresh(noise)
        else:
            rep, best, n = None, _MAX, 0
            for r in tr.creatures:
                m = self.noise_match(noise, r)
                if m < best and m < lerp_map(r.ticks_since_seen, 20.0, 600.0, 200.0, 1000.0):
                    best, rep = m, r
                if not r.visual_contact:
                    n += 1
            if best > lerp_map(float(n), 0.0, float(tr.max_tracked_creatures), 1000.0, 300.0):
                rep = None
            if rep is None:
                self.mysterious_noises += self.how_interesting(noise)
                self.mysterious_noise_counter = 200
            src = _Source(self, noise.pos, rep)
            self.sources.append(src)
            src.refresh(noise)
        self._update_examine_sound()
        ai.react_to_noise(src, noise)

    def _update_examine_sound(self) -> None:
        self.sound_to_examine = None
        L = self.ai.lizard
        best = _MAX
        for sc in self.sources:
            if sc.slated:
                continue
            d = distance(L.body_chunks[0].pos, sc.pos)
            if not self.ai.path_finder.coordinate_reachable_and_getbackable(tile_xy(sc.pos)):
                d += 500.0
            d += lerp_map(sc.age, self.forget_time / 2, self.forget_time, 0.0, 400.0)
            if sc.rep is None and d < best:
                best = d
                self.sound_to_examine = sc


class LizardAI:
    def __init__(self, lizard):
        self.lizard = lizard
        self.path_finder = lizard.pather
        self.tracker = Tracker(self)
        self.prey_tracker = PreyTracker(self)
        if lizard.lizard_params.key == "red":
            self.prey_tracker.give_up_on_unreachable_prey = 1800
        self.stuck_tracker = StuckTracker(self, True, True)
        self.agression_tracker = AgressionTracker(self, 0.001, 0.001)
        self.noise_tracker = NoiseTracker(self, self.tracker)
        self.submitted_to = None
        self.rest_spot = None
        self.leave_ticks = 0  # 输给对手后「离开」的剩余 tick（原版是任务 LeaveRoom）
        self.relationships: list[DynamicRelationship] = []
        self.behavior = Behavior.Idle
        self.excitement = 0.5
        self.panic = 0
        self.hunger = 0.0
        self.fear = 0.0
        self.run_speed = 0.0
        self.current_utility = 0.0
        self.prey_utility = 0.0  # UtilityComparer 里 PreyTracker 的平滑后（加权）效用
        self.idle_counter = 0
        self.idle_spot_win_streak = 0
        self.idle_restlessness = 0
        self.unable_to_find_comfortable_position = 0
        self.focus_creature: CreatureRepresentation | None = None
        self.casual_aggression_target: CreatureRepresentation | None = None
        self.attempt_bite_frames = 0
        self.eat_counter = 0
        self.eat_ticks = 0
        self.return_time = 0
        self.exit_tile: tuple[int, int] | None = None
        self.destination: tuple[int, int] | None = None
        self._forbidden_idle_spot: tuple[int, int] | None = None
        self.path_finder.walk_past_point_of_no_return = True

    # 目的地与关系

    def set_destination(self, tile) -> None:
        self.destination = (int(tile[0]), int(tile[1]))
        self.path_finder.set_destination(self.destination)

    def static_relationship(self, crit) -> Relationship:
        k = crit.kind_key
        rel = _STATIC[self.lizard.lizard_params.key].get(k) or _TEMPLATE.get(k)
        if rel is None:
            rel = _LIZARD_DEFAULT if getattr(crit, "lizard_params", None) is not None else _IGNORES
        return rel

    def establish_dynamic_relationship(self, rep: CreatureRepresentation) -> None:
        rel = self.static_relationship(rep.represented_creature)
        dr = DynamicRelationship(rep, rel)
        self.relationships.append(dr)
        if rel.type in (EATS, ATTACKS):
            self.prey_tracker.add_prey(rep)
        elif rel.type == RIVAL:
            self.agression_tracker.add_creature(rep, 0.1, rel.intensity)

    def forget_relationship(self, rep: CreatureRepresentation) -> None:
        self.relationships = [r for r in self.relationships if r.track_rep is not rep]
        self.prey_tracker.forget_prey(rep)
        self.agression_tracker.forget_creature(rep)

    def creature_relationship(self, rep) -> Relationship:
        return self.dynamic_relationship(rep)

    def dynamic_relationship(self, x) -> Relationship:
        """x 是 CreatureRepresentation 或被代表的生物（物体）。"""
        if isinstance(x, CreatureRepresentation):
            if x.dynamic_relationship is not None:
                return x.dynamic_relationship.current
            return self.static_relationship(x.represented_creature)
        rep = self.tracker.representation_for_creature(x)
        if rep is not None and rep.dynamic_relationship is not None:
            return rep.dynamic_relationship.current
        return self.static_relationship(x)

    def tracker_to_discard_dead(self, x) -> bool:
        """死了的生物只有不是猎物时才丢掉。"""
        crit = x.represented_creature if isinstance(x, CreatureRepresentation) else x
        return self.static_relationship(crit).type != EATS

    # 视觉

    def visual_score(self, point: V2, bonus: float) -> float:
        """ArtificialIntelligence.VisualScore 减去 LizardAI 的朝向项。"""
        L = self.lizard
        p = L.lizard_params
        c0, c1 = L.body_chunks[0], L.body_chunks[1]
        vp = c0.pos
        radius = p.visual_radius * (1.0 + bonus)
        if not dist_less(vp, point, radius):
            num = 0.0
        else:
            num = inverse_lerp(radius, 0.0, distance(vp, point))
            if L.terrain.narrow_space(tile_xy(point)):
                num -= 0.5
        return num - inverse_lerp(
            p.perfect_vision_angle,
            p.periferal_vision_angle,
            dot((c0.pos - c1.pos).normalized, (point - c1.pos).normalized),
        )

    def visual_contact_point(self, point: V2, bonus: float) -> bool:
        if self.visual_score(point, bonus) <= 0.0:
            return False
        L = self.lizard
        return visual_contact(L.terrain, L.body_chunks[0].pos, point)

    def visual_contact_chunk(self, chunk) -> bool:
        mbv = self.lizard.lizard_params.movement_based_vision
        owner_bonus = getattr(chunk.owner, "visibility_bonus", 0.0)
        step = distance(chunk.last_pos, chunk.pos)
        bonus = lerp(-mbv, 1.0, inverse_lerp(1.0, 10.0, step)) * mbv + owner_bonus * (1.0 - mbv * 0.5)
        return self.visual_contact_point(chunk.pos, max(-1.0, min(1.0, bonus)))

    # 坠落风险

    def unpleasant_fall_risk(self, tile) -> bool:
        T = self.lizard.terrain
        fy = T.fall_risk_y(tile)
        if fy < 0:
            return True
        if fy < tile[1] - 20:
            return True
        if fy < tile[1] - 10 and not self.path_finder.coordinate_possible_to_get_back_from((tile[0], fy)):
            return True
        return False

    def fall_risk(self, tile) -> bool:
        return self.lizard.terrain.fall_risk_y(tile) < self.lizard.pos_tile[1] - 5

    # 事件

    def bit_creature(self, chunk) -> None:
        if not self.unpleasant_fall_risk(self.lizard.pos_tile):
            from .physics import Animation

            self.lizard.enter_animation(Animation.ShakePrey, True)

    def creature_spotted(self, first_spot: bool, rep: CreatureRepresentation) -> None:
        from .physics import Animation

        L = self.lizard
        g = getattr(L, "graphics_module", None)
        if g is not None and g.creature_looker is not None:
            g.creature_looker.reevaluate_look_object(rep, 2.0 if first_spot else 4.0)
        rel = self.dynamic_relationship(rep)
        gr = L.grasps[0]
        if (
            rel.go_for_kill
            and rel.intensity > (0.2 if first_spot else 0.45)
            and (gr is None or gr.grabbed is not rep.represented_creature)
        ):
            L.enter_animation(Animation.PreySpotted if first_spot else Animation.PreyReSpotted, False)

    # 每 tick

    def _utilities(self) -> list:
        """UtilityComparer 里各模块的（加权）效用，按 AddModule 顺序；没有威胁、雨、友伴。"""
        L = self.lizard
        injury = s_curve(inverse_lerp(0.2, 0.9, 1.0 - max(0.0, min(1.0, L.health))), 0.01)
        injury *= 0.4 if L.lizard_params.key == "red" else 0.9
        fight = self.agression_tracker.utility() * 0.25 * L.health
        mission = 0.4 * 0.8 if self.leave_ticks > 0 else 0.0
        noise = self.noise_tracker.utility() * 0.2
        return [
            (Behavior.Hunt, self.prey_utility),
            (Behavior.Injured, injury),
            (Behavior.Fighting, fight),
            (Behavior.ActingOutMission, mission),
            (Behavior.InvestigateSound, noise),
        ]

    def determine_behavior(self) -> str:
        L = self.lizard
        behavior = Behavior.Idle
        best = 0.0
        for name, u in self._utilities():
            if u > best:
                best, behavior = u, name
        self.current_utility = best
        if self.current_utility < 0.05:
            self.current_utility = 0.05
            behavior = Behavior.Idle
        g = L.grasps[0]
        if g is not None and g.grabbed.is_creature and self.dynamic_relationship(g.grabbed).type == EATS:
            behavior = Behavior.ReturnPrey
            self.current_utility = 1.0
        pt = self.prey_tracker
        prey = pt.most_attractive_prey
        if (
            behavior == Behavior.Hunt
            and prey is not None
            and pt.frustration > 0.75
            and L.lizard_params.key != "red"
            and prey.estimated_chance_of_finding > 0.4
            and dist_less(
                L.body_chunks[0].pos, L.terrain.middle_of(prey.best_guess_for_position().tile), 350.0
            )
        ):
            behavior = Behavior.Frustrated
        return behavior

    def update(self) -> None:
        from .physics import Animation

        L = self.lizard
        rng = L.rng
        T = L.terrain
        p = L.lizard_params
        if self.panic > 0:
            self.panic -= 1
        self.hunger = self.prey_utility / PREY_WEIGHT
        self.excitement = lerp(self.excitement, max(self.hunger, self.fear), 0.1)
        self.behavior = self.determine_behavior()
        L.jaw_open -= 0.01
        b = self.behavior
        if b == Behavior.Hunt:
            prey = self.prey_tracker.most_attractive_prey
            if prey is not None:
                self._aggressive_behavior(prey, 1.0)
            self.run_speed = lerp(self.run_speed, max(self.hunger, 0.3), 0.1)
            if rng.random() < 0.0125:
                L.say("BloodLust")
        elif b == Behavior.Fighting:
            self._fighting()
        elif b == Behavior.Idle:
            self._idle()
            if rng.random() < 0.00125:
                L.say("Boredom")
        elif b == Behavior.ReturnPrey:
            self._return_prey()
        elif b == Behavior.Injured:
            self._retreat()
            if rng.random() < 0.0125:
                L.say("PainIdle", 1.0 - L.health)
        elif b == Behavior.Frustrated:
            self.focus_creature = self.prey_tracker.most_attractive_prey
            self.run_speed = lerp(self.run_speed, 1.0, 0.5)
            if rng.random() < 0.1 or (
                self.destination is not None and manhattan(L.pos_tile, self.destination) < 10
            ):
                cand = (rng.randrange(T.cols), rng.randrange(T.rows))
                pf = self.path_finder
                if pf.coordinate_reachable(cand) and pf.coordinate_possible_to_get_back_from(cand):
                    self.set_destination(cand)
                    self.idle_restlessness = rng.randrange(30, 100)
            if rng.random() < 0.0125:
                L.enter_animation(Animation.PreyReSpotted, False)
            if rng.random() < 0.0125:
                L.body_wiggle_counter = max(L.body_wiggle_counter, int(rng.random() * 100.0))
            if rng.random() < 0.0125:
                L.say("Frustration")
        elif b == Behavior.ActingOutMission:
            self._leave_mission()
            self.run_speed = lerp(self.run_speed, 0.6, 0.05)
        elif b == Behavior.InvestigateSound:
            if self.noise_tracker.sound_to_examine is not None:
                self.set_destination(self.noise_tracker.examine_pos)
            self.run_speed = lerp(self.run_speed, 0.6, 0.2)
        if b != Behavior.ReturnPrey:
            self.reset_eating()
        if b != Behavior.Injured:
            self.rest_spot = None
        if b != Behavior.Idle and p.key == "red":
            self.run_speed = self.run_speed**0.7
        self.run_speed = max(self.run_speed, self.stuck_tracker.utility())
        self.noise_tracker.hearing_skill = lerp_map(self.run_speed, 0.0, 0.6, 1.3, 0.6)
        tr = self.tracker
        if L.grasps[0] is None and tr.creatures_count > 0:
            rep = tr.get_rep(rng.randrange(tr.creatures_count))
            real = rep.represented_creature.realized_creature
            c = self.casual_aggression_target
            if (
                (
                    self.do_i_want_to_bite_this_creature(rep)
                    or (rng.random() > L.health and rng.random() < 0.05)
                )
                and rep.visual_contact
                and real is not None
                and (
                    c is None
                    or c.represented_creature.realized_creature is None
                    or distance(L.body_chunks[0].pos, real.main_body_chunk.pos)
                    < distance(
                        L.body_chunks[0].pos, c.represented_creature.realized_creature.main_body_chunk.pos
                    )
                )
            ):
                self.casual_aggression_target = rep
        c = self.casual_aggression_target
        if c is not None:
            real = c.represented_creature.realized_creature
            if real is None or c.delete_me_next_frame:
                self.casual_aggression_target = None
            elif (
                rng.random() < 0.5
                and c.visual_contact
                and dist_less(real.main_body_chunk.pos, L.body_chunks[0].pos, p.attempt_bite_radius)
            ):
                L.attempt_bite(real)
        self._modules_update()

    def _modules_update(self) -> None:
        """ArtificialIntelligence.Update：按 AddModule 顺序更新各模块。"""
        L = self.lizard
        crits = [c for c in getattr(L.ctx, "creatures", ()) if c is not L]
        self.tracker.update(crits)
        self.noise_tracker.update()
        self.prey_tracker.update()
        self.agression_tracker.update()
        self.prey_utility = lerp(self.prey_utility, self.prey_tracker.utility() * PREY_WEIGHT, PREY_SMOOTH)
        if self.leave_ticks > 0:
            self.leave_ticks -= 1
        self.stuck_tracker.update()

    def heard_noise(self, noise) -> None:
        self.noise_tracker.heard_noise(noise)

    def react_to_noise(self, source: _Source, noise) -> None:
        """LizardAI.ReactToNoise。"""
        from .physics import Animation

        L = self.lizard
        if source.rep is not None and source.rep is self.prey_tracker.most_attractive_prey:
            L.enter_animation(Animation.PreyReSpotted, False)
            return
        if (
            self.behavior in (Behavior.Idle, Behavior.InvestigateSound, "Lurk", "Travelling")
            and source is self.noise_tracker.sound_to_examine
        ):
            L.enter_animation(Animation.HearSound, False)
            return
        L.say("GeneralSmallNoise")
        L.bubble = max(L.bubble, 5)

    # 对手：交流、战斗、认输

    def send_communication(self, other, signal: str) -> None:
        """LizardAI.SendCommunication：示威 / 认输，对方看得见才收得到。"""
        if other is None or other.dead:
            return
        L = self.lizard
        self.focus_creature = self.tracker.representation_for_creature(other)
        g = L.graphics_module
        if signal == "Agression":
            g.show_dominance += L.rng.random()
            L.say("Dominance")
        else:
            g.show_dominance -= L.rng.random()
            L.say("Submission")
        other.ai.receive_communication(L, signal)

    def receive_communication(self, other, signal: str) -> None:
        L = self.lizard
        if not self.visual_contact_chunk(other.body_chunks[0]):
            return
        r = self.tracker.representation_for_creature(other)
        self.focus_creature = r
        if signal == "Agression":
            if other.ai.submitted_to is not L:
                if self.submitted_to is not other and r is not None:
                    self.agression_tracker.increment_anger(r, 0.1)
                if L.rng.random() < 1.0 / 24.0:
                    self.send_communication(other, "Submission")
                    if r is not None:
                        self.agression_tracker.set_anger(r, 0.0, 0.0)
                    self.submitted_to = other
                    self.leave_ticks = 1000  # 原版：MissionTracker.LeaveRoom(0.4, 1000)
        elif r is not None:
            self.agression_tracker.set_anger(r, 0.0, -1.0)

    def _fighting(self) -> None:
        from .physics import Animation

        L = self.lizard
        rng = L.rng
        self.focus_creature = f = self.agression_tracker.agression_target()
        if f is None:
            return
        real = f.represented_creature.realized_creature
        main = L.body_chunks[0]
        is_liz = getattr(real, "lizard_params", None) is not None
        if (
            f.visual_contact
            and dist_less(main.pos, real.main_body_chunk.pos, 160.0)
            and (
                not is_liz
                or distance(main.pos, real.main_body_chunk.pos) < distance(main.pos, real.body_chunks[2].pos)
            )
        ):
            if rng.random() < 0.05:
                L.enter_animation(Animation.FightingStance, False)
            self.run_speed = lerp(self.run_speed, 0.2, 0.15)
        else:
            self.run_speed = lerp(self.run_speed, 0.8, 0.15)
            if rng.random() < 1.0 / 180.0:
                L.enter_animation(Animation.FightingStance, False)
        if is_liz and rng.random() < 0.05 and rng.random() < self.dynamic_relationship(f).intensity:
            self.send_communication(real, "Agression")
        self._aggressive_behavior(f, 0.025)

    def has_retreated(self, other) -> bool:
        """对手已经向我认输离开，或伤重退走：对它不再有怒气。"""
        oai = getattr(other, "ai", None)
        if oai is None:
            return False
        L = self.lizard
        return (oai.submitted_to is L and oai.leave_ticks > 0) or (
            oai.behavior == Behavior.Injured and other.health < 0.5
        )

    def _retreat(self) -> None:
        """受伤：原版回窝养伤（run_speed 慢慢升到 1）。没有窝，改成跑到离对手最远的一个可达点，到了就趴着。"""
        L = self.lizard
        rng = L.rng
        T = L.terrain
        rivals = [
            r.represented_creature.pos_tile
            for r in self.tracker.creatures
            if self.dynamic_relationship(r).type == RIVAL
            and r.represented_creature.realized_creature is not None
        ]
        ref = min(rivals, key=lambda t: manhattan(t, L.pos_tile)) if rivals else None
        dest = self.destination
        near = ref is not None and dest is not None and manhattan(ref, dest) < 15
        if dest is None or (near and rng.random() < 0.02) or self.rest_spot is None:
            pf = self.path_finder
            best, best_d = None, -1
            for _ in range(30):
                cand = (rng.randrange(T.cols), rng.randrange(T.rows))
                if not T.accessible(cand, L.lizard_params) or not pf.coordinate_reachable_and_getbackable(
                    cand
                ):
                    continue
                d = manhattan(cand, ref) if ref is not None else manhattan(cand, L.pos_tile)
                if d > best_d:
                    best, best_d = cand, d
            if best is not None:
                self.rest_spot = best
                self.set_destination(best)
        if manhattan(L.pos_tile, self.destination) < 5:
            self.run_speed = lerp(self.run_speed, 0.0, 0.5)
        else:
            self.run_speed = lerp(self.run_speed, 1.0, 0.01 if self.run_speed > 0.4 else 0.1)

    def _leave_mission(self) -> None:
        """输给对手后离开一阵：每隔一会儿在可达的点里挑离对手最远的作目的地（原版是离开房间，这里没有出口）。"""
        L = self.lizard
        rng = L.rng
        T = L.terrain
        ref = self.submitted_to.pos_tile if self.submitted_to is not None else L.pos_tile
        if (
            self.destination is not None
            and self.leave_ticks % 60 != 0
            and manhattan(L.pos_tile, self.destination) >= 5
        ):
            return
        best, best_d = None, -1
        pf = self.path_finder
        for _ in range(30):
            cand = (rng.randrange(T.cols), rng.randrange(T.rows))
            if not T.accessible(cand, L.lizard_params) or not pf.coordinate_reachable_and_getbackable(cand):
                continue
            d = manhattan(cand, ref)
            if d > best_d:
                best, best_d = cand, d
        if best is not None:
            self.set_destination(best)

    # 行为

    def _aggressive_behavior(self, target: CreatureRepresentation, tongue_chance: float) -> None:
        from .physics import Animation

        L = self.lizard
        p = L.lizard_params
        rng = L.rng
        self.casual_aggression_target = None
        self.set_destination(target.best_guess_for_position().tile)
        real = target.represented_creature.realized_creature
        main = L.body_chunks[0]
        if L.animation == Animation.PrepareToLounge:
            L.jaw_open = lerp(L.jaw_open, 0.2, 0.2)
        elif L.animation == Animation.Lounge:
            L.jaw_open += 0.2
        elif L.animation == Animation.ShootTongue:
            if L.tongue.out:
                L.jaw_open += 0.1
            else:
                L.jaw_open = lerp(L.jaw_open, rng.random(), 0.2)
        elif target.visual_contact and real is not None:
            L.jaw_open = inverse_lerp(
                400.0, 90.0 + p.bite_in_front, distance(main.pos, real.main_body_chunk.pos)
            )
        else:
            L.jaw_open = lerp(L.jaw_open, inverse_lerp(0.6, 0.9, self.hunger * self.hunger) * 0.7, 0.2)
        if p.key == "red" and target.visual_contact:
            L.jaw_open = min(max(L.jaw_open + 0.1, 0.0), 1.0)
        self.focus_creature = target
        if not target.visual_contact or real is None:
            return
        pos_tile = L.pos_tile
        ftile = real.pos_tile
        T = L.terrain
        if (
            L.lounge_delay < 1
            and rng.random() < p.lounge_tendensy
            and not self.unpleasant_fall_risk(pos_tile)
            and not self.fall_risk(pos_tile)
            and not self.unpleasant_fall_risk(ftile)
            and dist_less(main.pos, real.main_body_chunk.pos, p.lounge_distance)
            and not T.narrow_space(ftile)
            and not T.narrow_space(pos_tile)
            and (p.key != "green" or T.solid(tile_xy(main.pos + V2(0.0, -20.0))))
            and L.legs_gripping > 2
        ):
            L.enter_animation(Animation.PrepareToLounge, False)
        elif (
            L.tongue is not None
            and L.tongue.ready
            and L.grasps[0] is None
            and dist_less(main.pos, real.main_body_chunk.pos, p.tongue_attack_range)
            and not dist_less(
                main.pos, real.main_body_chunk.pos, lerp(p.attempt_bite_radius, p.tongue_attack_range, 0.2)
            )
            and rng.random() < p.tongue_chance * tongue_chance
        ):
            L.enter_animation(Animation.ShootTongue, False)
        if target.age > 120 and L.jaw_ready_for_bite:
            self.attempt_bite_frames += 1
            for ch in real.body_chunks:
                if dist_less(ch.pos, main.pos, p.attempt_bite_radius):
                    L.attempt_bite(real)
                    break
        else:
            if self.attempt_bite_frames > 5:
                L.jaws_snap_shut(real.main_body_chunk.pos)
            self.attempt_bite_frames = 0

    def _idle(self) -> None:
        L = self.lizard
        T = L.terrain
        rng = L.rng
        if self.destination is None:
            self.set_destination(L.pos_tile)
            self.idle_counter = 0
        flag = True
        num = self.idle_counter
        self.idle_counter -= 1
        dest = self.destination
        if manhattan(L.pos_tile, dest) < 5:
            self.idle_counter -= L.lizard_params.idle_counter_subtract_when_close_to_idle_pos
            self.idle_restlessness -= 1
            flag = self.idle_counter < 1 or self.idle_restlessness > 0
            if not flag and not self._comfortable_idle_position():
                self.unable_to_find_comfortable_position += 1
                flag = True
            elif any(c.vel.magnitude > 2.0 for c in L.body_chunks):
                self.unable_to_find_comfortable_position += 1
            else:
                self.unable_to_find_comfortable_position = 0
            if self.unable_to_find_comfortable_position > 40:
                self.idle_counter = 0
                self.unable_to_find_comfortable_position = 0
            elif L.is_tile_solid(0, 0, -1) and L.is_tile_solid(1, 0, -1) and L.is_tile_solid(2, 0, -1):
                for c in L.body_chunks:
                    c.vel = V2(c.vel.x, c.vel.y - 0.1)
            if self.idle_restlessness < 40 and rng.random() < 0.0016666667:
                self.idle_restlessness = rng.randrange(1, 40)
        if self._idle_spot_score(self.destination) == _MAX or (
            self._crowd(self.destination) > 0 and rng.random() < 0.01
        ):
            self.idle_counter = 0
        if self.idle_counter < 1:
            if num > 0:
                self._forbidden_idle_spot = self.destination
            cand = (rng.randrange(T.cols), rng.randrange(T.rows))
            if self._idle_spot_score(cand) < self._idle_spot_score(self.destination):
                self.set_destination(cand)
                self.idle_spot_win_streak = 0
            else:
                self.idle_spot_win_streak += 1
                if self.idle_spot_win_streak > 50:
                    self.idle_counter = rng.randrange(1000, 4000)
                    self.idle_spot_win_streak = 0
        if flag:
            if self._forbidden_idle_spot != self.destination:
                self.run_speed = lerp(self.run_speed, 0.25, 0.5)
        else:
            self.run_speed = lerp(self.run_speed, 0.0, 0.5)
        self.focus_creature = None

    def _return_prey(self) -> None:
        """叼着猎物回「窝」：走到最近的屏幕边缘钻出去（shortcut），在屏幕外吃。
        走了 RETURN_PATIENCE 还没到、或哪边都走不到，就地吃，吃的时候护食。"""
        L = self.lizard
        T = L.terrain
        self.focus_creature = None
        if self.return_time == 0:
            self.exit_tile = self._nearest_exit()
            self.set_destination(self.exit_tile if self.exit_tile is not None else L.pos_tile)
        self.return_time += 1
        if self.eat_counter == 0 and self.exit_tile is not None and self.return_time <= RETURN_PATIENCE:
            side = shortcut.side_of(T, L.pos_tile)
            if side != 0 and T.accessible(L.pos_tile, L.lizard_params):
                shortcut.begin_enter(L, L.pos_tile, side)
                return
            self.run_speed = lerp(self.run_speed, math.sqrt(max(self.fear, 0.5)), 0.1)
            return
        if self.eat_ticks == 0:
            self.eat_ticks = L.rng.randrange(*EAT_TICKS)
        self.eat_counter += 1
        g = L.grasps[0]
        if g is not None:
            g.dominance = max(g.dominance, 2.0)  # 比任何 biteDominance * 随机 都大，抢不走
        self.run_speed = lerp(self.run_speed, 0.0, 0.5)
        if self.eat_counter >= self.eat_ticks:
            L.finish_eating()

    def _nearest_exit(self):
        L = self.lizard
        pf = self.path_finder
        best, best_d = None, _MAX
        for tile, _side in shortcut.exit_tiles(L.terrain, L.lizard_params):
            d = manhattan(L.pos_tile, tile)
            if d < best_d and pf.coordinate_reachable(tile):
                best, best_d = tile, d
        return best

    def reset_eating(self) -> None:
        self.eat_counter = 0
        self.eat_ticks = 0
        self.return_time = 0

    def _idle_spot_score(self, tile) -> float:
        L = self.lizard
        T = L.terrain
        if not T.accessible(tile, L.lizard_params):
            return _MAX
        if (
            not self.path_finder.coordinate_reachable_and_getbackable(tile)
            or tile == self._forbidden_idle_spot
        ):
            return _MAX
        num = 10.0
        narrow = T.narrow_space(tile)
        if narrow:
            num += 10.0
        key = L.lizard_params.key
        if key == "green":
            if T.acc(tile) == "Floor":
                num *= 0.5
            if narrow:
                num += 20.0
        elif key == "blue":
            num += min(max(10.0 - T.floor_altitude(tile), 0.0), 10.0)
            num += min(max(3.0 - T.terrain_proximity(tile), 0.0), 3.0)
            if T.acc(tile) in ("Climb", "Wall"):
                num *= 0.5
        elif key == "pink":
            num += T.floor_altitude(tile) * 2.0
            if narrow:
                num -= 15.0
        return num + CROWD_PENALTY * self._crowd(tile)

    def _crowd(self, tile) -> int:
        """闲待点附近 3 格内有几只别的蜥蜴（原版靠别的因素让它们散开，这里直接记一笔）。"""
        n = 0
        for o in getattr(self.lizard.ctx, "lizards", ()):
            if o is not self.lizard and manhattan(o.pos_tile, tile) <= 3:
                n += 1
        return n

    def _comfortable_idle_position(self) -> bool:
        L = self.lizard
        c0, c1, c2 = L.body_chunks
        if L.terrain.solid(tile_xy(c0.pos + dir_vec(c1.pos, c0.pos) * 30.0)):
            return False
        a, b = tile_xy(c0.pos), tile_xy(c2.pos)
        return a[1] == b[1] or (L.lizard_params.key == "blue" and a[0] == b[0])

    def do_i_want_to_hold_this_with_my_tongue(self, chunk) -> bool:
        """LizardAI.DoIWantToHoldThisWithMyTongue：舌头每 tick 问一次要不要继续拉着。"""
        if (
            chunk is None
            or getattr(chunk.owner, "gone", False)
            or (
                self.unpleasant_fall_risk(self.lizard.pos_tile)
                and self.unpleasant_fall_risk(tile_xy(chunk.pos))
            )
        ):
            return False
        if chunk.owner.is_creature:
            return self.dynamic_relationship(chunk.owner).go_for_kill
        return False

    def do_i_want_to_bite_this_creature(self, rep: CreatureRepresentation) -> bool:
        rng = self.lizard.rng
        if rng.random() < 0.1 and rng.random() > self.lizard.health:
            return True
        rel = self.dynamic_relationship(rep)
        if rel.go_for_kill:
            return True
        return rng.random() < 0.5 and rel.type == RIVAL
