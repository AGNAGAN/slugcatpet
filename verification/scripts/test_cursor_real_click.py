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


def info(tag):
    cap = pet._cursor_capture_window
    print(
        tag,
        "capture_state", pet._cursor_capture,
        "capture_visible", bool(cap and cap.isVisible()),
        "busy", pet._wayland_busy,
        "override", QApplication.overrideCursor() is not None,
        "hijack", pet.cursor_hijack is not None,
        flush=True,
    )


def start():
    cur = pet.desktop_backend.cursor_global()
    if cur is None:
        print("NO CURSOR", flush=True)
        app.quit()
        return
    x = (cur[0] - pet.overlay_rect().x()) / pet._scale
    y = (cur[1] - pet.overlay_rect().y()) / pet._scale
    pet.start_cursor_hold(x, y, 400)
    info("START")


QTimer.singleShot(1600, start)
for delay in (1000, 2500, 4000, 6000, 8000):
    QTimer.singleShot(delay, lambda d=delay: info(f"T{d}"))
QTimer.singleShot(11000, app.quit)
app.exec()
print("DONE", flush=True)
