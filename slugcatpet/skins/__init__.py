"""皮肤注册中心。"""

from __future__ import annotations

from pathlib import Path

from ..i18n import t
from . import sources
from .loader import SkinPack, load_pack
from . import groups as G
from .resolver import HIDDEN, SkinAtlasSet

# Dress My Slugcat 自带的绘制底稿 id
_DMS_TEMPLATES = frozenset({"dressmyslugcat.template", "dressmyslugcat.asymmetrytemplate"})

_state = {
    "loaded": False,
    "scan_external": True,
    "packs": {},  # id → SkinPack（可用）
    "failed": [],  # SkinPack（error 非空）或重复 id
    "zip_errors": [],  # (zip 解压目录, 错误)
    "signature": None,
}


def configure(scan_external: bool) -> None:
    _state["scan_external"] = bool(scan_external)


def scan_external() -> bool:
    return _state["scan_external"]


def _ensure():
    if not _state["loaded"]:
        reload()


def _watched_roots() -> list[Path]:
    roots = [sources.skins_dir()]
    if _state["scan_external"]:
        roots += sources.game_mod_roots() + sources.workshop_roots()
    return roots


def refresh_if_changed() -> bool:
    if _state["loaded"] and sources.signature(_watched_roots()) == _state["signature"]:
        return False
    reload()
    return True


def reload() -> None:
    """重扫全部来源；优先级：本地 > 游戏 mods > 创意工坊（同 id 先到先得）。"""
    roots: list[tuple[Path, str]] = [(sources.skins_dir(), "local")]
    zips = sources.unpack_zips()
    _state["zip_errors"] = [(d, e) for d, e in zips if e]
    zip_roots = {d for d, e in zips if not e}
    roots += [(d, "local") for d in sorted(zip_roots)]
    if _state["scan_external"]:
        roots += [(r, "game") for r in sources.game_mod_roots()]
        roots += [(r, "workshop") for r in sources.workshop_roots()]

    packs: dict[str, SkinPack] = {}
    failed: list[SkinPack] = []
    for root, src in roots:
        for d in sources.pack_dirs(root):
            pack = load_pack(d, src)
            pack.collection = (
                root.name.rsplit("-", 1)[0] if root in zip_roots else sources.collection_of(d, root, src)
            )
            if not pack.ok:
                failed.append(pack)
            elif pack.id in packs:
                if packs[pack.id].source != src:
                    continue
                pack.error = t("skin_err_dup_id", id=pack.id, other=packs[pack.id].path)
                failed.append(pack)
            else:
                packs[pack.id] = pack
    _state["packs"] = packs
    _state["failed"] = failed
    _state["loaded"] = True
    from .folder import write_report

    write_report()
    _state["signature"] = sources.signature(_watched_roots())


def _is_dms_template(p: SkinPack) -> bool:
    """Dress My Slugcat 自带的绘制底稿，不当作可选皮肤。"""
    return p.id.lower() in _DMS_TEMPLATES


def packs() -> list[SkinPack]:
    _ensure()
    return sorted(
        (p for p in _state["packs"].values() if not _is_dms_template(p)),
        key=lambda p: (p.source != "local", p.name.lower()),
    )


def get(skin_id: str | None) -> SkinPack | None:
    if not skin_id:
        return None
    _ensure()
    return _state["packs"].get(skin_id)


def problems() -> list[str]:
    _ensure()
    out = []
    for p in _state["failed"]:
        out.append(f"{p.path}: {p.error}")
    for d, e in _state["zip_errors"]:
        out.append(t("skin_zip_fail", name=d.name, e=e))
    for p in packs():
        for grp, miss in sorted(p.missing.items()):
            out.append(
                f"{p.name} ({p.path}): " + t("skin_missing_group", group=grp, n=len(miss), first=miss[0])
            )
        for w in p.warnings:
            out.append(f"{p.name} ({p.path}): {w}")
    return out


def failed() -> list[SkinPack]:
    _ensure()
    return list(_state["failed"])


def zip_errors() -> list:
    _ensure()
    return list(_state["zip_errors"])


def resolver_for(base_atlas, look, species: str) -> SkinAtlasSet:
    """该猫的查找链：每个部位按 look 取来源皮肤，找不到的按原皮；颜色和尾巴形状随部位来源。"""
    from ..appearance import EMPTY

    whole = get(look.skin)
    colors = dict(whole.colors) if whole is not None else {}
    tail = dict(whole.tail) if whole is not None else {}
    sources = {}
    for grp in G.GROUPS:
        sid = look.source(grp)
        if sid == EMPTY:
            sources[grp] = HIDDEN
            colors.pop(grp, None)
            continue
        pack = get(sid)
        sources[grp] = pack
        if grp in look.parts:
            colors.pop(grp, None)
            if pack is not None and grp in pack.colors:
                colors[grp] = pack.colors[grp]
            if grp == "TAIL":
                tail = dict(pack.tail) if pack is not None else {}
    if look.tail:
        tail.update(look.tail)
    return SkinAtlasSet(base_atlas, sources, species, colors, tail)


def skins_dir() -> Path:
    return sources.skins_dir()
