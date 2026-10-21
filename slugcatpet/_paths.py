"""资源路径和可写数据路径，兼容开发环境与 PyInstaller 打包。"""

from __future__ import annotations
import os
import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return base_dir() / "slugcatpet" / "resources"
    return Path(__file__).resolve().parent / "resources"


def user_dir() -> Path:
    """~/.slugcatpet，可用 SLUGCATPET_HOME 覆盖；旧版 ~/.saintpet 首次自动迁移。"""
    env = os.environ.get("SLUGCATPET_HOME")
    d = Path(env) if env else Path.home() / ".slugcatpet"
    old = Path.home() / ".saintpet"
    if not env and not d.exists() and old.is_dir():
        try:
            old.rename(d)
        except Exception:
            pass
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def assets_dir() -> Path:
    return user_dir() / "assets"


def music_asset_dirs() -> list[Path]:
    return [assets_dir() / "music"]


def bundled_assets_dir() -> Path:
    return resource_dir() / "assets"


def user_music_dir() -> Path:
    d = user_dir() / "music"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def rainworld_music_dir() -> Path:
    """从游戏选择性导入的配乐放在单独子目录，方便整体管理。"""
    d = user_music_dir() / "Rain World"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d
