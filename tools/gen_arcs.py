"""按内置角色的身体数值离线算好规划用的弧，写进 slugcatpet/resources/arcs.json.gz。"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def render() -> bytes:
    from slugcatpet.characters import REGISTRY
    from slugcatpet.planning.jump_arc import bake

    data = bake(d.stats for d in REGISTRY.values())
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0)


def main(argv=None):
    from slugcatpet.planning.jump_arc import _BAKED as OUT

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # 输出被重定向时不随系统代码页
    blob = render()
    rel = OUT.relative_to(ROOT)
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != blob:
            print(f"{rel} 已过期：运行 python tools/gen_arcs.py 重新生成")
            return 1
        print(f"{rel} 是最新的")
        return 0
    OUT.write_bytes(blob)
    print(f"写入 {rel}（{len(blob) // 1024} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
