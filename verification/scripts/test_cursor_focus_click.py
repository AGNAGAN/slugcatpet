import json
import os
import sys
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from slugcatpet.window import CursorCaptureWindow, PetWindow

_orig_cap_enter = CursorCaptureWindow.enterEvent
_orig_cap_leave = CursorCaptureWindow.leaveEvent


def _cap_enter(self, ev):
    print("CAP CLASS ENTER", ev.position(), "geom", self.geometry().getRect())
    _orig_cap_enter(self, ev)


def _cap_leave(self, ev):
    print("CAP CLASS LEAVE")
    _orig_cap_leave(self, ev)


CursorCaptureWindow.enterEvent = _cap_enter
CursorCaptureWindow.leaveEvent = _cap_leave

home = Path(os.environ["SLUGCATPET_HOME"])
params = json.loads((home / "app.json").read_text(encoding="utf-8"))
params["output"] = "HDMI-A-1"
params["cursor_hijack"] = True
params["cursor_shape"] = True

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
pet = PetWindow(params=params)
pet.show()

_orig_setpos = QCursor.setPos


def _traced_setpos(point):
    print("QCURSOR_SETPOS", point.x(), point.y())
    return _orig_setpos(point)


QCursor.setPos = staticmethod(_traced_setpos)

_orig_show_capture = pet._show_cursor_capture


def _traced_show_capture():
    win = _orig_show_capture()
    if win is not None and getattr(win, "_diag", False) is False:
        win._diag = True
        orig_enter = win.enterEvent
        orig_leave = win.leaveEvent

        def enter(ev):
            print("CAP ENTER", ev.position(), "geom", win.geometry().getRect(), "frame", win.frameGeometry().getRect())
            orig_enter(ev)

        def leave(ev):
            print("CAP LEAVE")
            orig_leave(ev)

        win.enterEvent = enter
        win.leaveEvent = leave
    print("CAP SHOW", win.geometry().getRect() if win else None, win.isVisible() if win else None)
    return win


pet._show_cursor_capture = _traced_show_capture


def info(tag):
    backend = pet.desktop_backend
    cap = pet._cursor_capture_window
    print(
        tag,
        "cursor", backend.cursor_global(),
        "capture_state", pet._cursor_capture,
        "capture_visible", bool(cap and cap.isVisible()),
        "busy", pet._wayland_busy,
        "override", QApplication.overrideCursor() is not None,
        "hijack", pet.cursor_hijack is not None,
        "qcursor", QCursor.pos(),
    )


def start():
    info("START")
    cur = pet.desktop_backend.cursor_global()
    if cur is None:
        print("NO CURSOR")
        app.quit()
        return
    x = (cur[0] - pet.overlay_rect().x()) / pet._scale
    y = (cur[1] - pet.overlay_rect().y()) / pet._scale
    hj = pet.start_cursor_hold(x, y, 400)
    print("created", hj is not None, "mock", getattr(hj, "mock", None))
    QTimer.singleShot(700, step_move)


def step_move():
    info("HOLD")
    x = pet._WL / 3
    y = pet._HL / 3
    print("move to", x, y)
    pet.move_cursor_hold(x, y)
    QTimer.singleShot(700, step_click)


def step_click():
    info("BEFORE_CLICK")
    cap = pet._cursor_capture_window
    if cap is None or not cap.isVisible():
        print("NO CAPTURE")
        app.quit()
        return
    QTest.mouseClick(cap, Qt.MouseButton.LeftButton)
    QTimer.singleShot(350, step_after_click)


def step_after_click():
    info("AFTER_CLICK")
    # 再抢一次，验证右键同样解除。
    cur = pet.desktop_backend.cursor_global()
    if cur is None:
        print("NO CURSOR 2")
        app.quit()
        return
    x = (cur[0] - pet.overlay_rect().x()) / pet._scale
    y = (cur[1] - pet.overlay_rect().y()) / pet._scale
    pet.start_cursor_hold(x, y, 400)
    QTimer.singleShot(500, step_move2)


def step_move2():
    info("HOLD2")
    x = pet._WL / 4
    y = pet._HL / 2
    print("move2 to", x, y)
    pet.move_cursor_hold(x, y)
    QTimer.singleShot(700, step_right_click)


def step_right_click():
    info("HOLD2_BEFORE_CLICK")
    cap = pet._cursor_capture_window
    if cap is None or not cap.isVisible():
        print("NO CAPTURE 2")
        app.quit()
        return
    QTest.mouseClick(cap, Qt.MouseButton.RightButton)
    QTimer.singleShot(350, step_stop)


def step_stop():
    info("STOP")
    app.quit()


QTimer.singleShot(1600, start)
QTimer.singleShot(8000, app.quit)
app.exec()
print("DONE")
