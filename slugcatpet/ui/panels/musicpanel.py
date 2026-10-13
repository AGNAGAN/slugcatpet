"""音乐播放面板：导入列表、播放/暂停、顺序/随机/单曲循环、音量与进度。"""

from __future__ import annotations
import os

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QListWidget,
    QListWidgetItem,
    QSlider,
    QFileDialog,
)
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap, QPolygonF

from ...i18n import t
from ...audio.director import game_title
from ...audio.player import AUDIO_EXTS, MODE_ORDER, MODE_SHUFFLE, MODE_ONE, fmt_time
from ..theme import qss
from ..theme.palette import TEXT, TEXT_ON_ACCENT
from ..widgets.tips import install as install_tip

_QSS = qss.settings_window("") + qss.MUSIC_EXTRA

_ROLE = Qt.ItemDataRole.UserRole   # 行数据：("user", 列表索引) 或 ("game", Track)

_ICON_PX = 18


def _transport_icon(kind: str, color: str) -> QIcon:
    dpr = 3
    pm = QPixmap(_ICON_PX * dpr, _ICON_PX * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    s = float(_ICON_PX)

    def tri(x0, x1):
        p.drawPolygon(QPolygonF([QPointF(x0, s * 0.2), QPointF(x1, s * 0.5), QPointF(x0, s * 0.8)]))

    if kind == "play":
        tri(s * 0.3, s * 0.8)
    elif kind == "pause":
        p.drawRoundedRect(QRectF(s * 0.27, s * 0.2, s * 0.16, s * 0.6), 1.2, 1.2)
        p.drawRoundedRect(QRectF(s * 0.57, s * 0.2, s * 0.16, s * 0.6), 1.2, 1.2)
    elif kind == "next":
        tri(s * 0.22, s * 0.66)
        p.drawRoundedRect(QRectF(s * 0.66, s * 0.2, s * 0.12, s * 0.6), 1.0, 1.0)
    elif kind == "prev":
        p.save()
        p.translate(s, 0)
        p.scale(-1, 1)
        tri(s * 0.22, s * 0.66)
        p.drawRoundedRect(QRectF(s * 0.66, s * 0.2, s * 0.12, s * 0.6), 1.0, 1.0)
        p.restore()
    p.end()
    return QIcon(pm)


_MODE_KEYS = {
    MODE_ORDER: "music_mode_order",
    MODE_SHUFFLE: "music_mode_shuffle",
    MODE_ONE: "music_mode_one",
}


class MusicPanel(QWidget):
    def __init__(self, player, write_state=None, on_close=None):
        super().__init__()
        self._player = player
        self._write_state = write_state
        self._on_close = on_close
        self._syncing = False  # 程序改列表/滑块时抑制回调
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle(t("music_title"))
        self.setStyleSheet(_QSS)
        self.setMinimumWidth(420)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(16, 14, 16, 14)
        self._outer.setSpacing(10)
        self._body = None
        self._connected = False
        self._rebuild()

    def open(self):
        if not self._connected:
            self._connect()
        self._refresh_list()
        self._refresh_now()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, ev):
        self._save()
        super().closeEvent(ev)

    def _save(self):
        if self._write_state is not None:
            self._write_state()

    def _connect(self):
        self._player.track_changed.connect(lambda _t: self._refresh_now())
        self._player.playing_changed.connect(self._refresh_play_button)
        self._player.mode_changed.connect(lambda _m: self._refresh_mode())
        self._player.volume_changed.connect(self._refresh_volume)
        self._player.list_changed.connect(self._refresh_list)
        self._player.position_changed.connect(self._on_position)
        self._player.mute_changed.connect(lambda _m: self._refresh_now())
        self._player.failed.connect(self._on_failed)
        self._connected = True

    def _rebuild(self):
        self.setWindowTitle(t("music_title"))
        if self._body is not None:
            self._outer.removeWidget(self._body)
            self._body.setParent(None)
            self._body.deleteLater()
        self._body = QWidget()
        v = QVBoxLayout(self._body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self._build_header(v)
        v.addWidget(self._divider())
        self._build_list(v)
        v.addWidget(self._divider())
        self._build_controls(v)
        self._build_progress(v)

        self._outer.addWidget(self._body)
        self._refresh_list()
        self._refresh_now()
        self._refresh_mode()
        self._refresh_volume(self._player.volume)
        self.adjustSize()

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(qss.DIVIDER_LINE)
        return f

    def _build_header(self, v):
        header = QLabel(t("music_title"))
        header.setObjectName("secHeader")
        v.addWidget(header)
        self._now_lbl = QLabel(t("music_empty"))
        self._now_lbl.setObjectName("nowPlaying")
        self._now_lbl.setWordWrap(True)
        v.addWidget(self._now_lbl)

    def _build_list(self, v):
        self._list = QListWidget()
        self._list.setMinimumHeight(150)
        self._list.itemDoubleClicked.connect(self._on_item_activated)
        self._list.currentRowChanged.connect(self._on_row_changed)
        v.addWidget(self._list)

    def _build_controls(self, v):
        row = QHBoxLayout()
        row.setSpacing(6)
        b_files = QPushButton(t("music_import_files"))
        b_files.clicked.connect(self._import_files)
        row.addWidget(b_files)
        b_dir = QPushButton(t("music_import_dir"))
        b_dir.clicked.connect(self._import_dir)
        row.addWidget(b_dir)
        b_open = QPushButton(t("music_open_folder"))
        b_open.clicked.connect(self._open_folder)
        row.addWidget(b_open)
        b_rescan = QPushButton(t("music_rescan"))
        b_rescan.clicked.connect(self._rescan)
        row.addWidget(b_rescan)
        row.addStretch(1)
        b_remove = QPushButton(t("music_remove"))
        b_remove.clicked.connect(self._remove_selected)
        row.addWidget(b_remove)
        v.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self._icons = {k: _transport_icon(k, TEXT) for k in ("prev", "next")}
        self._icons.update({k: _transport_icon(k, TEXT_ON_ACCENT) for k in ("play", "pause")})
        self._prev_btn = self._transport("prev", "music_prev", lambda: self._player.prev())
        row2.addWidget(self._prev_btn)
        self._play_btn = self._transport("play", "music_play", self._on_play_clicked, main=True)
        row2.addWidget(self._play_btn)
        self._next_btn = self._transport("next", "music_next", lambda: self._player.next())
        row2.addWidget(self._next_btn)
        self._mode_btn = QPushButton(t("music_mode_order"))
        install_tip(self._mode_btn, t("music_mode_order"))
        self._mode_btn.clicked.connect(self._player.cycle_mode)
        row2.addWidget(self._mode_btn)
        row2.addStretch(1)
        row2.addWidget(QLabel(t("music_volume")))
        self._vol = QSlider(Qt.Orientation.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setFixedWidth(120)
        self._vol.valueChanged.connect(self._on_volume)
        row2.addWidget(self._vol)
        v.addLayout(row2)

    def _transport(self, icon, tip, slot, main=False):
        b = QPushButton()
        b.setObjectName("transportMain" if main else "transport")
        b.setIcon(self._icons[icon])
        b.setIconSize(QSize(_ICON_PX, _ICON_PX))
        b.setFixedSize(36 if main else 30, 36 if main else 30)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        install_tip(b, t(tip))
        b.clicked.connect(lambda _c=False: slot())
        return b

    def _build_progress(self, v):
        row = QHBoxLayout()
        row.setSpacing(6)
        self._pos_lbl = QLabel("00:00")
        row.addWidget(self._pos_lbl)
        b_back = QPushButton("-5s")
        install_tip(b_back, t("music_back5"))
        b_back.clicked.connect(lambda: self._player.relative_seek(-5000))
        row.addWidget(b_back)
        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.sliderReleased.connect(self._on_seek_released)
        row.addWidget(self._seek, 1)
        b_fwd = QPushButton("+5s")
        install_tip(b_fwd, t("music_forward5"))
        b_fwd.clicked.connect(lambda: self._player.relative_seek(5000))
        row.addWidget(b_fwd)
        self._dur_lbl = QLabel("00:00")
        row.addWidget(self._dur_lbl)
        v.addLayout(row)

    def _refresh_list(self):
        if not hasattr(self, "_list"):
            return
        self._syncing = True
        self._list.clear()
        for i, tr in enumerate(self._player.tracks):
            item = QListWidgetItem(f"{i + 1}. {tr.name}")
            item.setData(_ROLE, ("user", i))
            self._list.addItem(item)
        games = self._player.game_tracks()
        if games:
            head = QListWidgetItem(t("music_game_group"))
            f = QFont(head.font())
            f.setBold(True)
            head.setFont(f)
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(head)
            for tr in games:
                item = QListWidgetItem("    " + game_title(tr.path.stem))
                item.setData(_ROLE, ("game", tr))
                self._list.addItem(item)
        self._syncing = False
        self._refresh_selection()

    def _refresh_now(self):
        if not hasattr(self, "_now_lbl"):
            return
        cur = self._player.current()
        if cur is None:
            self._now_lbl.setText(t("music_empty"))
        else:
            tags = ""
            if self._player.muted:
                tags += " 🔇"
            if self._player.looping:
                tags += " 🔁"
            if self._game_row(cur) is not None:
                self._now_lbl.setText(f"♪ {game_title(cur.path.stem)}  ({t('music_game_group')}){tags}")
            else:
                idx = self._player.index + 1
                n = len(self._player.tracks)
                self._now_lbl.setText(f"♪ {cur.name}  ({idx}/{n}){tags}")
        self._refresh_play_button(self._player.is_playing())
        self._refresh_selection()

    def _refresh_selection(self):
        if not hasattr(self, "_list"):
            return
        self._syncing = True
        row = self._game_row(self._player.current())
        if row is None and 0 <= self._player.index < len(self._player.tracks):
            row = self._player.index
        if row is not None:
            self._list.setCurrentRow(row)
        else:
            self._list.clearSelection()
        self._syncing = False

    def _game_row(self, track):
        if track is None or not hasattr(self, "_list"):
            return None
        for r in range(self._list.count()):
            d = self._list.item(r).data(_ROLE)
            if d and d[0] == "game" and d[1].path == track.path:
                return r
        return None

    def _row_data(self, row):
        item = self._list.item(row) if row >= 0 else None
        return item.data(_ROLE) if item is not None else None

    def _play_row(self, row, autoplay=True):
        d = self._row_data(row)
        if not d:
            return
        if d[0] == "user":
            self._player.set_index(d[1], autoplay=autoplay)
        elif autoplay:
            self._player.play_game_track(d[1])

    def _refresh_play_button(self, playing):
        if not hasattr(self, "_play_btn"):
            return
        self._play_btn.setIcon(self._icons["pause" if playing else "play"])

    def _refresh_mode(self):
        if not hasattr(self, "_mode_btn"):
            return
        key = _MODE_KEYS.get(self._player.mode, "music_mode_order")
        self._mode_btn.setText(t(key))
        install_tip(self._mode_btn, t(key))

    def _refresh_volume(self, v):
        if not hasattr(self, "_vol"):
            return
        self._syncing = True
        self._vol.setValue(int(v))
        self._syncing = False

    def _on_position(self, pos, dur):
        if not hasattr(self, "_seek"):
            return
        self._syncing = True
        self._seek.setRange(0, max(0, dur))
        if not self._seek.isSliderDown():
            self._seek.setValue(pos)
        self._pos_lbl.setText(fmt_time(pos))
        self._dur_lbl.setText(fmt_time(dur))
        self._syncing = False

    def _on_failed(self, path):
        name = os.path.basename(path)
        self._now_lbl.setText(f"⚠ {name}")

    def _remove_selected(self):
        d = self._row_data(self._list.currentRow())
        if not d:
            self._now_lbl.setText(t("music_no_selection"))
            return
        if d[0] == "game":
            self._now_lbl.setText(t("music_game_fixed"))
            return
        self._player.remove_index(d[1])
        self._save()

    def _rescan(self):
        n = self._player.rescan()
        self._refresh_list()
        if n == 0:
            self._now_lbl.setText(t("music_empty"))
        self._save()

    def _on_play_clicked(self):
        if not self._player.is_playing():
            row = self._list.currentRow()
            d = self._row_data(row)
            cur = self._player.current()
            if d and not (cur is not None and self._is_row_of(d, cur)):
                self._play_row(row)
                return
        self._player.toggle()

    def _is_row_of(self, d, track):
        if d[0] == "game":
            return d[1].path == track.path
        return 0 <= d[1] < len(self._player.tracks) and self._player.tracks[d[1]].path == track.path

    def _on_item_activated(self, item):
        self._play_row(self._list.row(item))

    def _on_row_changed(self, row):
        if self._syncing or row < 0:
            return
        self._play_row(row, autoplay=self._player.is_playing())

    def _on_volume(self, v):
        if self._syncing:
            return
        self._player.set_volume(v)
        self._save()

    def _on_seek_released(self):
        self._player.seek(self._seek.value())

    def _import_files(self):
        exts = " ".join(f"*{e}" for e in AUDIO_EXTS)
        files, _ = QFileDialog.getOpenFileNames(
            self, t("music_pick_files"), "", f"Audio ({exts})"
        )
        if files:
            n = self._player.add_paths(files)
            self._notify(n)
            self._save()

    def _import_dir(self):
        d = QFileDialog.getExistingDirectory(self, t("music_pick_dir"), "")
        if d:
            n = self._player.add_paths([d])
            self._notify(n)
            self._save()

    def _open_folder(self):
        from ..._paths import user_music_dir

        path = user_music_dir()
        try:
            os.startfile(str(path))
        except (AttributeError, OSError):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _notify(self, n):
        if n > 0:
            self._now_lbl.setText(t("music_imported", n=n))
        else:
            self._now_lbl.setText(t("music_import_none"))

    def rebuild_ui(self):
        self._rebuild()

    def refresh_selection(self):
        """外部状态变化时同步选中行（未开窗跳过）。"""
        if self.isVisible():
            self._refresh_selection()

