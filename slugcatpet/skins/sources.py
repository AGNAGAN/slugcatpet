"""皮肤来源发现（用户目录 / 游戏 mods / 创意工坊）与 zip 解压。"""

from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from pathlib import Path

from .._paths import user_dir
from .loader import META_FILE

RW_APP_ID = "312520"
DMS_DIR = "dressmyslugcat"
_ZIP_EXTS = {".png", ".txt", ".json"}
MAX_ZIP_ENTRIES = 2000
MAX_ZIP_UNPACKED = 64 * 1024 * 1024


def skins_dir() -> Path:
    d = user_dir() / "skins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _skipped(rel_parts) -> bool:
    return any(p.startswith("_") for p in rel_parts)


def _zip_cache_dir() -> Path:
    return user_dir() / "cache" / "skin_zips"


def pack_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    try:
        for meta in root.rglob(META_FILE):
            if meta.is_file() and meta.parent != root and not _skipped(meta.parent.relative_to(root).parts):
                out.append(meta.parent)
    except OSError:
        pass
    return sorted(out)


def collection_of(pack_dir: Path, root: Path, source: str) -> str:
    if source in ("game", "workshop"):
        mod = root.parent
        try:
            from ..rendering.atlas import load_json_lenient

            name = load_json_lenient(mod / "modinfo.json").get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        except Exception:
            pass
        return mod.name
    rel = pack_dir.relative_to(root).parts
    return rel[0] if len(rel) > 1 else ""


_SIG_EXTS = (".json", ".zip", ".png", ".txt")


def signature(roots) -> tuple:
    sig = []
    stack = [str(r) for r in roots]
    while stack:
        try:
            it = os.scandir(stack.pop())
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.name.lower().endswith(_SIG_EXTS):
                        st = e.stat(follow_symlinks=False)
                        sig.append((e.path, st.st_mtime_ns, st.st_size))
                except OSError:
                    pass
    return tuple(sorted(sig))


def game_mod_roots() -> list[Path]:
    """<游戏>/RainWorld_Data/StreamingAssets/mods/*/dressmyslugcat。"""
    from ..gameassets import detect_install

    game = detect_install()
    if game is None:
        return []
    mods = game / "RainWorld_Data" / "StreamingAssets" / "mods"
    return _dms_roots_under(mods)


def workshop_roots() -> list[Path]:
    """<Steam 库>/steamapps/workshop/content/312520/*/dressmyslugcat。"""
    from ..gameassets import _steam_libraries

    out = []
    for lib in _steam_libraries():
        out += _dms_roots_under(lib / "steamapps" / "workshop" / "content" / RW_APP_ID)
    return out


def _dms_roots_under(parent: Path) -> list[Path]:
    if not parent.is_dir():
        return []
    out = []
    try:
        for mod in sorted(parent.iterdir()):
            d = mod / DMS_DIR
            if d.is_dir():
                out.append(d)
    except OSError:
        pass
    return out


def unpack_zips() -> list[tuple[Path, str]]:
    cache = _zip_cache_dir()
    results = []
    for z in sorted(skins_dir().glob("*.zip")):
        h = hashlib.sha1(f"{z.name}:{z.stat().st_size}:{z.stat().st_mtime_ns}".encode()).hexdigest()[:12]
        dest = cache / f"{z.stem}-{h}"
        if dest.is_dir():
            results.append((dest, ""))
            continue
        err = safe_extract(z, dest)
        results.append((dest, err))
    keep = {r[0].name for r in results}
    if cache.is_dir():
        for old in cache.iterdir():
            if old.is_dir() and old.name not in keep:
                shutil.rmtree(old, ignore_errors=True)
    return results


def safe_extract(zpath: Path, dest: Path) -> str:
    """只解 png/txt/json，防路径穿越与解压炸弹；失败返回错误串并清理。"""
    try:
        with zipfile.ZipFile(zpath) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if len(infos) > MAX_ZIP_ENTRIES:
                return f"too many entries ({len(infos)})"
            if sum(i.file_size for i in infos) > MAX_ZIP_UNPACKED:
                return "unpacked size too large"
            dest.mkdir(parents=True, exist_ok=True)
            root = dest.resolve()
            for i in infos:
                name = i.filename.replace("\\", "/")
                if Path(name).suffix.lower() not in _ZIP_EXTS:
                    continue
                target = (dest / name).resolve()
                if root not in target.parents:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(i) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        return ""
    except (zipfile.BadZipFile, OSError) as e:
        shutil.rmtree(dest, ignore_errors=True)
        return str(e)
