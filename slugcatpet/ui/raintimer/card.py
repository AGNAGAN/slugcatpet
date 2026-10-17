"""雨循环卡片：空闲时点时长即开始，进行中只给当下有用的几项操作；点卡片外面就关。"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import t
from ...world.raintimer import DRY, DRY_MAX, IDLE, RAIN
from ..theme import palette, qss
from ..widgets.tips import install as install_tip
from .text import fmt_at, fmt_span, parse_input, status_line

DRY_PRESETS = (5, 10, 15, 25, 45, 60)  # 分钟
RAIN_PRESETS = (2, 5, 10, 15)
LIVE_MS = 500
GAP = 8  # 卡片离锚点的距离
INPUT_W = 52
INPUT_MAX_MIN = DRY_MAX // 60


class _MinutesEdit(QLineEdit):
    """分钟输入框：上下键和滚轮每次加减 1 分钟，空着时从默认时长起算。"""

    def __init__(self, fallback_min):
        super().__init__()
        self._fallback = fallback_min

    def _bump(self, d):
        s = self.text().strip()
        if s and not s.isdigit():
            return
        m = max(1, min(INPUT_MAX_MIN, (int(s) if s else self._fallback()) + d))
        self.setText(str(m))
        self.textEdited.emit(self.text())

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Up:
            self._bump(1)
        elif ev.key() == Qt.Key.Key_Down:
            self._bump(-1)
        else:
            super().keyPressEvent(ev)

    def wheelEvent(self, ev):
        d = ev.angleDelta().y()
        if d:
            self._bump(1 if d > 0 else -1)


class RainCard(QWidget):
    _live = None

    @classmethod
    def open_for(cls, timer, dial, anchor: QRect, sides=("left", "right", "above", "below"), on_close=None):
        """在锚点旁边打开卡片，按 sides 的顺序找放得下的一侧。"""
        if cls._live is not None:
            cls._live.close()
        card = cls(timer, dial, anchor, sides, on_close)
        cls._live = card
        card.show()
        card.activateWindow()
        return card

    def __init__(self, timer, dial, anchor, sides, on_close):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(qss.RAIN_CARD)
        self._timer = timer
        self._dial = dial
        self._anchor = anchor
        self._sides = sides
        self._on_close = on_close
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._box = None
        self._head = self._edit = self._suffix = self._preview = None
        timer.listeners.append(self._on_event)
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(LIVE_MS)
        self._live_timer.timeout.connect(self._refresh_live)
        self._live_timer.start()
        self._build()

    # 内容

    def _build(self):
        if self._box is not None:
            self._outer.removeWidget(self._box)
            self._box.deleteLater()
        self._box = QFrame(self)
        self._box.setObjectName("rainCard")
        lay = QVBoxLayout(self._box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self._outer.addWidget(self._box)
        self._head = self._edit = self._suffix = self._preview = None
        tm = self._timer
        if tm.phase == IDLE:
            self._build_idle(lay)
        else:
            self._head = self._label(status_line(tm), "rainHead")
            lay.addWidget(self._head)
            row = QHBoxLayout()
            row.setSpacing(6)
            if tm.phase == DRY:
                row.addWidget(self._button(t("rt_later"), tm.extend))
                row.addWidget(self._button(t("rt_rain_now"), tm.rain_now, close=True))
                row.addWidget(
                    self._button(t("rt_stop_loop") if tm.loop else t("rt_cancel"), tm.cancel, close=True)
                )
            elif tm.phase == RAIN:
                if tm.end_ts is not None:
                    row.addWidget(self._button(t("rt_more_rain"), tm.extend))
                row.addWidget(self._button(t("rt_stop_rain"), tm.stop_rain, close=True))
                if tm.loop:
                    row.addWidget(self._button(t("rt_stop_loop"), tm.cancel, close=True))
            lay.addLayout(row)
            lay.addWidget(self._divider())
            lay.addLayout(self._after_row())
        lay.addWidget(self._divider())
        chk = QCheckBox(t("rt_show_dial"))
        chk.setChecked(self._dial.wanted)
        chk.toggled.connect(self._dial.set_wanted)
        lay.addWidget(chk)
        self._place()

    def _build_idle(self, lay):
        tm = self._timer
        lay.addWidget(self._label(t("rt_dry_head"), "rainHead"))
        row = QHBoxLayout()
        row.setSpacing(4)
        for m in DRY_PRESETS:
            row.addWidget(self._chip(str(m), tm.dry_s == m * 60, lambda m=m: self._start(m * 60)))
        lay.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._edit = _MinutesEdit(lambda: round(tm.dry_s / 60))
        self._edit.setFixedWidth(INPUT_W)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._edit.setPlaceholderText(str(round(tm.dry_s / 60)))
        pal = self._edit.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(palette.TEXT_HINT))
        self._edit.setPalette(pal)
        self._edit.textEdited.connect(self._on_typed)
        self._edit.returnPressed.connect(self._apply_input)
        row.addWidget(self._edit)
        self._suffix = self._label(t("rt_unit_min"), "rainLabel")
        row.addWidget(self._suffix)
        row.addStretch(1)
        self._preview = self._label("", "rainPreview")
        row.addWidget(self._preview)
        lay.addLayout(row)
        lay.addWidget(self._divider())
        lay.addLayout(self._rain_row())
        lay.addLayout(self._after_row())
        self._refresh_preview()
        QTimer.singleShot(0, self._edit.setFocus)

    def _rain_row(self):
        tm = self._timer
        chips = []

        def pick(sec):
            tm.rain_s = sec
            for c, s in chips:
                c.setChecked(s == tm.rain_s)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._label(t("rt_rain_len"), "rainLabel"))
        row.addStretch(1)
        for sec in [m * 60 for m in RAIN_PRESETS] + [0]:
            c = self._chip(str(sec // 60) if sec else "∞", tm.rain_s == sec, lambda s=sec: pick(s))
            if not sec:
                install_tip(c, t("rt_forever"))
            chips.append((c, sec))
            row.addWidget(c)
        return row

    def _after_row(self):
        tm = self._timer
        chips = []

        def pick(on):
            tm.loop = on
            for c, v in chips:
                c.setChecked(v == tm.loop)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._label(t("rt_after"), "rainLabel"))
        row.addStretch(1)
        for label, on in ((t("rt_after_clear"), False), (t("rt_after_loop"), True)):
            c = self._chip(label, tm.loop == on, lambda on=on: pick(on), name=None)
            chips.append((c, on))
            row.addWidget(c)
        return row

    # 小部件

    @staticmethod
    def _label(text, name):
        lbl = QLabel(text)
        lbl.setObjectName(name)
        return lbl

    @staticmethod
    def _divider():
        f = QFrame()
        f.setObjectName("rainDivider")
        f.setFixedHeight(1)
        return f

    def _chip(self, text, on, cb, name="rainChip"):
        b = QPushButton(text)
        if name:
            b.setObjectName(name)
        b.setCheckable(True)
        b.setChecked(on)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False: cb())
        return b

    def _button(self, text, cb, close=False):
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False: (cb(), self.close() if close else None))
        return b

    # 输入

    def _start(self, sec):
        self._timer.start(sec)
        self.close()

    def _on_typed(self, _text):
        self._set_bad(False)
        self._refresh_preview()

    def _refresh_preview(self):
        if self._preview is None:
            return
        text = self._edit.text().strip()
        got = parse_input(text) if text else ("span", self._timer.dry_s)
        now = self._timer.now()
        self._suffix.setVisible(got is None or got[0] == "span")
        if got is None:
            self._preview.setText("")
        elif got[0] == "span":
            self._preview.setText(t("rt_preview", at=fmt_at(now + got[1])))
        else:
            self._preview.setText(t("rt_preview_in", at=fmt_at(got[1]), span=fmt_span(got[1] - now)))

    def _apply_input(self):
        text = self._edit.text().strip()
        if not text:
            self._start(None)
            return
        got = parse_input(text)
        if got is None:
            self._set_bad(True)
            return
        if got[0] == "at":
            self._timer.start_until(got[1])
            self.close()
        else:
            self._start(got[1])

    def _set_bad(self, bad):
        if self._edit is None or bool(self._edit.property("bad")) == bad:
            return
        self._edit.setProperty("bad", bad)
        self._edit.style().unpolish(self._edit)
        self._edit.style().polish(self._edit)

    # 刷新与摆放

    def _refresh_live(self):
        if self._head is not None:
            self._head.setText(status_line(self._timer))
        self._refresh_preview()

    def _on_event(self, ev):
        if ev in ("start", "rain", "clear", "stop", "lost"):
            self._build()

    def _place(self):
        self._box.adjustSize()
        self.adjustSize()
        a, w, h = self._anchor, self.width(), self.height()
        scr = QGuiApplication.screenAt(a.center()) or QGuiApplication.primaryScreen()
        area = scr.availableGeometry()
        spots = {
            "left": (a.left() - GAP - w, a.center().y() - h // 2),
            "right": (a.right() + GAP, a.center().y() - h // 2),
            "above": (a.center().x() - w // 2, a.top() - GAP - h),
            "below": (a.center().x() - w // 2, a.bottom() + GAP),
        }
        pick = None
        for side in self._sides:
            x, y = spots[side]
            fits_x = area.left() <= x and x + w <= area.right()
            fits_y = area.top() <= y and y + h <= area.bottom()
            if (side in ("left", "right") and fits_x) or (side in ("above", "below") and fits_y):
                pick = (x, y)
                break
        x, y = pick or spots[self._sides[0]]
        x = max(area.left(), min(x, area.right() - w))
        y = max(area.top(), min(y, area.bottom() - h))
        self.move(x, y)

    def closeEvent(self, ev):
        if self._on_event in self._timer.listeners:
            self._timer.listeners.remove(self._on_event)
        if RainCard._live is self:
            RainCard._live = None
        if self._on_close is not None:
            self._on_close()
        super().closeEvent(ev)
