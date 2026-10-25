"""喵声素材：从玩家本机的 Push to Meow（创意工坊订阅或本地 mods 目录）复制到 assets/meow。

那些录音是 GPL 授权，不随本程序分发。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .._paths import assets_dir
from ..gameassets import _STREAMING, _steam_libraries, detect_install
from .voice import CLIPS

WORKSHOP_ID = "3257541402"
MOD_ID = "pushtomeow"
_APP_ID = "312520"


def meow_sounds_dir() -> Path:
    return assets_dir() / "meow"


def meow_sounds_missing() -> list[str]:
    d = meow_sounds_dir()
    return [n for n in CLIPS if not (d / f"{n}.wav").is_file()]


def _sources():
    install = detect_install()
    if install is not None:
        yield install / _STREAMING / "mods" / MOD_ID / "soundeffects"
    for lib in _steam_libraries():
        yield lib / "steamapps" / "workshop" / "content" / _APP_ID / WORKSHOP_ID / "soundeffects"


def import_meow_sounds() -> bool:
    """补齐缺的片段，返回是否齐了。找不到 Push to Meow 时什么都不做。"""
    todo = meow_sounds_missing()
    if not todo:
        return True
    src = next((s for s in _sources() if all((s / f"{n}.wav").is_file() for n in todo)), None)
    if src is None:
        return False
    d = meow_sounds_dir()
    d.mkdir(parents=True, exist_ok=True)
    for n in todo:
        tmp = d / f"{n}.wav.part"
        shutil.copyfile(src / f"{n}.wav", tmp)
        tmp.replace(d / f"{n}.wav")
    return True
