"""从 Rain World 游戏目录选择性导入配乐的二级窗口。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
)

from ..._paths import rainworld_music_dir
from ...gameassets import (
    detect_install,
    extract_music,
    game_music_imported,
    game_music_names,
    is_game_install,
    remember_install,
)
from ...i18n import t
from ..widgets.dialogs import CardDialog

_ROLE = Qt.ItemDataRole.UserRole
_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked
_OUT_EXTS = (".mp3", ".ogg", ".wav")


class _ExtractWorker(QObject):
    progress = Signal(int, int, str)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, install: Path, names: list[str], out_dir: Path):
        super().__init__()
        self._install = install
        self._names = names
        self._out_dir = out_dir

    def run(self):
        try:
            written = extract_music(
                self._install,
                self._names,
                out_dir=self._out_dir,
                progress=lambda done, total, name: self.progress.emit(done, total, name),
            )
            self.done.emit(written)
        except Exception as e:
            self.failed.emit(str(e))


class RainWorldMusicDialog(CardDialog):
    """列出游戏里所有配乐，勾选后复制到 ~/.slugcatpet/music/Rain World。"""

    imported = Signal(int)

    def __init__(self, player, write_state, parent=None):
        super().__init__(t("music_game_title"), parent, width=620)
        self._player = player
        self._write_state = write_state
        self._out_dir = rainworld_music_dir()
        self._install: Path | None = None
        self._names: list[str] = []
        self._items: dict[str, QListWidgetItem] = {}
        self._busy = False
        self._filling = False
        self._thread: QThread | None = None
        self._worker: _ExtractWorker | None = None
        self._running: list[str] = []
        self._build()
        self._scan()

    def _build(self):
        hint = QLabel(t("music_game_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        self.body.addWidget(hint)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._path_lbl = QLabel()
        self._path_lbl.setWordWrap(True)
        self._path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_row.addWidget(self._path_lbl, 1)
        self._pick_btn = QPushButton(t("music_game_pick_dir"))
        self._pick_btn.clicked.connect(self._choose_install)
        path_row.addWidget(self._pick_btn)
        self._reload_btn = QPushButton(t("music_game_rescan"))
        self._reload_btn.clicked.connect(lambda: self._scan())
        path_row.addWidget(self._reload_btn)
        self.body.addLayout(path_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText(t("music_game_search"))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _s: self._apply_filter())
        search_row.addWidget(self._search, 1)
        self._all_btn = QPushButton(t("music_game_select_all"))
        self._all_btn.clicked.connect(lambda: self._set_visible_checks(True))
        search_row.addWidget(self._all_btn)
        self._none_btn = QPushButton(t("music_game_select_none"))
        self._none_btn.clicked.connect(lambda: self._set_visible_checks(False))
        search_row.addWidget(self._none_btn)
        self._new_btn = QPushButton(t("music_game_select_new"))
        self._new_btn.clicked.connect(self._select_new)
        search_row.addWidget(self._new_btn)
        self.body.addLayout(search_row)

        self._list = QListWidget()
        self._list.setMinimumHeight(310)
        self._list.itemChanged.connect(self._on_item_changed)
        self.body.addWidget(self._list)

        self._count = QLabel()
        self._count.setStyleSheet("color: palette(mid);")
        self.body.addWidget(self._count)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.hide()
        self.body.addWidget(self._progress)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self.body.addWidget(self._status)

        self._cancel_btn = self.add_button(t("settings_cancel"), "ghost")
        self._cancel_btn.clicked.connect(self.reject)
        self._import_btn = self.add_button(t("music_game_import"), "primary")
        self._import_btn.clicked.connect(self._start_import)
        self._import_btn.setEnabled(False)

    def _scan(self, install: Path | None = None):
        if self._busy:
            return
        app = QApplication.instance()
        if app is not None:
            app.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._install = install if install is not None else detect_install()
            if self._install is None:
                self._names = []
                self._path_lbl.setText(t("music_game_no_install"))
                self._status.setText(t("music_game_no_install"))
            else:
                self._path_lbl.setText(str(self._install))
                self._names = game_music_names(self._install)
                self._status.setText("" if self._names else t("music_game_none"))
            self._fill_list()
        finally:
            if app is not None:
                app.restoreOverrideCursor()

    def _fill_list(self):
        self._filling = True
        self._list.blockSignals(True)
        self._list.clear()
        self._items.clear()
        for name in self._names:
            item = QListWidgetItem(name)
            item.setData(_ROLE, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(_UNCHECKED)
            self._list.addItem(item)
            self._items[name] = item
        self._list.blockSignals(False)
        self._filling = False
        self._refresh_marks()
        self._apply_filter()
        self._update_count()

    def _refresh_marks(self):
        self._list.blockSignals(True)
        for name, item in self._items.items():
            text = name
            if game_music_imported(name, self._out_dir):
                text = f"{name}  ·  {t('music_game_imported_mark')}"
            item.setText(text)
        self._list.blockSignals(False)

    def _apply_filter(self):
        needle = self._search.text().strip().casefold()
        for name, item in self._items.items():
            item.setHidden(bool(needle and needle not in name.casefold()))

    def _visible_names(self) -> list[str]:
        return [name for name, item in self._items.items() if not item.isHidden()]

    def _selected(self) -> list[str]:
        return [name for name in self._names if self._items[name].checkState() == _CHECKED]

    def _set_visible_checks(self, checked: bool):
        if self._busy:
            return
        self._list.blockSignals(True)
        state = _CHECKED if checked else _UNCHECKED
        for name in self._visible_names():
            self._items[name].setCheckState(state)
        self._list.blockSignals(False)
        self._update_count()

    def _select_new(self):
        if self._busy:
            return
        self._list.blockSignals(True)
        for name in self._visible_names():
            imported = game_music_imported(name, self._out_dir)
            self._items[name].setCheckState(_UNCHECKED if imported else _CHECKED)
        self._list.blockSignals(False)
        self._update_count()

    def _on_item_changed(self, _item):
        if not self._filling:
            self._update_count()

    def _update_count(self):
        selected = len(self._selected())
        self._count.setText(t("music_game_count", selected=selected, total=len(self._names)))
        self._import_btn.setEnabled(selected > 0 and not self._busy and self._install is not None)

    def _choose_install(self):
        if self._busy:
            return
        start = str(self._install or "")
        d = QFileDialog.getExistingDirectory(self, t("music_game_pick_dir"), start)
        if not d:
            return
        path = Path(d)
        if not is_game_install(path):
            self._status.setText(t("music_game_bad_dir"))
            return
        remember_install(path)
        self._scan(path)

    def _set_busy(self, busy: bool):
        self._busy = busy
        for w in (
            self._pick_btn,
            self._reload_btn,
            self._search,
            self._all_btn,
            self._none_btn,
            self._new_btn,
            self._list,
            self._cancel_btn,
        ):
            w.setEnabled(not busy)
        self._progress.setVisible(busy)
        self._update_count()

    def _start_import(self):
        if self._busy or self._install is None:
            return
        names = self._selected()
        if not names:
            return
        self._running = list(names)
        self._set_busy(True)
        self._progress.setRange(0, len(names))
        self._progress.setValue(0)
        self._status.setText(t("music_game_preparing"))
        self._thread = QThread(self)
        self._worker = _ExtractWorker(self._install, names, self._out_dir)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._thread_done)
        self._thread.start()

    def _thread_done(self):
        self._thread = None
        self._worker = None

    def _join_thread(self):
        """让导入线程在弹窗销毁前退出，避免 QThread 运行中被回收。"""
        thread = self._thread
        if thread is not None:
            thread.quit()
            thread.wait(2000)

    def _on_progress(self, done: int, total: int, name: str):
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(done)
        self._status.setText(t("music_game_importing", done=done, total=total, name=name))

    def _on_done(self, _written):
        self._join_thread()
        self._set_busy(False)
        wanted = len(self._running)
        paths = []
        for name in self._running:
            for ext in _OUT_EXTS:
                p = self._out_dir / (name + ext)
                try:
                    if p.is_file() and p.stat().st_size > 0:
                        paths.append(p)
                        break
                except OSError:
                    continue
        added = self._player.add_paths(paths, record=False) if paths else 0
        if self._write_state is not None:
            self._write_state()
        self._refresh_marks()
        self._update_count()
        failed = wanted - len(paths)
        if added and failed:
            text = t("music_game_partial", n=added, failed=failed)
        elif added:
            text = t("music_game_done", n=added)
        else:
            text = t("music_game_done_zero")
        self._status.setText(text)
        self._running = []
        self.imported.emit(added)

    def _on_failed(self, msg: str):
        self._join_thread()
        self._set_busy(False)
        self._status.setText(t("music_game_failed", e=msg))
        self._running = []

    def reject(self):
        if self._busy:
            return
        super().reject()

    def closeEvent(self, ev):
        if self._busy:
            ev.ignore()
            return
        self._join_thread()
        super().closeEvent(ev)
