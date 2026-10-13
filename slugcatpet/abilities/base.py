"""能力（Ability）基类与参数表。"""

from __future__ import annotations

from types import SimpleNamespace


class Param:
    __slots__ = ("default", "lo", "hi", "doc")

    def __init__(self, default, lo=None, hi=None, doc=""):
        self.default = default
        self.lo = lo
        self.hi = hi
        self.doc = doc


def resolve_params(spec: dict, overrides: dict | None, where: str) -> SimpleNamespace:
    """参数表 + 覆盖值 → 命名空间；非法即报错。"""
    vals = {k: p.default for k, p in spec.items()}
    for k, v in (overrides or {}).items():
        p = spec.get(k)
        if p is None:
            raise ValueError(f"{where}: 未知参数 {k!r}（可用：{', '.join(spec) or '无'}）")
        if isinstance(p.default, bool):
            ok = isinstance(v, bool)
        elif isinstance(p.default, int):
            ok = isinstance(v, int) and not isinstance(v, bool)
        elif isinstance(p.default, float):
            ok = isinstance(v, (int, float)) and not isinstance(v, bool)
            v = float(v) if ok else v
        else:
            ok = True
        if not ok:
            raise ValueError(f"{where}: 参数 {k!r} 类型应同默认值 {p.default!r}，得到 {v!r}")
        if (p.lo is not None and v < p.lo) or (p.hi is not None and v > p.hi):
            raise ValueError(f"{where}: 参数 {k!r}={v!r} 超出范围 [{p.lo}, {p.hi}]")
        vals[k] = v
    return SimpleNamespace(**vals)


class Ability:
    key = ""
    title = {"zh": "", "en": ""}
    doc = ""
    requires = ()
    params: dict = {}

    def __init__(self, p: SimpleNamespace):
        self.p = p

    def attach_body(self, pet, body):
        """身体刚建好：写入物理特性（如 body.aquatic）。"""

    def build(self, pet):
        return None

    def draw_layers(self, pet):
        """[(槽位, fn(gfx, painter, atlas, ts))]；槽位见 SlugcatGraphics.LAYER_SLOTS。"""
        return ()

    def pre_step(self, pet):
        """行为决策之后、身体物理步之前。"""

    def post_step(self, pet):
        """身体物理步与图形姿态更新之后、尾巴之前。"""

    def resize(self, pet, floor_y):
        """换屏 / 改分辨率。"""

    def reaches(self, pet):
        return ()

    def fetch_assist(self, pet):
        """取果时的空中补救器（update / abort / reset / holding），无则 None。"""
        return None

    def mount(self, fsm):
        """行为状态机建好后、行为模块挂载前调用：挂 ticker、致死钩子等。"""

    def control(self, pet, body):
        """进入手动控制时挂本能力的操控器。"""
