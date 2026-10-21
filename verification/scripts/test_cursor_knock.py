import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
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
pet.show()
backend = pet.desktop_backend


def start():
    cur = backend.cursor_global()
    print("START", cur, "overlay", pet.overlay_rect().getRect(), flush=True)
    if cur is None:
        app.quit()
        return
    x = (cur[0] - pet.overlay_rect().x()) / pet._scale
    y = (cur[1] - pet.overlay_rect().y()) / pet._scale
    hj = pet.start_cursor_hijack(x, y, lock_ticks=30, knock_v=(220.0, -40.0))
    print("created", hj is not None, "mock", getattr(hj, "mock", None), flush=True)
    QTimer.singleShot(1200, check)


def check():
    print(
        "KNOCK",
        "cursor", backend.cursor_global(),
        "hijack", pet.cursor_hijack is not None,
        "capture", bool(pet._cursor_capture_window and pet._cursor_capture_window.isVisible()),
        flush=True,
    )
    pet.stop_cursor_hijack()
    QTimer.singleShot(500, done)


def done():
    print("STOP", backend.cursor_global(), pet.cursor_hijack, flush=True)
    app.quit()


QTimer.singleShot(1800, start)
QTimer.singleShot(8000, app.quit)
app.exec()
