"""挡路几何纯函数：判断 blocker 是否挡在 walker 去路上。"""
from __future__ import annotations

from ...core.creature import WALK_STOP_EPS


def _sign(v: float) -> float:
    return 1.0 if v > 0.0 else (-1.0 if v < 0.0 else 0.0)


def blocks_path(blocker_x, walker_x, walker_target_x, contact_dist) -> bool:
    """blocker 是否正挡在 walker 前进方向上且已接触。"""
    if walker_target_x is None:
        return False
    d = walker_target_x - walker_x
    if abs(d) <= WALK_STOP_EPS:
        return False
    rel = (blocker_x - walker_x) * _sign(d)
    return 0.0 < rel <= contact_dist

