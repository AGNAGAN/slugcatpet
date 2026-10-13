"""物品状态字符串常量。"""

from __future__ import annotations


class ItemState:
    FREE = "free"
    HANGING = "hanging"
    CARRIED = "carried"
    MOUSE = "mouse"
    STUCK = "stuck"  # 扎在墙里或身上
    EATEN = "eaten"
    GONE = "gone"
