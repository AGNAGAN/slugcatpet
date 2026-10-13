"""皮肤文件夹里的说明、绘制模板与加载报告。"""

from __future__ import annotations

from pathlib import Path

from .. import i18n
from . import sources

TEMPLATES_SUBDIR = "_templates"
TEMPLATE_SPECIES = ("survivor", "monk", "hunter", "rivulet", "saint", "artificer")

_README = {
    "zh": (
        "说明.txt",
        """别人给的皮肤（文件夹或 zip）放进这里就行。创意工坊里订阅的会自动读取，不用放。
换皮肤、改颜色：在设置里点猫旁边的「外观」。
自己画：把 _templates 里的一只猫复制到这里，改里面的 png，再把 metadata.json 里的 id 和 name 改成自己的。
格式和 Dress My Slugcat 一样，见它的创意工坊页面：https://steamcommunity.com/sharedfiles/filedetails/?id=2948971756
皮肤读不出来时，原因会写在「加载报告.txt」里。
""",
    ),
    "en": (
        "README.txt",
        """Put skins you get from others (folders or zips) here. Workshop subscriptions are read automatically.
Change a skin or colors: in Settings, click "Appearance" next to a cat.
Draw your own: copy a cat from _templates to here, edit its pngs, and change id and name in metadata.json.
The format is Dress My Slugcat's; see its Workshop page: https://steamcommunity.com/sharedfiles/filedetails/?id=2948971756
If a skin doesn't load, the reason is in load_report.txt.
""",
    ),
}
_OLD_BAT = ("编辑猫.bat", "Edit cats.bat")
_REPORT = {"zh": "加载报告.txt", "en": "load_report.txt"}


def _lang():
    return "zh" if i18n.LANG == "zh" else "en"


def _write_if_changed(path: Path, text: str, encoding="utf-8") -> None:
    try:
        if path.exists() and path.read_text(encoding=encoding) == text:
            return
    except (OSError, UnicodeError):
        pass
    path.write_text(text, encoding=encoding)


def ensure_folder(base_atlas=None) -> Path:
    root = sources.skins_dir()
    lang = _lang()
    for other in ("zh", "en"):
        if other != lang:
            for name in (_README[other][0], _REPORT[other]):
                (root / name).unlink(missing_ok=True)
    for name in _OLD_BAT:
        (root / name).unlink(missing_ok=True)
    name, text = _README[lang]
    _write_if_changed(root / name, text, encoding="utf-8-sig")
    tdir = root / TEMPLATES_SUBDIR
    if base_atlas is not None and not tdir.exists():
        from .template import export_template

        for sp in TEMPLATE_SPECIES:
            export_template(tdir / sp, base_atlas, sp)
    return root


def write_report() -> None:
    from . import problems

    root = sources.skins_dir()
    path = root / _REPORT[_lang()]
    lines = problems()
    if lines:
        _write_if_changed(path, "\n".join(lines) + "\n", encoding="utf-8-sig")
    else:
        path.unlink(missing_ok=True)
