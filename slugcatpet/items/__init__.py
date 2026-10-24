"""物品注册表：顺序决定侧边栏按钮、推进与同层绘制的先后；kinds() 只给当前 app 里有的。

每种物品用 ItemKind.apps 声明出现在哪些 app，placeable_apps 声明在哪些 app 的侧边栏可放置（None 为 apps 全部）。
蜥蜴只在切到蜥蜴 app 时才导入，蛞蝓猫的打包不带这部分代码。"""

from __future__ import annotations

from .base import ItemKind
from .batfly import KIND as BATFLY
from .bugegg import KIND as BUGEGG
from .eggbug import KIND as EGGBUG
from .fruit import KIND as FRUIT
from .lamp import KIND as LAMP
from .pearl import KIND as PEARL
from .pole import HPOLE, VPOLE
from .slimemold import KIND as SLIMEMOLD
from .spear import KIND as SPEAR
from .stone import KIND as STONE

# 新物品加在末尾，原有场景的推进和绘制顺序就不变
BUILTIN: tuple[ItemKind, ...] = (
    VPOLE,
    HPOLE,
    FRUIT,
    STONE,
    LAMP,
    SLIMEMOLD,
    BATFLY,
    SPEAR,
    EGGBUG,
    BUGEGG,
    PEARL,
)

_BY_KEY = {k.key: k for k in BUILTIN}
SLUGCAT, LIZARD = "slugcat", "lizard"
_app = SLUGCAT
_active: tuple[ItemKind, ...] | None = None
_lizard_loaded = False


def set_app(app: str) -> None:
    """切换当前 app；须在建 PetWindow 之前调用。"""
    global _app, _active, BUILTIN, _lizard_loaded
    if app == LIZARD and not _lizard_loaded:
        from .lizard import KINDS

        _lizard_loaded = True
        BUILTIN = (*BUILTIN, *KINDS)  # 排在末尾，共有物品的推进和绘制顺序不变
        _BY_KEY.update((k.key, k) for k in KINDS)
    _app, _active = app, None


def app() -> str:
    return _app


def kinds() -> tuple[ItemKind, ...]:
    global _active
    if _active is None:
        _active = tuple(k for k in BUILTIN if _app in k.apps)
    return _active


def get(key: str) -> ItemKind:
    k = _BY_KEY[key]
    if _app not in k.apps:
        raise KeyError(key)
    return k
