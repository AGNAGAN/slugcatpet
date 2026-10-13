"""从能力 / 行为模块的 params 表生成 ai-docs/PARAMS.md。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ai-docs" / "PARAMS.md"
sys.path.insert(0, str(ROOT))


def _fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _range(p):
    if isinstance(p.default, bool) or (p.lo is None and p.hi is None):
        return ""
    return f"{_fmt(p.lo) if p.lo is not None else '−∞'} ~ {_fmt(p.hi) if p.hi is not None else '∞'}"


def _table(params):
    if not params:
        return "无可调参数。\n"
    rows = ["| 参数 | 默认 | 范围 | 说明 |", "|---|---|---|---|"]
    for name, p in params.items():
        rows.append(f"| `{name}` | {_fmt(p.default)} | {_range(p)} | {p.doc} |")
    return "\n".join(rows) + "\n"


def render() -> str:
    from slugcatpet.abilities import BUILTIN as ABILITIES
    from slugcatpet.behaviors import BUILTIN as BEHAVIORS
    from slugcatpet.characters import REGISTRY

    users = {cls.key: [k for k, d in REGISTRY.items() if cls.key in d.abilities] for cls in ABILITIES}
    out = [
        "# 能力与行为参数",
        "",
        "> 本文件由 `python tools/params_doc.py` 从代码生成，请勿手改。",
        "> 角色怎么写见 [CHARACTERS.md](CHARACTERS.md)，整体结构见 [ARCHITECTURE.md](ARCHITECTURE.md)。",
        "",
        "角色定义（`slugcatpet/resources/characters/<key>.json`）里这样覆盖参数：",
        "",
        "```json",
        '"abilities": {"tongue": {"ceiling_drop": false}, "ascension": {}},',
        '"behaviors": {"cursor_lick": {"dwell_ticks": 120}, "dodge_kill": false}',
        "```",
        "",
        "- `abilities`：这只猫有哪些能力（键）以及参数覆盖（值，`{}` = 全用默认）。",
        "- `behaviors`：行为按能力自动挂载，这里只写例外：`false` 关掉，对象 = 覆盖参数。",
        "- 带心情候选的行为，权重还会乘以性格权重（好动度 × `toy_pref[心情名]`）。",
        "",
        "## 性格",
        "",
        "角色 JSON 的 `personality` 各轴作用如下，换算都在 `characters/personality.py` 的 `Traits` 里。",
        "",
        "| 轴 | 作用 |",
        "|---|---|",
    ]
    from slugcatpet.characters.personality import EFFECTS

    out += [f"| `{k}` | {v} |" for k, v in EFFECTS]
    out += ["", "## 能力", ""]
    for cls in ABILITIES:
        dep = [b.key for b in BEHAVIORS if cls.key in b.requires]
        out += [f"### {cls.title['zh']} `{cls.key}`", "", cls.doc, ""]
        meta = []
        if cls.requires:
            meta.append("依赖能力：" + "、".join(f"`{r}`" for r in cls.requires))
        meta.append("内置角色：" + ("、".join(f"`{u}`" for u in users[cls.key]) or "无"))
        if dep:
            meta.append("随之挂载的行为：" + "、".join(f"`{d}`" for d in dep))
        out += ["- " + m for m in meta] + ["", _table(cls.params)]
    out += ["## 行为", ""]
    for cls in BEHAVIORS:
        out += [f"### {cls.title['zh']} `{cls.key}`", "", cls.doc, ""]
        from slugcatpet.items.base import USES

        abil = [r for r in cls.requires if r not in USES]
        uses = [r for r in cls.requires if r in USES]
        meta = ["需要能力：" + ("、".join(f"`{r}`" for r in abil) or "无（所有猫）")]
        if uses:
            meta.append("用到的物品：" + "、".join(f"`{r}`" for r in uses))
        if cls.mood:
            meta.append(f"心情名（toy_pref 键）：`{cls.mood}`")
        out += ["- " + m for m in meta] + ["", _table(cls.params)]
    return "\n".join(out).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != text:
            print("ai-docs/PARAMS.md 已过期：运行 python tools/params_doc.py 重新生成")
            return 1
        print("ai-docs/PARAMS.md 是最新的")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"写入 {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
