"""从用户本机 Rain World 安装提取图集和场景曲到 ~/.slugcatpet/assets。"""

from __future__ import annotations
import re
import sys
from pathlib import Path

from ._paths import assets_dir, bundled_assets_dir, music_asset_dirs, user_dir
from .i18n import t

# 图集名：base + MSC 各含贴图与 UI
ATLASES = ("rainWorld", "rainworldmsc", "uiSprites", "uispritesmsc")
RAIN_ATLAS = "waterSprites"  # 雨的水花，可缺
_ATLAS_REL = Path("RainWorld_Data") / "resources.assets"


class SetupError(RuntimeError):
    """导入失败，message 面向用户、可照做。"""


def atlases_present(d: Path) -> bool:
    return all(
        (d / f).exists()
        for f in (
            "rainWorld",
            "rainWorld.png",
            "rainworldmsc",
            "rainworldmsc.png",
            "uiSprites",
            "uiSprites.png",
            "uispritesmsc",
            "uispritesmsc.png",
        )
    )


def _drive_roots() -> list[Path]:
    if sys.platform == "win32":
        return [Path(f"{c}:\\") for c in "CDEFGHIJKLMNOP" if Path(f"{c}:\\").exists()]
    home = Path.home()
    return [home / "Library/Application Support/Steam", home / ".steam/steam", home / ".local/share/Steam"]


def _steam_root() -> Path | None:
    if sys.platform == "win32":
        try:
            import winreg

            for hive, key, val in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        p = Path(winreg.QueryValueEx(k, val)[0])
                        if p.exists():
                            return p
                except OSError:
                    pass
        except Exception:
            pass
    return None


def _steam_libraries() -> list[Path]:
    roots: list[Path] = []
    sr = _steam_root()
    if sr:
        roots.append(sr)
    for d in _drive_roots():
        roots += [d / "Program Files (x86)" / "Steam", d / "Steam", d / "SteamLibrary", d]
    libs: list[Path] = []
    seen: set[Path] = set()
    for r in roots:
        if r in seen or not r.exists():
            continue
        seen.add(r)
        libs.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            txt = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s*"([^"]+)"', txt):
                p = Path(m.group(1).replace("\\\\", "\\"))
                if p not in seen and p.exists():
                    seen.add(p)
                    libs.append(p)
    return libs


INSTALL_FILE = "game_path.txt"  # 导入图集时记下游戏目录，手动选的也能再找到


def _saved_install() -> Path | None:
    for d in {assets_dir(), user_dir() / "assets"}:
        try:
            game = Path((d / INSTALL_FILE).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if (game / _ATLAS_REL).exists():
            return game
    return None


def detect_install() -> Path | None:
    saved = _saved_install()
    if saved is not None:
        return saved
    for lib in _steam_libraries():
        game = lib / "steamapps" / "common" / "Rain World"
        if (game / _ATLAS_REL).exists():
            return game
    return None


def remember_install(install: Path) -> None:
    """记住用户手动选择的游戏目录，下次导入配乐时直接复用。"""
    install = Path(install)
    try:
        assets_dir().mkdir(parents=True, exist_ok=True)
        (assets_dir() / INSTALL_FILE).write_text(str(install.resolve()), encoding="utf-8")
    except OSError:
        pass


def extract_atlases(install: Path, dest: Path | None = None) -> Path:
    install = Path(install)
    res = install / _ATLAS_REL
    if not res.exists():
        raise SetupError(t("err_atlas_missing", res=res))
    try:
        import UnityPy
    except ImportError as e:
        raise SetupError(t("err_no_unitypy")) from e

    dest = Path(dest or assets_dir())
    got = _extract_named(UnityPy, res, (*ATLASES, RAIN_ATLAS), dest)

    if got.get("rainWorld") != {"png", "map"}:
        raise SetupError(t("err_base_fail"))
    if got.get("rainworldmsc") != {"png", "map"}:
        raise SetupError(t("err_msc_missing"))
    if got.get("uiSprites") != {"png", "map"}:
        raise SetupError(t("err_ui_fail"))
    if got.get("uispritesmsc") != {"png", "map"}:
        raise SetupError(t("err_uimsc_missing"))
    try:
        (dest / INSTALL_FILE).write_text(str(install.resolve()), encoding="utf-8")
    except OSError:
        pass
    return dest


def _extract_named(UnityPy, res: Path, names, dest: Path) -> dict[str, set[str]]:
    """从资源文件取出这些图集的贴图与帧表，返回 {名: {"png", "map"}}。"""
    dest.mkdir(parents=True, exist_ok=True)
    want = set(names)
    got: dict[str, set[str]] = {}
    for obj in UnityPy.load(str(res)).objects:
        if obj.type.name not in ("Texture2D", "TextAsset"):
            continue
        d = obj.read()
        name = getattr(d, "m_Name", None) or getattr(d, "name", None)
        if name not in want:
            continue
        if obj.type.name == "Texture2D":
            d.image.save(str(dest / f"{name}.png"))
            got.setdefault(name, set()).add("png")
        else:
            raw = d.m_Script if hasattr(d, "m_Script") else d.script
            if isinstance(raw, str):
                raw = raw.encode("utf-8", "surrogateescape")
            (dest / name).write_bytes(raw)
            got.setdefault(name, set()).add("map")
    return got


RAIN_SOUNDS = (
    "shortLightRainLoop",
    "rainHeavy1",
    "rainLightUnderground1",
    "rainMedUnderground1",
    "shortDeathRainLoop",
    "RWTW_RainRumble_LOOP",
    "click1A",
)
_SFX_BUNDLES = ("loadedsoundeffects",)


def rain_sounds_dir() -> Path:
    return assets_dir() / "rain"


def rain_sounds_missing() -> list[str]:
    return [n for n in RAIN_SOUNDS if not (rain_sounds_dir() / f"{n}.wav").is_file()]


def extract_rain_sounds(install: Path) -> list[str]:
    """雨声循环从音效资源包取出、封装成 wav；返回这次写出的片名。"""
    from .audio.fsbogg import fsb_to_wav

    todo = rain_sounds_missing()
    if not todo:
        return []
    out = rain_sounds_dir()
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for name, fsb in _bundle_clips(Path(install), todo, _SFX_BUNDLES).items():
        try:
            data = fsb_to_wav(fsb)
        except ValueError:
            continue
        tmp = out / f"{name}.wav.part"
        tmp.write_bytes(data)
        tmp.replace(out / f"{name}.wav")
        done.append(name)
    return done


DIAL_SOUNDS = (
    "karmaFuzz",
    "karmaWheelC_1",
    "karmaWheelC_2",
    "karmaWheelC_3",
    "karmaWheelC_4",
    "karmaWheelLow",
    "capBell2",
    "karmaRiseA",
    "UIWoodHit",
    "tick",
    "tock",
)


def dial_sounds_dir() -> Path:
    return assets_dir() / "karma"


def dial_sounds_missing() -> list[str]:
    return [n for n in DIAL_SOUNDS if not (dial_sounds_dir() / f"{n}.wav").is_file()]


def extract_dial_sounds(install: Path) -> list[str]:
    """表盘的音效从音效资源包取出、封装成 wav；返回这次写出的片名。"""
    from .audio.fsbogg import fsb_to_wav

    todo = dial_sounds_missing()
    if not todo:
        return []
    out = dial_sounds_dir()
    out.mkdir(parents=True, exist_ok=True)
    done = []
    for name, fsb in _bundle_clips(Path(install), todo, _SFX_BUNDLES).items():
        try:
            data = fsb_to_wav(fsb)
        except ValueError:
            continue
        tmp = out / f"{name}.wav.part"
        tmp.write_bytes(data)
        tmp.replace(out / f"{name}.wav")
        done.append(name)
    return done


def rain_atlas_missing() -> bool:
    return not any(
        (d / RAIN_ATLAS).is_file() and (d / f"{RAIN_ATLAS}.png").is_file()
        for d in (assets_dir(), bundled_assets_dir())
    )


def extract_rain_atlas(install: Path) -> bool:
    """提取水花图集。"""
    import UnityPy

    res = Path(install) / _ATLAS_REL
    if not res.is_file():
        return False
    return _extract_named(UnityPy, res, (RAIN_ATLAS,), assets_dir()).get(RAIN_ATLAS) == {"png", "map"}


_STREAMING = Path("RainWorld_Data") / "StreamingAssets"
_AUDIO_BUNDLES = ("music_songs",)
_LOOSE_AUDIO = (("music/songs", ".mp3"),)


def _bundle_clips(install: Path, names, bundles=_AUDIO_BUNDLES) -> dict[str, bytes]:
    import UnityPy
    from UnityPy.helpers.ResourceReader import get_resource_data

    want, got = set(names), {}
    for bundle in bundles:
        path = install / _STREAMING / "AssetBundles" / bundle
        if not path.is_file() or not want - got.keys():
            continue
        for obj in UnityPy.load(str(path)).objects:
            if obj.type.name != "AudioClip":
                continue
            d = obj.read()
            if d.m_Name in want:
                r = d.m_Resource
                got[d.m_Name] = bytes(get_resource_data(r.m_Source, d.assets_file, r.m_Offset, r.m_Size))
    return got


def read_bundle_clip(install: Path, name: str) -> bytes:
    return _bundle_clips(Path(install), [name])[name]


_GAME_MUSIC_EXTS = (".mp3", ".ogg", ".wav")


def is_game_install(path: Path) -> bool:
    """目录看起来是 Rain World 根目录（有图集或有配乐资源）。"""
    path = Path(path)
    return (
        (path / _ATLAS_REL).is_file()
        or (path / _STREAMING / "music" / "songs").is_dir()
        or (path / _STREAMING / "AssetBundles" / _AUDIO_BUNDLES[0]).is_file()
    )


def _bundle_decoded(install: Path, names) -> dict[str, tuple[str, bytes]]:
    """少数配乐使用未知 Vorbis setup 时，退回 UnityPy 解码成 wav。"""
    import UnityPy

    want = set(names)
    if not want:
        return {}
    path = Path(install) / _STREAMING / "AssetBundles" / _AUDIO_BUNDLES[0]
    if not path.is_file():
        return {}
    got: dict[str, tuple[str, bytes]] = {}
    for obj in UnityPy.load(str(path)).objects:
        if obj.type.name != "AudioClip":
            continue
        try:
            d = obj.read()
            if d.m_Name not in want:
                continue
            samples = d.samples
        except Exception:
            continue
        for filename, data in samples.items():
            ext = Path(filename).suffix.lower()
            if ext in _GAME_MUSIC_EXTS and data:
                got[d.m_Name] = (ext, data)
                break
    return got


def _bundle_clip_names(install: Path) -> set[str]:
    """只读取资源包里的 AudioClip 名称，供选择窗口列出全部配乐。"""
    import UnityPy

    path = Path(install) / _STREAMING / "AssetBundles" / _AUDIO_BUNDLES[0]
    if not path.is_file():
        return set()
    names: set[str] = set()
    for obj in UnityPy.load(str(path)).objects:
        if obj.type.name != "AudioClip":
            continue
        try:
            name = obj.read().m_Name
        except Exception:
            continue
        if name:
            names.add(name)
    return names


def _music_sort_key(name: str):
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold()) for part in re.split(r"(\d+)", name)
    )


def game_music_names(install: Path) -> list[str]:
    """列出游戏目录里全部配乐名；散文件可能是空占位，资源包里的同名曲仍可用。"""
    install = Path(install)
    bundle_names: set[str] = set()
    try:
        bundle_names = _bundle_clip_names(install)
    except Exception:
        pass
    names = set(bundle_names)
    songs = install / _STREAMING / "music" / "songs"
    try:
        for f in songs.iterdir():
            if not f.is_file() or f.suffix.lower() not in _GAME_MUSIC_EXTS:
                continue
            try:
                usable = f.stat().st_size > 0 or not bundle_names or f.stem in bundle_names
            except OSError:
                continue
            if usable:
                names.add(f.stem)
    except OSError:
        pass
    return sorted(names, key=_music_sort_key)


def game_music_imported(name: str, out_dir: Path) -> bool:
    out = Path(out_dir)
    for ext in _GAME_MUSIC_EXTS:
        f = out / (name + ext)
        try:
            if f.is_file() and f.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


_MUSIC_MARK = ".format"  # 记录提取时的 ogg 格式版本，对不上就重新提取


def _ogg_format() -> int:
    from .audio.fsbogg import FORMAT

    return FORMAT


def _music_current(d: Path) -> bool:
    try:
        return (d / _MUSIC_MARK).read_text(encoding="ascii").strip() == str(_ogg_format())
    except OSError:
        return False


def music_missing(names, dirs=None) -> list[str]:
    dirs = [d for d in (music_asset_dirs() if dirs is None else dirs) if _music_current(d)]
    return [n for n in names if not any((d / (n + ext)).is_file() for d in dirs for ext in (".ogg", ".mp3"))]


def prune_music(keep) -> None:
    d = music_asset_dirs()[0]
    try:
        files = list(d.iterdir())
    except OSError:
        return
    for f in files:
        if f.suffix == ".part" or (f.suffix in (".ogg", ".mp3") and f.stem not in keep):
            try:
                f.unlink()
            except OSError:
                pass


def extract_music(
    install: Path,
    names,
    dest: Path | None = None,
    *,
    out_dir: Path | None = None,
    progress=None,
) -> list[str]:
    """游戏里有完整散文件就直接复制，否则从资源包重新封装成 ogg；已有的跳过，单首失败不影响别的，返回这次写出的曲名。

    dest 是旧接口（会再加一层 music/）；out_dir 用于把选中的配乐直接导入个人音乐目录。
    progress(done, total, name) 会在处理每一首后回调。
    """
    from .audio.fsbogg import fsb_to_ogg

    install = Path(install)
    if out_dir is not None:
        if dest is not None:
            raise ValueError("dest and out_dir are mutually exclusive")
        out = Path(out_dir)
        todo = [n for n in names if not game_music_imported(n, out)]
    else:
        out = Path(dest) / "music" if dest is not None else music_asset_dirs()[0]
        todo = music_missing(names, [out] if dest is not None else None)
    if not todo:
        return []
    out.mkdir(parents=True, exist_ok=True)
    blobs: dict[str, tuple[str, bytes]] = {}
    for name in todo:
        for sub, ext in _LOOSE_AUDIO:
            f = install / _STREAMING / sub / (name + ext)
            try:
                if f.is_file() and f.stat().st_size > 0:
                    blobs[name] = (ext, f.read_bytes())
                    break
            except OSError:
                pass
    rest = [n for n in todo if n not in blobs]
    if rest:
        try:
            clips = _bundle_clips(install, rest)
        except Exception:
            clips = {}
        for name, fsb in clips.items():
            try:
                blobs[name] = (".ogg", fsb_to_ogg(fsb))
            except Exception:
                pass
        fallback = [n for n in rest if n not in blobs]
        if fallback:
            try:
                blobs.update(_bundle_decoded(install, fallback))
            except Exception:
                pass
    written: list[str] = []
    total = len(todo)
    for done, name in enumerate(todo, 1):
        item = blobs.get(name)
        if item is not None:
            ext, data = item
            tmp = out / (name + ext + ".part")
            try:
                tmp.write_bytes(data)
                tmp.replace(out / (name + ext))
                written.append(name)
            except OSError:
                try:
                    tmp.unlink()
                except OSError:
                    pass
        if progress is not None:
            try:
                progress(done, total, name)
            except Exception:
                pass
    if out_dir is None:
        (out / _MUSIC_MARK).write_text(str(_ogg_format()), encoding="ascii")
    return written


def ensure_atlases() -> Path:
    for d in (assets_dir(), bundled_assets_dir()):
        if atlases_present(d):
            return d
    install = detect_install()
    if not install:
        raise SetupError(t("err_no_install"))
    return extract_atlases(install)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    install = Path(argv[0]) if argv else detect_install()
    if install is None:
        print("未找到 Rain World 安装。用法：python -m slugcatpet.gameassets <游戏根目录>")
        return 2
    try:
        dest = extract_atlases(install)
    except SetupError as e:
        print(f"导入失败：{e}")
        return 1
    print(f"已从 {install} 导入图集到 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
