"""从原版图集导出 DMS 格式的皮肤绘制模板。"""

from __future__ import annotations

import json
import math
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from . import groups as G

# 输出文件 → 部件组（PIXEL 桌宠不画，不导出）
FILES = {
    "head": ("HEAD",),
    "face": ("FACE",),
    "body": ("BODY",),
    "hips": ("HIPS",),
    "arm": ("ARMS",),
    "legs": ("LEGS",),
    "tail": ("TAIL",),
    "extras": ("FACESCAR", "GILLS", "TAILSPECKLES", "ASCENSION"),
}
TAIL_SIZE = (150, 75)
ROW_MAX_W = 1024
LABEL_H = 9
GAP = 4
GUIDE = QColor(128, 128, 128, 170)


def _extra(v: int, anchor: float) -> int:
    """画布加量：≥ 原尺寸（四周各留一半），且 anchor*加量 为整数，保证锚点像素对齐。"""
    den = Fraction(anchor).limit_denominator(100).denominator
    want = max(16, v)
    return int(math.ceil(want / den) * den)


def _species_frame(frame: str, species: str) -> str:
    for specific, generic in G.SPECIES_ALIASES.get(species, {}).items():
        if frame.startswith(generic) and frame[len(generic) :].isdigit():
            return specific + frame[len(generic) :]
    return frame


def _frame_image(base, frame: str, species: str = "survivor"):
    if frame == "TailTexture":
        img = QImage(*TAIL_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(255, 255, 255, 255))
        return img, False
    src_frame = _species_frame(frame, species)
    key = base.find_atlas(src_frame)
    if key is None:
        src_frame = frame
        key = base.find_atlas(frame)
    if key is None:
        img = QImage(16, 16, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 0))
        return img, True
    src = base.sprite(key, src_frame, None, True).toImage()
    vw, vh = src.width(), src.height()
    ax, ay = G.frame_anchor(frame)
    ew, eh = _extra(vw, ax), _extra(vh, ay)
    img = QImage(vw + ew, vh + eh, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.drawImage(int(round(ax * ew)), int(round(ay * eh)), src)
    p.end()
    return img, False


def _pack(frames: list[tuple[str, QImage]]):
    x = y = 0
    row_h = 0
    width = 0
    out = []
    for name, img in frames:
        cw, ch = img.width() + GAP * 2, img.height() + LABEL_H + GAP * 2
        if x > 0 and x + cw > ROW_MAX_W:
            x = 0
            y += row_h
            row_h = 0
        out.append((name, img, x + GAP, y + GAP + LABEL_H))
        x += cw
        row_h = max(row_h, ch)
        width = max(width, x)
    return width, y + row_h, out


def _write_atlas(dest: Path, stem: str, frames: list[tuple[str, QImage]]):
    w, h, placed = _pack(frames)
    sheet = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    sheet.fill(QColor(0, 0, 0, 0))
    p = QPainter(sheet)
    font = QFont()
    font.setPixelSize(7)
    p.setFont(font)
    data = {}
    for name, img, fx, fy in placed:
        fw, fh = img.width(), img.height()
        p.drawImage(fx, fy, img)
        p.setPen(GUIDE)
        p.drawRect(QRect(fx - 1, fy - 1, fw + 1, fh + 1))
        p.drawText(
            QRect(fx - 1, fy - LABEL_H - 1, max(fw + 2, 60), LABEL_H),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
            name,
        )
        data[f"{name}.png"] = {
            "frame": {"x": fx, "y": fy, "w": fw, "h": fh},
            "rotated": False,
            "trimmed": False,
            "spriteSourceSize": {"x": 0, "y": 0, "w": fw, "h": fh},
            "sourceSize": {"w": fw, "h": fh},
        }
    p.end()
    sheet.save(str(dest / f"{stem}.png"))
    meta = {
        "app": "slugcatpet",
        "version": "1.0",
        "image": f"{stem}.png",
        "format": "RGBA8888",
        "size": {"w": w, "h": h},
        "scale": "1",
    }
    (dest / f"{stem}.txt").write_text(json.dumps({"frames": data, "meta": meta}, indent=1), encoding="utf-8")


def export_template(dest: Path, base, species: str = "survivor") -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    missing = []
    for file_stem, grps in FILES.items():
        frames = []
        for grp in grps:
            for f in G.GROUPS[grp]:
                img, miss = _frame_image(base, f, species)
                if miss:
                    missing.append(f)
                frames.append((f, img))
        _write_atlas(dest, file_stem, frames)
    meta = {"id": f"template.{species}", "name": f"Template ({species})", "author": "me"}
    (dest / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return missing
