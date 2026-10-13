"""场景配乐弹窗：给每个场景选曲目、循环/一次、音量，可逐行试听；完成才保存。"""

from __future__ import annotations
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon

from ...i18n import t
from ...audio.director import MODE_LOOP, MODE_ONCE, SCENES, game_title, track_title
from ..theme import qss
from ..theme.palette import TEXT, TEXT_DISABLED, TEXT_ON_ACCENT
from ..widgets.dialogs import CardDialog
from ..widgets.tips import install as install_tip
from .musicpanel import transport_icon

_SCENE_KEYS = {
    "intro": "scene_intro",
    "settings": "scene_settings",
    "none": "scene_none",
    "blizzard": "settings_snow",
    "zerog": "settings_zerog",
    "water": "settings_water",
}
_TRACK_ROLE = Qt.ItemDataRole.UserRole
_VOL_STEP = 5


def _preview_icon(kind: str, active: bool) -> QIcon:
    """试听键图标：激活时用主按钮上的字色，禁用时变灰。"""
    icon = transport_icon(kind, TEXT_ON_ACCENT if active else TEXT)
    dim = transport_icon(kind, TEXT_DISABLED)
    for size in dim.availableSizes():
        icon.addPixmap(dim.pixmap(size), QIcon.Mode.Disabled)
    return icon


class _VolumePopup(QWidget):
    """按钮下方弹出的竖向音量条，点外面收起。"""

    def __init__(self, value: int, on_change, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(qss.VOLUME_POP)
        frame = QFrame(self)
        frame.setObjectName("volPop")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        col = QVBoxLayout(frame)
        col.setContentsMargins(10, 10, 10, 8)
        col.setSpacing(6)
        self._val = QLabel(f"{value}%")
        self._val.setObjectName("volPopVal")
        self._val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._val)
        sl = QSlider(Qt.Orientation.Vertical)
        sl.setRange(0, 100)
        sl.setSingleStep(_VOL_STEP)
        sl.setPageStep(10)
        sl.setValue(value)
        sl.setFixedHeight(110)
        sl.valueChanged.connect(lambda n: (self._val.setText(f"{n}%"), on_change(n)))
        col.addWidget(sl, 0, Qt.AlignmentFlag.AlignHCenter)
        self.setFixedWidth(52)

    def show_under(self, w: QWidget):
        self.adjustSize()
        pos = w.mapToGlobal(QPoint((w.width() - self.width()) // 2, w.height() + 4))
        self.move(pos)
        self.show()


class _VolumeButton(QPushButton):
    """显示百分比的音量按钮：点击弹出音量条，悬停滚轮按 5% 调。"""

    changed = Signal(int)

    def __init__(self, value: int):
        super().__init__()
        self.setObjectName("sceneVol")
        self.setFixedWidth(52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._value = value
        self.clicked.connect(self._pop)
        install_tip(self, t("scene_volume_tip"))
        self._refresh()

    def set_value(self, v: int):
        v = max(0, min(100, int(v)))
        if v != self._value:
            self._value = v
            self._refresh()
            self.changed.emit(v)

    def setEnabled(self, on: bool):
        super().setEnabled(on)
        self._refresh()

    def _refresh(self):
        self.setText(f"{self._value}%" if self.isEnabled() else "–")

    def _pop(self):
        _VolumePopup(self._value, self.set_value, parent=self).show_under(self)

    def wheelEvent(self, e):
        if not self.isEnabled():
            return super().wheelEvent(e)
        step = _VOL_STEP if e.angleDelta().y() > 0 else -_VOL_STEP
        self.set_value((self._value // _VOL_STEP) * _VOL_STEP + step)
        e.accept()


class _Row:
    __slots__ = ("scene", "preview", "combo", "loop", "once", "vol")


class SceneMusicDialog(CardDialog):
    def __init__(self, director, player, write_state, parent=None):
        super().__init__(t("settings_scene_music"), parent, width=590)
        self._card.setStyleSheet(qss.SCENE_MUSIC)
        self._director = director
        self._player = player
        self._write_state = write_state
        self._cfg = director.config
        self._pv_scene = None  # 正在试听的那一行
        self._icons = {(k, on): _preview_icon(k, on) for k in ("play", "pause") for on in (0, 1)}

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        for col, key in enumerate(
            ("scene_col_scene", "scene_col_track", "scene_col_mode", "scene_col_volume")
        ):
            head = QLabel(t(key))
            head.setObjectName("sceneHead")
            grid.addWidget(head, 0, col if col == 0 else col + 1, 1, 2 if col == 0 else 1)
        self._rows = {}
        for r, scene in enumerate(SCENES, start=1):
            self._rows[scene] = self._build_row(grid, r, scene)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        cancel = self.add_button(t("settings_cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        ok = self.add_button(t("skin_done"), "primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)

        for sig in (player.playing_changed, player.track_changed, player.played_once):
            sig.connect(self._refresh_previews)
        self._refresh_previews()

    def _build_row(self, grid, r, scene):
        cfg = self._cfg[scene]
        row = _Row()
        row.scene = scene

        pv = QPushButton()
        pv.setObjectName("scenePreview")
        pv.setCheckable(True)
        pv.setFixedSize(22, 22)
        pv.setIconSize(QSize(12, 12))
        pv.setCursor(Qt.CursorShape.PointingHandCursor)
        pv.clicked.connect(lambda _c=False, s=scene: self._on_preview(s))
        install_tip(pv, t("scene_preview"))
        grid.addWidget(pv, r, 0)
        row.preview = pv

        name = QLabel(t(_SCENE_KEYS[scene]))
        name.setObjectName("sceneName")
        grid.addWidget(name, r, 1)

        combo = QComboBox()
        combo.setFixedWidth(210)
        combo.view().setMinimumWidth(260)
        self._fill_tracks(combo, cfg["track"])
        combo.currentIndexChanged.connect(lambda _i, s=scene: self._on_track(s))
        grid.addWidget(combo, r, 2)
        row.combo = combo

        seg = QWidget()
        seg_l = QGridLayout(seg)
        seg_l.setContentsMargins(0, 0, 0, 0)
        seg_l.setSpacing(0)
        group = QButtonGroup(seg)
        group.setExclusive(True)
        for col, (mode, obj, key, tip) in enumerate(
            (
                (MODE_LOOP, "segLeft", "scene_mode_loop", "scene_mode_loop_tip"),
                (MODE_ONCE, "segRight", "scene_mode_once", "scene_mode_once_tip"),
            )
        ):
            b = QPushButton(t(key))
            b.setObjectName(obj)
            b.setCheckable(True)
            b.setChecked(cfg["mode"] == mode)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if scene == "intro" and mode == MODE_LOOP:
                tip = "scene_intro_once_tip"
            install_tip(b, t(tip))
            b.toggled.connect(lambda on, s=scene, m=mode: on and self._on_mode(s, m))
            group.addButton(b)
            seg_l.addWidget(b, 0, col)
        row.loop, row.once = group.buttons()
        grid.addWidget(seg, r, 3)

        vol = _VolumeButton(round(cfg["gain"] * 100))
        vol.changed.connect(lambda n, s=scene: self._on_gain(s, n))
        grid.addWidget(vol, r, 4)
        row.vol = vol

        self._sync_row(row)
        return row

    def _fill_tracks(self, combo, current):
        combo.addItem(t("scene_track_none"), None)
        found = current is None
        groups = (
            (
                t("music_game_group"),
                [(game_title(tr.path.stem), tr.path.stem) for tr in self._player.game_tracks()],
            ),
            (t("scene_my_music"), [(tr.name, str(tr.path)) for tr in self._player.tracks]),
        )
        for title, items in groups:
            if not items:
                continue
            combo.insertSeparator(combo.count())
            combo.addItem(title)
            combo.model().item(combo.count() - 1).setEnabled(False)
            for text, tid in items:
                combo.addItem(text, tid)
                if tid == current:
                    found = True
        if not found:
            combo.insertSeparator(combo.count())
            combo.addItem(t("scene_track_missing", name=track_title(current)), current)
        idx = combo.findData(current)
        combo.setCurrentIndex(max(0, idx))

    def _sync_row(self, row):
        cfg = self._cfg[row.scene]
        has = cfg["track"] is not None
        row.preview.setEnabled(has and self._director.resolve(cfg["track"]) is not None)
        row.loop.setEnabled(has and row.scene != "intro")
        row.once.setEnabled(has)
        row.vol.setEnabled(has)

    def _on_track(self, scene):
        row = self._rows[scene]
        self._cfg[scene]["track"] = row.combo.currentData()
        if self._pv_scene == scene:
            self._director.stop_preview()
            self._pv_scene = None
        self._sync_row(row)
        self._refresh_previews()

    def _on_mode(self, scene, mode):
        self._cfg[scene]["mode"] = mode

    def _on_gain(self, scene, n):
        self._cfg[scene]["gain"] = n / 100.0
        if self._pv_scene == scene:
            self._director.set_preview_gain(n / 100.0)

    def _on_preview(self, scene):
        d = self._director
        if self._pv_scene == scene and d.preview_active():
            if d.preview_playing():
                d.pause_preview()
            else:
                d.resume_preview()
        else:
            cfg = self._cfg[scene]
            self._pv_scene = scene if d.preview(cfg["track"], cfg["gain"]) else None
        self._refresh_previews()

    def _refresh_previews(self, *_args):
        d = self._director
        if self._pv_scene is not None and not d.preview_active():
            self._pv_scene = None
        playing = d.preview_playing()
        for scene, row in self._rows.items():
            active = scene == self._pv_scene
            row.preview.setChecked(active)
            row.preview.setIcon(self._icons[("pause" if active and playing else "play", int(active))])

    def done(self, result):
        if self._finished:
            return
        for sig in (self._player.playing_changed, self._player.track_changed, self._player.played_once):
            sig.disconnect(self._refresh_previews)
        if result == self.DialogCode.Accepted:
            self._director.set_config(self._cfg)
            self._write_state()
        else:
            self._director.end_preview()
        super().done(result)
