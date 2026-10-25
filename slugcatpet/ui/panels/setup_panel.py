"""首次启动素材初始化面板：run() 阻塞至成功或放弃。"""

from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QProgressBar,
    QFileDialog,
)
from PySide6.QtCore import Qt, QObject, QThread, QEventLoop, Signal

from ...gameassets import detect_install, ensure_atlases, extract_atlases, extract_music, SetupError
from ...i18n import t
from ..theme import qss


class _ImportWorker(QObject):
    """后台导入：install 为 None 走自动定位，否则从指定目录提取；图集之后依次跑 extras。"""

    done = Signal()
    failed = Signal(str)

    def __init__(self, install: Path | None, extras):
        super().__init__()
        self._install = install
        self._extras = extras

    def run(self):
        try:
            if self._install is None:
                ensure_atlases()
            else:
                extract_atlases(self._install)
            self._run_extras()
            self.done.emit()
        except SetupError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(t("setup_unexpected", e=e))

    def _run_extras(self):
        """图集之外的素材顺带提取，失败不算导入失败。"""
        install = self._install or detect_install()
        if install is None:
            return
        for fn in self._extras:
            try:
                fn(install)
            except Exception:
                pass


def _extract_game_music(install: Path) -> None:
    from ...audio.director import GAME_TRACKS

    extract_music(install, GAME_TRACKS)


class SetupPanel(QDialog):
    def __init__(self, extras=(_extract_game_music,), parent=None):
        """extras：图集之后要提取的素材，每个是 fn(游戏目录)。"""
        super().__init__(parent)
        self._extras = extras
        self._result = False
        self._loop: QEventLoop | None = None
        self._thread: QThread | None = None
        self._worker: _ImportWorker | None = None

        # 首次启动窗口保持普通对话框；不按屏幕坐标自定位，交给合成器放置。
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._build()

    def _build(self):
        self._card = QWidget(self)
        self._card.setObjectName("setupCard")
        col = QVBoxLayout(self._card)
        col.setContentsMargins(28, 24, 28, 22)
        col.setSpacing(14)

        self._title = QLabel(t("app_title"))
        self._title.setObjectName("setupTitle")

        self._status = QLabel(t("setup_importing"))
        self._status.setObjectName("setupStatus")
        self._status.setWordWrap(True)

        self._hint = QLabel(t("setup_hint_init"))
        self._hint.setObjectName("setupHint")
        self._hint.setWordWrap(True)

        self._bar = QProgressBar()
        self._bar.setObjectName("setupBar")
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)

        self._btns = QWidget()
        row = QHBoxLayout(self._btns)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addStretch(1)
        self._btn_quit = QPushButton(t("setup_quit"))
        self._btn_quit.setObjectName("btnGhost")
        self._btn_quit.clicked.connect(self._on_quit)
        self._btn_pick = QPushButton(t("setup_pick"))
        self._btn_pick.setObjectName("btnPrimary")
        self._btn_pick.clicked.connect(self._on_pick)
        row.addWidget(self._btn_quit)
        row.addWidget(self._btn_pick)
        self._btns.hide()

        col.addWidget(self._title)
        col.addWidget(self._status)
        col.addWidget(self._hint)
        col.addWidget(self._bar)
        col.addWidget(self._btns)

        self._card.setStyleSheet(qss.SETUP_CARD)

    def _place(self):
        self._card.setFixedWidth(380)
        self._card.adjustSize()
        size = self._card.size()
        self.resize(size)
        self._card.setGeometry(0, 0, size.width(), size.height())

    def _set_busy(self):
        self._status.setText(t("setup_importing"))
        self._hint.setText(t("setup_hint_busy"))
        self._bar.show()
        self._btns.hide()
        self._place()

    def _set_error(self, msg: str):
        self._status.setText(msg)
        self._hint.setText(t("setup_hint_error"))
        self._bar.hide()
        self._btns.show()
        self._place()

    def _start_import(self, install: Path | None):
        self._set_busy()
        self._thread = QThread(self)
        self._worker = _ImportWorker(install, self._extras)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_done(self):
        self._result = True
        if self._loop is not None:
            self._loop.quit()

    def _on_failed(self, msg: str):
        self._set_error(msg)

    def _on_pick(self):
        d = QFileDialog.getExistingDirectory(self, t("setup_pick"))
        if d:
            self._start_import(Path(d))

    def _on_quit(self):
        self._result = False
        if self._loop is not None:
            self._loop.quit()

    def closeEvent(self, ev):
        if self._loop is not None and self._loop.isRunning():
            self._result = False
            self._loop.quit()
        ev.accept()

    def run(self) -> bool:
        self._place()
        self.show()
        self.raise_()
        self._loop = QEventLoop()
        self._start_import(None)
        self._loop.exec()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        self.hide()
        return self._result
