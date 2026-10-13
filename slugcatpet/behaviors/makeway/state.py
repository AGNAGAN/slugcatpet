"""内置行为状态：被挡让路。"""

from __future__ import annotations

from ... import tuning
from .blocking import blocks_path
from ...brain.skills.motor import WALL_MARGIN
from ...brain.state import T_ACTIVITY, State, LIGHT


class MakeWay(State):
    name = "MakeWay"
    tier = T_ACTIVITY
    energy = LIGHT

    def __init__(self, fsm):
        super().__init__(fsm)
        self._away = 0.0  # 跳起时横向让开方向
        self._face = 0  # 趴下时的朝向（顺对方前进方向）
        self._hop = False
        self._lie_min = 0

    def enter(self):
        fsm = self.fsm
        b = fsm.body
        b.stop_walk()
        cr = fsm.social.crowd(fsm.win)
        ob = getattr(cr.yield_to, "body", None)
        away = 0.0
        if ob is not None and ob.walk_target_x is not None:
            away = -1.0 if ob.walk_target_x >= ob.chunk1.x else 1.0
        self._away = away
        self._face = 0
        self._lie_min = 0
        b.prone_snap = 0
        if self._crowded() or self._near_edge():
            self._hop = True
        elif fsm.social.count() > tuning.MAKEWAY_CROWD_LIE_N:
            self._hop = fsm.rng.random() < tuning.MAKEWAY_CROWD_HOP_PROB
        else:
            self._hop = fsm.rng.random() >= 0.5
        if self._hop:
            b.set_posture(True)
            if away:
                evx = b.stats.makeway_evade_vx
                b.chunk0.vx += away * evx
                b.chunk1.vx += away * evx
            b.request_jump("stand", hold_ticks=b.stats.makeway_hop_hold)
        else:
            self._away = 0.0
            self._face = int(-away)
            self._lie_min = tuning.MAKEWAY_LIE_MIN_TICKS
            b.set_posture(False)
            b.hip_sink = 1.0
            b.crawl_pose = 1.0
            b.prone_snap = tuning.MAKEWAY_LIE_SNAP_TICKS
            b.crawl_anchor = b.chunk1.x
            if self._face:
                b.facing = self._face
        cr.shoved = 0
        cr.yield_cd = tuning.MAKEWAY_COOLDOWN
        if cr.yield_to is not None:
            fsm.social.note_yield(fsm.win, cr.yield_to)

    def tick(self, cursor, disturbed):
        fsm = self.fsm
        b = fsm.body
        ob = getattr(fsm.social.crowd(fsm.win).yield_to, "body", None)
        if ob is not None:
            fsm.gfx.look_at = (ob.chunk0.x, ob.chunk0.y)
        if self._away:
            b.move_dir = 1 if self._away > 0 else -1
            tgt = self._away * b.stats.makeway_evade_vx
            b.chunk0.vx += (tgt - b.chunk0.vx) * 0.3
            b.chunk1.vx += (tgt - b.chunk1.vx) * 0.3
        if not self._hop:
            b.move_dir = 0
            b.hip_sink = 1.0
            b.crawl_pose = min(1.0, b.crawl_pose + 0.3)
            if self._face:
                b.facing = self._face
        # 退出：让开了 / 超时 / 顶人者走了；趴下的至少趴稳再起
        if (
            fsm.timer >= tuning.MAKEWAY_TIMEOUT
            or ob is None
            or not blocks_path(b.chunk1.x, ob.chunk1.x, ob.walk_target_x, tuning.SHOVE_CONTACT_DIST)
        ):
            if fsm.timer < self._lie_min:
                return
            fsm._transition("IdleStand")

    def _crowded(self):
        b = self.fsm.body
        n = 0
        for o in self.fsm.social.others(self.fsm.win):
            ob = o.body
            if ob.on_floor() and abs(ob.chunk1.x - b.chunk1.x) <= tuning.MAKEWAY_CROWD_DIST:
                n += 1
        return n >= tuning.MAKEWAY_CROWD_N

    def _near_edge(self):
        fsm = self.fsm
        m = tuning.MAKEWAY_EDGE_MARGIN
        x = fsm.body.chunk1.x
        return x <= WALL_MARGIN + m or x >= fsm.WL - WALL_MARGIN - m
