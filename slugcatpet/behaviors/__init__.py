"""行为注册表。"""

from __future__ import annotations

from ..abilities import body_tags
from ..abilities.base import resolve_params
from .anger import Anger, ArmStoneBehavior
from .ascend import Ascend
from .base import Behavior, mood_candidate, mood_params, needed_tags
from .catch_breath import CatchBreathBehavior
from .cursor_lick import CursorLick
from .dodge_kill import DodgeKill
from .fetch import Fetch, ForageBehavior
from .idle import Idle
from .makeway import MakeWayBehavior
from .poles import Poles
from .pyro_maul import PyroMaul
from .pyro_romp import PyroRomp
from .rest import Rest
from .riv_flip import RivFlip
from .riv_snatch import RivSnatch
from .seek_hpole import SeekHPoleBehavior
from .swim import Swim
from .wall_climb import WallClimb
from .warmth import Warmth
from .zerog_lick import ZeroGLick

# 顺序即挂载顺序（影响心情抽签、规则与砸晕收尾的先后）；新模块加在末尾
BUILTIN = (
    Fetch,
    Anger,
    Poles,
    Idle,
    Warmth,
    Rest,
    Swim,
    MakeWayBehavior,
    SeekHPoleBehavior,
    WallClimb,
    CursorLick,
    Ascend,
    DodgeKill,
    RivFlip,
    RivSnatch,
    PyroRomp,
    PyroMaul,
    ForageBehavior,
    ArmStoneBehavior,
    CatchBreathBehavior,
    ZeroGLick,
)

REGISTRY: dict[str, type[Behavior]] = {cls.key: cls for cls in BUILTIN}


def validate(behaviors: dict, abilities: dict, where: str) -> None:
    tags = body_tags(abilities)
    for key, over in behaviors.items():
        cls = REGISTRY.get(key)
        if cls is None:
            raise ValueError(f"{where}: 未知行为 {key!r}（可用：{', '.join(REGISTRY)}）")
        if over is False:
            if cls.essential:
                raise ValueError(f"{where}: 行为 {key!r} 不能关闭")
            continue
        missing = [r for r in needed_tags(cls) if r not in tags]
        if missing:
            raise ValueError(f"{where}: 行为 {key!r} 需要 {', '.join(missing)}")
        resolve_params(cls.params, over if isinstance(over, dict) else None, f"{where} 行为 {key}")


def enabled(cat) -> list[type[Behavior]]:
    over = cat.behaviors
    tags = body_tags(cat.abilities)
    return [
        cls
        for cls in BUILTIN
        if (cls.essential or over.get(cls.key, True) is not False)
        and all(r in tags for r in needed_tags(cls))
    ]


def mount_all(fsm) -> None:
    cat = fsm.win.cat
    validate(cat.behaviors, cat.abilities, f"角色 {cat.key!r}")
    for cls in enabled(cat):
        over = cat.behaviors.get(cls.key)
        p = resolve_params(cls.params, over if isinstance(over, dict) else None, f"{cat.key} 行为 {cls.key}")
        cls(p).mount(fsm)


__all__ = ["Behavior", "REGISTRY", "enabled", "mount_all", "mood_candidate", "mood_params", "validate"]
