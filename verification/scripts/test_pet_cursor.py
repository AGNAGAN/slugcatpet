import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

from slugcatpet.window import PetWindow

home = Path(os.environ["SLUGCATPET_HOME"])
params = json.loads((home / "app.json").read_text(encoding="utf-8"))
params["output"] = "HDMI-A-1"
params["cursor_hijack"] = True
params["cursor_shape"] = True

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)
pet = PetWindow(params=params)
_orig_enter = pet.enterEvent
_orig_leave = pet.leaveEvent

def _enter(e):
    print("EVENT enter", e.position())
    _orig_enter(e)

def _leave(e):
    print("EVENT leave")
    _orig_leave(e)

pet.enterEvent = _enter
pet.leaveEvent = _leave
pet.show()


def info(tag):
    backend = pet.desktop_backend
    print(
        tag,
        "available", pet.cursor_hijack_available,
        "cursor", backend.cursor_global(),
        "capture", pet._cursor_capture,
        "busy", pet._wayland_busy,
        "override", QApplication.overrideCursor() is not None,
        "hijack", pet.cursor_hijack is not None,
        "qcursor", QCursor.pos(),
        "mask_empty", pet.windowHandle().mask().isEmpty() if pet.windowHandle() else None,
        "mask_bounds", pet.windowHandle().mask().boundingRect().getRect() if pet.windowHandle() else None,
        "win_geom", pet.geometry().getRect(),
        "win_frame", pet.frameGeometry().getRect(),
        "handle_geom", pet.windowHandle().geometry().getRect() if pet.windowHandle() else None,
        "handle_frame", pet.windowHandle().frameGeometry().getRect() if pet.windowHandle() else None,
    )


def start():
    info("START")
    if not pet.cursor_hijack_available:
        print("UNAVAILABLE")
        app.quit()
        return
    cur = pet.desktop_backend.cursor_global()
    if cur is None:
        print("NO CURSOR")
        app.quit()
        return
    x = (cur[0] - pet.overlay_rect().x()) / pet._scale
    y = (cur[1] - pet.overlay_rect().y()) / pet._scale
    print("cursor logical", x, y, "expected global", pet._area.x() + x * pet._scale, pet._area.y() + y * pet._scale)
    hj = pet.start_cursor_hold(x, y, 200)
    print("created", hj is not None, "mock", getattr(hj, "mock", None))
    h = pet.windowHandle()
    if h is not None:
        try:
            h.requestActivate()
            print("requestActivate called")
        except Exception as e:
            print("requestActivate error", e)
    QTimer.singleShot(900, step2)


def step2():
    info("HOLD1")
    x = pet._WL / 3
    y = pet._HL / 3
    print("target2 logical", x, y, "expected global",
          pet._area.x() + x * pet._scale, pet._area.y() + y * pet._scale)
    pet.move_cursor_hold(x, y)
    QTimer.singleShot(900, step3)


def step3():
    info("HOLD2")
    pet.stop_cursor_hijack()
    QTimer.singleShot(500, step4)


def step4():
    info("STOP")
    app.quit()


QTimer.singleShot(1800, start)
QTimer.singleShot(8000, app.quit)
app.exec()
print("DONE")
