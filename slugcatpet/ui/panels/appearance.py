"""设置页「皮肤」区块与单只猫的外观弹窗。"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import i18n, skins
from ...accessories import BUILTIN as ACCESSORIES
from ...appearance import EMPTY, PART_GROUPS, TAIL_KEYS, accessory_color, shown_source, whole_set
from ...i18n import t
from ...skins.folder import ensure_folder
from ..theme import qss
from ..theme.palette import BG_CARD, BORDER, TEXT_DIM, WARN
from ..widgets.iconkit import ui_icon
from ..widgets.dialogs import CardDialog
from ..widgets.screens import available_at


def open_skin_folder(window):
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(ensure_folder(window.atlas))))


def build_skin_section(settings, v):
    v.addWidget(settings._header(t("settings_skins_section")))

    b = QPushButton(t("settings_skins_open"))
    b.clicked.connect(lambda: open_skin_folder(settings._window))
    v.addWidget(b)

    chk = QCheckBox(t("settings_skins_scan"))
    chk.setChecked(skins.scan_external())

    def on_scan(checked):
        skins.configure(checked)
        settings._window.reload_skins()
        settings._write_state()
        settings._rebuild()

    chk.toggled.connect(on_scan)
    v.addWidget(chk)

    n_bad = len(skins.problems())
    text = t("settings_skins_status", n=len(skins.packs()))
    if n_bad:
        text += t("settings_skins_status_bad", n=n_bad)
    lab = QLabel(text)
    lab.setStyleSheet(qss.ERROR_TEXT if n_bad else qss.DIM_TEXT)
    v.addWidget(lab)


class AppearanceDialog(CardDialog):
    """改动即时生效，完成=保留，取消=还原。"""

    def __init__(self, pet, parent=None):
        super().__init__(t("look_button"), parent, width=DIALOG_W)
        self._card.setStyleSheet(qss.LOOK_DIALOG)
        pet.window.reload_skins(force=False)
        self._pet = pet
        self._orig = pet.look.copy()
        self._look = pet.look.copy()
        self._pop = None
        self._resets = {}  # 部位组 → 该行的重置键
        self._thumbs = {}  # 缩略图缓存

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_head(t("look_skin")))
        self.combo = QComboBox()
        self.combo.activated.connect(self._on_whole)
        row.addWidget(self.combo, 1)
        self.body.addLayout(row)

        self.parts_toggle = QToolButton()
        self.parts_toggle.setObjectName("partsToggle")
        self.parts_toggle.setText(t("look_parts"))
        self.parts_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.parts_toggle.setCheckable(True)
        self.parts_toggle.toggled.connect(self._on_parts_toggle)
        self.body.addWidget(self.parts_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.parts_box = QWidget()
        self.parts_box.setObjectName("partsBox")
        self.parts_grid = QGridLayout(self.parts_box)
        self.parts_grid.setContentsMargins(12, 0, 0, 0)
        self.parts_grid.setHorizontalSpacing(8)
        self.parts_grid.setVerticalSpacing(4)
        self.parts_area = QScrollArea()
        self.parts_area.setObjectName("partsScroll")
        self.parts_area.setWidget(self.parts_box)
        self.parts_area.setWidgetResizable(True)
        self.parts_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.parts_area.setFrameShape(QFrame.Shape.NoFrame)
        self.parts_area.setVisible(False)
        self.body.addWidget(self.parts_area)

        self._color_block()
        self._acc_block()

        cancel = self.add_button(t("settings_cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        ok = self.add_button(t("skin_done"), "primary")
        ok.clicked.connect(self.accept)
        self._sync()

    # ── 整套 ──

    def _groups(self):
        """面板里列出的部位：身体部位 + 戴着的配件。"""
        out = list(PART_GROUPS)
        for cls in ACCESSORIES:
            if cls.skin_group and self._look.wears(cls, self._pet.cat.key):
                out.append(cls.skin_group)
        return out

    def _fill_combo(self):
        c = self.combo
        c.blockSignals(True)
        c.clear()
        model = c.model()
        cur = whole_set(self._look, self._groups(), skins.get)
        if cur is None:
            c.addItem(t("look_mixed"), None)
            model.item(0).setEnabled(False)
        c.addItem(t("skin_original"), "")
        for title, packs in _collections(skins.packs(), self._pet.cat.key):
            if title:
                c.addItem(title, None)
                it = model.item(c.count() - 1)
                it.setEnabled(False)
                f = QFont()
                f.setBold(True)
                it.setFont(f)
            for p in packs:
                c.addItem(("    " if title else "") + p.name, p.id)
                if p.missing or p.rejected:
                    it = model.item(c.count() - 1)
                    it.setForeground(QColor(WARN))
                    it.setToolTip(_pack_problems(p))
        c.setCurrentIndex(0 if cur is None else max(0, c.findData(cur)))
        c.blockSignals(False)

    def _on_whole(self, idx):
        sid = self.combo.itemData(idx)
        if sid is None:
            return
        self._look.set_skin(sid, self._groups())
        self._apply()

    # ── 部位 ──

    def _on_parts_toggle(self, on):
        self.parts_area.setVisible(on)
        self._paint_toggle()
        self._fit()

    def _paint_toggle(self):
        down = self.parts_toggle.isChecked()
        self.parts_toggle.setArrowType(Qt.ArrowType.DownArrow if down else Qt.ArrowType.RightArrow)

    def _fill_parts(self):
        g = self.parts_grid
        while g.count():
            w = g.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._resets = {}

        def add(w, r, c):
            g.addWidget(w, r, c)
            w.show()  # 弹窗可见时新加的控件需立即显示

        for r, grp in enumerate(self._groups()):
            add(_text(self._part_name(grp)), r, 0)
            sid = self._shown(grp)
            b = _PackButton(self._pack_text(sid, grp))
            b.setObjectName("partPack")
            b.setIcon(self.thumb(sid, grp, THUMB))
            b.setIconSize(QSize(THUMB, THUMB))
            tip = self._pack_warning(sid, grp)
            if tip:
                b.setToolTip(tip)
                b.setStyleSheet(f"#partPack{{color:{WARN};}}")
            b.clicked.connect(lambda _c=False, gr=grp, btn=b: self._open_picker(gr, btn))
            add(b, r, 1)
            sw = _PartSwatch()
            sw.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            sw.clicked.connect(lambda _c=False, gr=grp: self._pick_part_color(gr))
            sw.customContextMenuRequested.connect(lambda _p, gr=grp: self._clear_part_color(gr))
            own = self._own_color(grp) is not None
            sw.set_state(self.part_color(grp), own)
            sw.setToolTip(t("look_color_pick") + (" · " + t("look_color_clear") if own else ""))
            add(sw, r, 2)
            if grp == "TAIL":
                more = _mini("more", t("look_tail_shape"))
                more.clicked.connect(lambda _c=False, btn=more: self._open_tail(btn))
                add(more, r, 3)
            back = _mini("reset", t("look_part_reset"))
            back.clicked.connect(lambda _c=False, gr=grp: self._reset_part(gr))
            sp = back.sizePolicy()
            sp.setRetainSizeWhenHidden(True)  # 每行都占住这一列，按钮出没时列宽不跳
            back.setSizePolicy(sp)
            back.setVisible(self._part_changed(grp))
            g.addWidget(back, r, 4)
            self._resets[grp] = back
        g.setColumnStretch(1, 1)

    def _shown(self, grp):
        """部位行显示的来源：皮肤没有这个部位就显示原皮，缺帧或被拒的仍显示该皮肤以便提示。"""
        sid = self._look.source(grp)
        p = skins.get(sid)
        if p is not None and grp not in p.groups and grp not in p.missing and grp not in p.rejected:
            return ""
        return sid

    def _part_name(self, grp):
        acc = _acc_for(grp)
        if acc is not None:
            return acc.title.get(i18n.LANG) or acc.title["en"]
        return t("part_" + grp)

    def _pack_text(self, sid, grp):
        if sid == EMPTY:
            return t("look_hidden")
        p = skins.get(sid)
        return p.name if p is not None else (sid or t("skin_original"))

    def _pack_warning(self, sid, grp):
        if not sid or sid == EMPTY:
            return ""
        p = skins.get(sid)
        if p is None:
            return t("look_pack_gone")
        if grp in p.missing:
            miss = p.missing[grp]
            return t("skin_missing_group", group=grp, n=len(miss), first=miss[0])
        if grp in p.rejected:
            return next((w for w in p.warnings if grp in w), "")
        return ""

    def _part_changed(self, grp):
        lk = self._look
        if shown_source(lk.source(grp), grp, skins.get) != shown_source(lk.skin or "", grp, skins.get):
            return True
        return self._own_color(grp) is not None or (grp == "TAIL" and lk.tail is not None)

    def set_part(self, grp, sid):
        if sid == (self._look.skin or ""):
            self._look.parts.pop(grp, None)
        else:
            self._look.parts[grp] = sid
        self._apply()

    def _reset_part(self, grp):
        self._look.parts.pop(grp, None)
        self._drop_part_color(grp)
        if grp == "TAIL":
            self._look.tail = None
        self._apply()

    def preview_tail(self, shape):
        """拖尾巴滑条：只更新猫和尾巴行的重置键，不重建整张表。"""
        self._look.tail = shape
        self._pet.set_look(self._look.copy())
        back = self._resets.get("TAIL")
        if back is not None:
            back.setVisible(self._part_changed("TAIL"))

    def _open_picker(self, grp, anchor):
        self._popup(PackPicker(self, grp), anchor)

    def _open_tail(self, anchor):
        self._popup(TailPopup(self), anchor)

    def _popup(self, pop, anchor):
        self._pop = pop
        pop.adjustSize()
        top = anchor.mapToGlobal(QPoint(0, 0))
        pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        r = scr.availableGeometry()
        x = min(pos.x(), r.right() - pop.width())
        y = pos.y() if pos.y() + pop.height() <= r.bottom() else top.y() - pop.height()
        pop.move(max(r.left(), x), max(r.top(), y))
        pop.show()

    # ── 部位颜色 ──

    @staticmethod
    def _color_acc(grp):
        """部位色块改的是配件颜色时返回该配件（配件颜色就取自这个部位组）。"""
        acc = _acc_for(grp)
        return acc if acc is not None and acc.color_group == grp else None

    def part_color(self, grp):
        """部位当前实际颜色（缩略图和色块用）。"""
        acc = self._color_acc(grp)
        if acc is not None:
            return _acc_color(self._look, acc, self._pet.gfx._skin_colors)
        g = self._pet.gfx
        return tuple(g._skin_colors.get(grp, g.EYE if grp == "FACE" else g._body0))

    def _effect_color(self, grp):
        """配件自带的另一种颜色（鳃的效果色），没有则 None。"""
        acc = _acc_for(grp)
        if acc is None or acc.color_group == grp:
            return None
        return _acc_color(self._look, acc, self._pet.gfx._skin_colors)

    def _own_color(self, grp):
        acc = self._color_acc(grp)
        return self._look.acc_color(acc.key) if acc is not None else self._look.part_colors.get(grp)

    def _drop_part_color(self, grp):
        acc = self._color_acc(grp)
        if acc is not None:
            self._look.accessories.get(acc.key, {}).pop("color", None)
        else:
            self._look.part_colors.pop(grp, None)

    def _pick_part_color(self, grp):
        c = QColorDialog.getColor(QColor(*self.part_color(grp)), self)
        if c.isValid():
            self.set_part_color(grp, (c.red(), c.green(), c.blue()))

    def set_part_color(self, grp, rgb):
        acc = self._color_acc(grp)
        if acc is not None:
            self._look.accessories.setdefault(acc.key, {})["color"] = tuple(rgb)
        else:
            self._look.part_colors[grp] = tuple(rgb)
        self._apply()

    def _clear_part_color(self, grp):
        if self._own_color(grp) is None:
            return
        self._drop_part_color(grp)
        self._apply()

    # ── 缩略图 ──

    def thumb(self, sid, grp, side) -> QIcon:
        """部位在某个来源皮肤里的样子，按这只猫当前的颜色上色；零碎的部位垫上半透明的头或身体。"""
        if sid == EMPTY:
            return ui_icon("hidden", TEXT_DIM, side // 2)
        layers = self._layers(sid, grp)
        dpr = self.devicePixelRatioF()
        key = (side, dpr, layers)
        icon = self._thumbs.get(key)
        if icon is None:
            if len(self._thumbs) > THUMB_CACHE:
                self._thumbs.clear()
            sprites = [(self._sprite(*spec[:4]), *spec[4:]) for spec in layers]
            icon = self._thumbs[key] = _render_thumb(sprites, side, dpr)
        return icon

    def _layers(self, sid, grp):
        """缩略图图层：(来源, 部位组, 帧, 颜色, x, y, 旋转, sx, sy, ax, ay, 是否主体)，坐标为原图像素。"""
        col = self.part_color(grp)

        def own(frame, *pose, c=col):
            return (sid, grp, frame, c, *pose, True)

        def ctx(g):
            src = shown_source(self._look.source(g), g, skins.get)
            if src == EMPTY:
                return ()
            return ((src, g, self._frame(src, g), self.part_color(g), 0, 0, 0, 1, 1, 0.5, 0.5, False),)

        center = (0, 0, 0, 1, 1, 0.5, 0.5)
        if grp == "FACE":
            return (*ctx("HEAD"), own(self._frame(sid, grp), *center))
        if grp == "FACESCAR":
            # 正脸时疤相对脸心的偏移，同 ScarAccessory._draw
            return (*ctx("HEAD"), *ctx("FACE"), own(SAMPLE_FRAME[grp], 3, -3, 0, 1, 1, 0.5, 0.5))
        if grp == "ARMS":
            f = SAMPLE_FRAME[grp]
            return (*ctx("BODY"), own(f, -5, -7, 100, 0.75, 1, 0, 0.5), own(f, 5, -7, 80, 0.75, -1, 0, 0.5))
        if grp == "GILLS":
            fx = self._effect_color(grp) or col
            scales = tuple(
                own(frame, s * 5, 2, s * rot, s * 0.8, 0.8, 0.5, 0.9, c=c)
                for frame, c in (("LizardScaleA3", col), ("LizardScaleB3", fx))
                for s in (-1, 1)
                for rot in GILL_FAN
            )
            return (*ctx("HEAD"), *scales)
        if grp == "TAIL":
            return (own(TAIL_FRAME, *center),)
        return (own(self._frame(sid, grp), *center),)

    def _frame(self, sid, grp):
        p = skins.get(sid)
        if (p is None or grp not in p.groups) and grp in ("HEAD", "FACE"):
            return self._pet.cat.frames[grp.lower()][1] + "0"
        return SAMPLE_FRAME[grp]

    def _sprite(self, sid, grp, frame, rgb) -> QPixmap | None:
        """取一帧：来源皮肤有这个部位就用皮肤的，否则用原版图集。"""
        tint = QColor(*rgb)
        p = skins.get(sid)
        pack = p if p is not None and grp in p.groups else None
        if frame == TAIL_FRAME:
            tex = None
            if pack is not None and "TailTexture" in pack.elements:
                atlas, name = pack.elements["TailTexture"]
                tex = atlas.sprite(name, tint, True)
            return _tail_pixmap(tint, tex)
        if pack is not None and frame in pack.elements:
            atlas, name = pack.elements[frame]
            return atlas.sprite(name, tint, True)
        base = self._pet.window.atlas
        key = base.find_atlas(frame)
        return base.sprite(key, frame, tint, True) if key else None

    # ── 颜色、配件 ──

    def _color_block(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_head(t("look_color")))
        self.rb_default = QRadioButton(t("look_default"))
        self.rb_custom = QRadioButton(t("look_custom"))
        grp = QButtonGroup(self)
        for rb in (self.rb_default, self.rb_custom):
            grp.addButton(rb)
            row.addWidget(rb)
        row.addStretch(1)
        (self.rb_custom if self._look.colors else self.rb_default).setChecked(True)
        self.rb_custom.toggled.connect(self._on_custom)
        self.body.addLayout(row)

        self.swatch_box = QWidget()
        sw = QHBoxLayout(self.swatch_box)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(8)
        self.swatch = {}
        for k, lk in (("body", "look_body"), ("face", "look_face")):
            sw.addWidget(_text(t(lk)))
            b = _swatch()
            b.clicked.connect(lambda _c=False, key=k: self._pick_color(key))
            self.swatch[k] = b
            sw.addWidget(b)
        sw.addStretch(1)
        self.swatch_box.setVisible(bool(self._look.colors))
        self._paint_colors()
        self.body.addWidget(self.swatch_box)

    def _on_custom(self, on):
        if on and not self._look.colors:
            g = self._pet.gfx
            self._look.colors = {"body": tuple(g._body0), "face": tuple(g.EYE)}
        elif not on:
            self._look.colors = None
        self.swatch_box.setVisible(on)
        self._paint_colors()
        self._apply()

    def _paint_colors(self):
        if self._look.colors:
            for k, b in self.swatch.items():
                _paint(b, self._look.colors[k])

    def _pick_color(self, k):
        c = QColorDialog.getColor(QColor(*self._look.colors[k]), self)
        if c.isValid():
            self.set_color(k, (c.red(), c.green(), c.blue()))

    def set_color(self, k, rgb):
        self._look.colors[k] = tuple(rgb)
        self._paint_colors()
        self._apply()

    def _acc_block(self):
        self.body.addWidget(_head(t("look_accessories")))
        self.acc_check = {}
        self.acc_swatch = {}
        for cls in ACCESSORIES:
            row = QHBoxLayout()
            row.setSpacing(8)
            chk = QCheckBox(cls.title.get(i18n.LANG) or cls.title["en"])
            chk.setChecked(self._look.wears(cls, self._pet.cat.key))
            chk.toggled.connect(lambda on, c=cls: self._on_acc(c, on))
            row.addWidget(chk, 1)
            b = _swatch()
            b.clicked.connect(lambda _c=False, c=cls: self._pick_acc_color(c))
            row.addWidget(b)
            self.acc_check[cls.key] = chk
            self.acc_swatch[cls.key] = b
            self.body.addLayout(row)
            self._paint_acc(cls)

    def _on_acc(self, cls, on):
        self._look.accessories.setdefault(cls.key, {})["on"] = on
        self._apply()

    def _acc_now(self, cls):
        return _acc_color(self._look, cls, self._pet.gfx._skin_colors)

    def _paint_acc(self, cls):
        _paint(self.acc_swatch[cls.key], self._acc_now(cls))

    def _pick_acc_color(self, cls):
        c = QColorDialog.getColor(QColor(*self._acc_now(cls)), self)
        if c.isValid():
            self.set_acc_color(cls, (c.red(), c.green(), c.blue()))

    def set_acc_color(self, cls, rgb):
        self._look.accessories.setdefault(cls.key, {})["color"] = tuple(rgb)
        self._apply()

    def _apply(self):
        self._pet.set_look(self._look.copy())
        self._sync()

    def _sync(self):
        """按当前外观刷新整套下拉、部位表和配件色块。"""
        self._fill_combo()
        self._paint_toggle()
        self._fill_parts()
        for cls in ACCESSORIES:
            self._paint_acc(cls)
        self._fit()

    def _fit(self):
        """按内容收放卡片；部位表太高时在自身区域里滚动，整窗夹回屏内。"""
        lay = self._card.layout()
        if not self.parts_area.isHidden():
            self.parts_box.layout().activate()
            need = self.parts_box.sizeHint().height()
            self.parts_area.setFixedHeight(need)
            lay.invalidate()
            lay.activate()
            scr = available_at(self.frameGeometry().center())
            over = self._card.sizeHint().height() - (scr.height() - 2 * SCREEN_PAD)
            if over > 0:
                self.parts_area.setFixedHeight(max(PARTS_MIN_H, need - over))
        lay.invalidate()
        lay.activate()
        self._card.adjustSize()
        self.resize(self._card.size())
        self.move(self._clamped(self.pos()))

    def reject(self):
        self._pet.set_look(self._orig)
        super().reject()


def _head(text):
    lab = QLabel(text)
    lab.setObjectName("lookHead")
    return lab


def _text(text):
    lab = QLabel(text)
    lab.setObjectName("cardText")
    return lab


def _swatch():
    b = QPushButton()
    b.setObjectName("swatch")
    return b


def _paint(b, c):
    r, g, bl = c
    hexs = f"#{r:02X}{g:02X}{bl:02X}"
    fg = "#000" if (r * 0.3 + g * 0.59 + bl * 0.11) > 128 else "#fff"
    b.setText(hexs)
    b.setStyleSheet(f"#swatch{{background:{hexs};color:{fg};}}")


def _pack_problems(p) -> str:
    """皮肤缺帧 / 被拒的部位说明，悬停提示用。"""
    lines = [t("skin_missing_group", group=g, n=len(m), first=m[0]) for g, m in sorted(p.missing.items())]
    lines += [w for w in p.warnings if any(g in w for g in p.rejected)]
    return "\n".join(lines)


DIALOG_W = 380
SCREEN_PAD = 24  # 弹窗离屏幕边的最小距离
PARTS_MIN_H = 120  # 部位表需要滚动时的最小高度
THUMB = 28  # 部位行缩略图边长
PICK_THUMB = 40  # 选包弹窗缩略图边长
PICK_COLS = 4
THUMB_CACHE = 256
CONTEXT_ALPHA = 0.28  # 缩略图里垫底的头 / 身体的不透明度
MIN_CONTRAST = 2.5  # 部件与卡片底色的对比度低于此值时描浅色边
OUTLINE = QColor(205, 215, 195, 200)
GILL_FAN = (55, 85, 115)  # 鳃缩略图每侧三片鳞的角度
TAIL_FRAME = "__tail__"  # 缩略图图层：画尾巴示意
# 各部位在缩略图里用哪一帧
SAMPLE_FRAME = {
    "HEAD": "HeadA0",
    "FACE": "FaceA0",
    "BODY": "BodyA",
    "ARMS": "PlayerArm12",
    "HIPS": "HipsA",
    "LEGS": "LegsA0",
    "TAIL": "TailTexture",
    "FACESCAR": "MushroomA",
    "GILLS": "LizardScaleA3",
    "TAILSPECKLES": "tinyStar",
    "ASCENSION": "guardEye",
}
# 尾巴滑块：键 → (最小, 最大, 刻度倍率, 默认)
TAIL_SLIDERS = {
    "length": (2.0, 15.0, 1, 4.0),
    "wideness": (0.1, 10.0, 10, 1.0),
    "roundness": (0.0, 1.5, 100, 0.0),
}


class PackPicker(QFrame):
    """选某个部位的来源皮肤：缩略图网格，点一下即生效并关闭。"""

    def __init__(self, dlg, grp):
        super().__init__(dlg, Qt.WindowType.Popup)
        self.setObjectName("lookPop")
        self.setStyleSheet(qss.LOOK_POP)
        self._dlg = dlg
        self._grp = grp
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 10, 12, 12)
        col.setSpacing(6)
        title = QLabel(dlg._part_name(grp))
        title.setObjectName("lookHead")
        col.addWidget(title)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        cur = dlg._look.source(grp)
        self._grid(v, [("", t("skin_original")), (EMPTY, t("look_hidden"))], cur)
        packs = [p for p in skins.packs() if grp in p.groups]
        for title_text, group in _collections(packs, dlg._pet.cat.key):
            if title_text:
                v.addWidget(_text(title_text))
            self._grid(v, [(p.id, p.name) for p in group], cur)
        area = QScrollArea()
        area.setObjectName("lookPopScroll")
        area.setWidget(inner)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setFrameShape(QFrame.Shape.NoFrame)
        inner.adjustSize()
        area.setFixedWidth(inner.sizeHint().width() + area.verticalScrollBar().sizeHint().width())
        area.setFixedHeight(min(inner.sizeHint().height(), 320))
        col.addWidget(area)

    def _grid(self, v, items, cur):
        g = QGridLayout()
        g.setSpacing(4)
        for i, (sid, name) in enumerate(items):
            b = QToolButton()
            b.setObjectName("packTile")
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIcon(self._dlg.thumb(sid, self._grp, PICK_THUMB))
            b.setIconSize(QSize(PICK_THUMB, PICK_THUMB))
            b.setText(b.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 64))
            b.setToolTip(name)
            b.setFixedSize(72, 68)
            b.setCheckable(True)
            b.setChecked(sid == cur)
            b.clicked.connect(lambda _c=False, sid_=sid: self._choose(sid_))
            g.addWidget(b, i // PICK_COLS, i % PICK_COLS)
        g.setColumnStretch(PICK_COLS, 1)
        v.addLayout(g)

    def _choose(self, sid):
        self.close()
        self._dlg.set_part(self._grp, sid)


class TailPopup(QFrame):
    """尾巴形状：拖动即改为自定形状。"""

    def __init__(self, dlg):
        super().__init__(dlg, Qt.WindowType.Popup)
        self.setObjectName("lookPop")
        self.setStyleSheet(qss.LOOK_POP)
        self._dlg = dlg
        cur = dict(dlg._look.tail or dlg._pet.atlas.tail)
        self._vals = {k: float(cur.get(k, spec[3])) for k, spec in TAIL_SLIDERS.items()}
        g = QGridLayout(self)
        g.setContentsMargins(12, 10, 12, 12)
        g.setHorizontalSpacing(10)
        title = QLabel(t("look_tail_shape"))
        title.setObjectName("lookHead")
        g.addWidget(title, 0, 0, 1, 3)
        self._num = {}
        for r, (k, (lo, hi, mul, _d)) in enumerate(TAIL_SLIDERS.items(), start=1):
            g.addWidget(_text(t("look_tail_" + k)), r, 0)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(round(lo * mul), round(hi * mul))
            sl.setValue(round(self._vals[k] * mul))
            sl.setFixedWidth(140)
            sl.valueChanged.connect(lambda v, key=k, m=mul: self._on(key, v / m))
            g.addWidget(sl, r, 1)
            num = _text("")
            num.setFixedWidth(30)
            g.addWidget(num, r, 2)
            self._num[k] = num
            self._paint(k)

    def _paint(self, k):
        v = self._vals[k]
        self._num[k].setText(f"{v:.0f}" if k == "length" else f"{v:.1f}" if k == "wideness" else f"{v:.2f}")

    def _on(self, k, v):
        self._vals[k] = v
        self._paint(k)
        self._dlg.preview_tail({key: self._vals[key] for key in TAIL_KEYS})


def _collections(packs, species):
    """皮肤按合集分组：[(合集名或"", [皮肤…])]；单个的合集并入散装。"""
    groups = {}
    for p in packs:
        groups.setdefault(p.collection, []).append(p)

    def key(p):
        return (species[:4] not in (p.name + p.id).lower(), p.name.lower())

    loose = groups.pop("", [])
    for name in [n for n in groups if len(groups[n]) == 1]:
        loose += groups.pop(name)
    out = [("", sorted(loose, key=key))] if loose else []
    out += [(name, sorted(groups[name], key=key)) for name in sorted(groups, key=str.lower)]
    return out


def _acc_for(grp):
    return next((c for c in ACCESSORIES if c.skin_group == grp), None)


def _acc_color(look, cls, skin_colors):
    probe = SimpleNamespace(
        color=look.acc_color(cls.key), color_group=cls.color_group, default_color=cls.default_color
    )
    return accessory_color(probe, skin_colors)


def _mini(kind, tip):
    b = QPushButton()
    b.setIcon(ui_icon(kind, TEXT_DIM))
    b.setObjectName("partMini")
    b.setToolTip(tip)
    return b


class _PackButton(QPushButton):
    """部位行的皮肤按钮：宽度随列伸缩，皮肤名按实际宽度省略。"""

    def __init__(self, text):
        super().__init__()
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(THUMB + 60, super().sizeHint().height())

    def minimumSizeHint(self):
        return self.sizeHint()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        avail = self.width() - THUMB - 26  # 减去图标、图文间距、内边距和边框
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(0, avail)))


class _PartSwatch(QPushButton):
    """部位色块：实心=自定颜色，半块带斜线=跟随皮肤 / 整套。"""

    SIZE = 20

    def __init__(self):
        super().__init__()
        self.setObjectName("partSwatch")
        self.setFixedSize(self.SIZE, self.SIZE)
        self._rgb = (0, 0, 0)
        self._own = False

    def set_state(self, rgb, own):
        self._rgb, self._own = tuple(rgb), own
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 4, 4)
        col = QColor(*self._rgb)
        if self._own:
            p.fillPath(path, col)
        else:
            p.setClipPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawPolygon(QPolygonF([r.topRight(), r.bottomRight(), r.bottomLeft()]))
            p.setPen(QPen(QColor(TEXT_DIM), 1.2))
            p.drawLine(r.bottomLeft(), r.topRight())
            p.setClipping(False)
        p.setPen(QPen(QColor(TEXT_DIM if self.underMouse() else BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


def _render_thumb(layers, side: int, dpr: float) -> QIcon:
    """把图层拼成缩略图：按整数倍放大（放不下才平滑缩小）居中，垫底图层压暗，主体太暗时描边。"""
    rects, items = [], []
    for pm, x, y, rot, sx, sy, ax, ay, main in layers:
        if pm is None or pm.isNull():
            continue
        tf = (
            QTransform().translate(-ax * pm.width(), -ay * pm.height())
            * QTransform().scale(sx, sy)
            * QTransform().rotate(rot)
            * QTransform().translate(x, y)
        )
        rects.append(tf.mapRect(QRectF(pm.rect())))
        items.append((pm, tf, main))
    if not any(main for _pm, _tf, main in items):
        return QIcon()
    bound = rects[0]
    for r in rects[1:]:
        bound = bound.united(r)
    bound = bound.toAlignedRect()
    shift = QTransform().translate(-bound.x(), -bound.y())
    imgs = {}
    for layer_main in (False, True):
        img = QImage(bound.size(), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        for pm, tf, main in items:
            if main == layer_main:
                p.setTransform(tf * shift)
                p.drawPixmap(0, 0, pm)
        p.end()
        imgs[layer_main] = img
    box = _alpha_box(imgs[False]).united(_alpha_box(imgs[True]))
    if box.isEmpty():
        return QIcon()
    ctx, main = imgs[False].copy(box), imgs[True].copy(box)

    phys = max(1, round(side * dpr))
    w, h = box.width(), box.height()
    if max(w, h) <= phys:
        k = phys // max(w, h)
        size, mode = QSize(w * k, h * k), Qt.TransformationMode.FastTransformation
    else:
        size = QSize(w, h).scaled(phys, phys, Qt.AspectRatioMode.KeepAspectRatio)
        mode = Qt.TransformationMode.SmoothTransformation
    ctx = ctx.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, mode)
    main = main.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, mode)

    out = QImage(phys, phys, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    ox, oy = (phys - size.width()) // 2, (phys - size.height()) // 2
    p = QPainter(out)
    p.setOpacity(CONTEXT_ALPHA)
    p.drawImage(ox, oy, ctx)
    p.setOpacity(1.0)
    if _contrast(main) < MIN_CONTRAST:
        sil = QImage(main)
        sp = QPainter(sil)
        sp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        sp.fillRect(sil.rect(), OUTLINE)
        sp.end()
        d = max(1, round(dpr))
        for dx in (-d, 0, d):
            for dy in (-d, 0, d):
                if dx or dy:
                    p.drawImage(ox + dx, oy + dy, sil)
    p.drawImage(ox, oy, main)
    p.end()
    pm = QPixmap.fromImage(out)
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


def _alpha_box(img: QImage) -> QRect:
    """不透明像素的包围盒（全透明时为空矩形）。"""
    w = img.width()
    alpha = bytes(img.constBits())[3::4]
    top = left = None
    bottom = right = -1
    for y in range(img.height()):
        row = alpha[y * w : (y + 1) * w]
        lead = w - len(row.lstrip(b"\0"))
        if lead == w:
            continue
        if top is None:
            top = y
        bottom = y
        left = lead if left is None else min(left, lead)
        right = max(right, len(row.rstrip(b"\0")) - 1)
    if top is None:
        return QRect()
    return QRect(left, top, right - left + 1, bottom - top + 1)


def _luminance(r, g, b):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


_BG_LUM = _luminance(*QColor(BG_CARD).getRgb()[:3])


def _contrast(img: QImage) -> float:
    """图里不透明像素按透明度加权的平均色，与卡片底色的对比度。"""
    data = bytes(img.convertToFormat(QImage.Format.Format_ARGB32).constBits())
    a = data[3::4]
    total = sum(a)
    if not total:
        return float("inf")
    b, g, r = (sum(map(int.__mul__, data[i::4], a)) / total for i in range(3))
    lum = _luminance(r, g, b)
    hi, lo = max(lum, _BG_LUM), min(lum, _BG_LUM)
    return (hi + 0.05) / (lo + 0.05)


def _tail_pixmap(color: QColor, texture: QPixmap | None) -> QPixmap:
    """尾巴示意：收尖的尾形，皮肤带尾巴贴图时铺上贴图。"""
    w, h = 10, 30
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    if texture is not None and not texture.isNull():
        brush = QBrush(texture)
        brush.setTransform(QTransform().scale(w / texture.width(), h / texture.height()))
        p.setBrush(brush)
    else:
        p.setBrush(color)
    p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w / 2, h)]))
    p.end()
    return out
